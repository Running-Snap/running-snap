"""
구도 분석기
러너 검출, 진행 방향 파악, 자동 크롭 계산
"""
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
import numpy as np
import cv2
from rich.console import Console

from ..core.config_loader import ConfigLoader


@dataclass
class RunnerDetection:
    """러너 검출 결과"""
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    center: Tuple[int, int]          # (cx, cy)
    size_ratio: float                # 화면 대비 크기 비율
    confidence: float                # 검출 신뢰도


@dataclass
class MotionDirection:
    """움직임 방향"""
    direction: str           # "left", "right", "unknown"
    confidence: float        # 방향 신뢰도
    velocity: Tuple[float, float]  # (vx, vy) 평균 속도


@dataclass
class CompositionResult:
    """구도 분석 결과"""
    runner: Optional[RunnerDetection]
    motion: Optional[MotionDirection]
    crop_box: Optional[Tuple[int, int, int, int]]  # (x, y, w, h)
    composition_type: str
    metadata: Dict[str, Any]


class CompositionAnalyzer:
    """구도 분석 및 자동 크롭 계산기"""

    def __init__(
        self,
        config_loader: ConfigLoader,
        console: Optional[Console] = None
    ):
        self.config = config_loader
        self.console = console or Console()
        self.composition_config = self._load_composition_config()

        # HOG 사람 검출기 초기화
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def _load_composition_config(self) -> dict:
        """구도 설정 로드"""
        try:
            return self.config._load_yaml("composition_styles.yaml")
        except Exception:
            return self._get_default_config()

    def _get_default_config(self) -> dict:
        """기본 구도 설정"""
        return {
            "composition_types": {
                "action_shot": {
                    "parameters": {
                        "runner_size_ratio": 0.40,
                        "horizontal_position": 0.33,
                        "vertical_position": 0.50,
                        "leading_space": 0.60
                    }
                },
                "environmental": {
                    "parameters": {
                        "runner_size_ratio": 0.20,
                        "horizontal_position": 0.50,
                        "vertical_position": 0.66
                    }
                },
                "dynamic_closeup": {
                    "parameters": {
                        "runner_size_ratio": 0.70,
                        "horizontal_position": 0.45,
                        "vertical_position": 0.33
                    }
                }
            }
        }

    def detect_runner(
        self,
        frame: np.ndarray,
        use_gpu: bool = False
    ) -> Optional[RunnerDetection]:
        """
        프레임에서 러너(사람) 검출

        Args:
            frame: BGR 이미지
            use_gpu: GPU 사용 여부 (현재 미지원)

        Returns:
            RunnerDetection 또는 None
        """
        h, w = frame.shape[:2]

        # HOG로 사람 검출
        boxes, weights = self.hog.detectMultiScale(
            frame,
            winStride=(8, 8),
            padding=(4, 4),
            scale=1.05
        )

        if len(boxes) == 0:
            return None

        # 가장 큰 (또는 가장 신뢰도 높은) 사람 선택
        best_idx = 0
        best_score = 0

        for i, (box, weight) in enumerate(zip(boxes, weights)):
            x, y, bw, bh = box
            # 크기와 신뢰도 조합
            score = (bw * bh) * weight
            if score > best_score:
                best_score = score
                best_idx = i

        x, y, bw, bh = boxes[best_idx]
        confidence = float(weights[best_idx])

        # 중심점 계산
        cx = x + bw // 2
        cy = y + bh // 2

        # 화면 대비 크기 비율
        size_ratio = (bw * bh) / (w * h)

        return RunnerDetection(
            bbox=(int(x), int(y), int(bw), int(bh)),
            center=(int(cx), int(cy)),
            size_ratio=float(size_ratio),
            confidence=confidence
        )

    def detect_motion_direction(
        self,
        frame_current: np.ndarray,
        frame_prev: Optional[np.ndarray] = None,
        runner_bbox: Optional[Tuple[int, int, int, int]] = None
    ) -> MotionDirection:
        """
        움직임 방향 검출 (Optical Flow 사용)

        Args:
            frame_current: 현재 프레임
            frame_prev: 이전 프레임 (없으면 방향 추정 불가)
            runner_bbox: 러너 영역 (있으면 해당 영역만 분석)

        Returns:
            MotionDirection
        """
        if frame_prev is None:
            return MotionDirection(
                direction="unknown",
                confidence=0.0,
                velocity=(0.0, 0.0)
            )

        # 그레이스케일 변환
        gray_curr = cv2.cvtColor(frame_current, cv2.COLOR_BGR2GRAY)
        gray_prev = cv2.cvtColor(frame_prev, cv2.COLOR_BGR2GRAY)

        # 러너 영역만 분석
        if runner_bbox:
            x, y, w, h = runner_bbox
            # 패딩 추가
            pad = 20
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(gray_curr.shape[1], x + w + pad)
            y2 = min(gray_curr.shape[0], y + h + pad)

            gray_curr = gray_curr[y1:y2, x1:x2]
            gray_prev = gray_prev[y1:y2, x1:x2]

        # Dense Optical Flow (Farneback)
        flow = cv2.calcOpticalFlowFarneback(
            gray_prev, gray_curr,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )

        # 평균 속도 계산
        vx = float(np.mean(flow[:, :, 0]))
        vy = float(np.mean(flow[:, :, 1]))

        # 방향 결정 (수평 움직임 기준)
        if abs(vx) < 0.5:  # 거의 움직임 없음
            direction = "unknown"
            confidence = 0.3
        elif vx > 0:
            direction = "right"
            confidence = min(1.0, abs(vx) / 5.0)
        else:
            direction = "left"
            confidence = min(1.0, abs(vx) / 5.0)

        return MotionDirection(
            direction=direction,
            confidence=confidence,
            velocity=(vx, vy)
        )

    def calculate_crop_box(
        self,
        frame: np.ndarray,
        runner: RunnerDetection,
        motion: MotionDirection,
        composition_type: str,
        aspect_ratio: Tuple[int, int] = (16, 9)
    ) -> Tuple[int, int, int, int]:
        """
        구도 타입에 맞는 크롭 박스 계산

        핵심 원칙: 러너 전신이 절대 잘리지 않도록 보장

        Args:
            frame: 원본 프레임
            runner: 러너 검출 결과
            motion: 움직임 방향
            composition_type: 구도 타입 ("action_shot", "environmental", "dynamic_closeup")
            aspect_ratio: 출력 종횡비

        Returns:
            (x, y, w, h) 크롭 박스
        """
        h, w = frame.shape[:2]
        rx, ry, rw, rh = runner.bbox
        rcx, rcy = runner.center

        # 구도 파라미터 로드
        comp_types = self.composition_config.get("composition_types", {})
        params = comp_types.get(composition_type, {}).get("parameters", {})

        target_size_ratio = params.get("runner_size_ratio", 0.40)
        target_h_pos = params.get("horizontal_position", 0.33)
        target_v_pos = params.get("vertical_position", 0.50)
        leading_space = params.get("leading_space", 0.60)

        # 진행 방향에 따라 수평 위치 조정
        if motion.direction == "right":
            # 오른쪽으로 가면 러너를 왼쪽에 배치 (오른쪽에 여백)
            target_h_pos = 1.0 - leading_space
        elif motion.direction == "left":
            # 왼쪽으로 가면 러너를 오른쪽에 배치 (왼쪽에 여백)
            target_h_pos = leading_space
        # direction이 unknown이면 기본값 유지

        # 다이나믹 클로즈업은 방향에 따라 미세 조정
        if composition_type == "dynamic_closeup":
            if motion.direction == "right":
                target_h_pos = 0.55
            elif motion.direction == "left":
                target_h_pos = 0.45

        # ============================================
        # 핵심: 러너 전신이 잘리지 않도록 최소 크롭 크기 계산
        # ============================================

        # 러너 bbox에 여유 패딩 추가 (머리 위, 발 아래 공간)
        padding_ratio = 0.15  # 15% 여유 공간
        runner_padded_h = int(rh * (1 + padding_ratio * 2))  # 위아래 패딩
        runner_padded_w = int(rw * (1 + padding_ratio * 2))  # 좌우 패딩

        # 종횡비 계산
        ar_w, ar_h = aspect_ratio
        ar = ar_w / ar_h

        # 러너가 목표 비율을 차지하려면 필요한 크롭 크기
        # 러너 높이 기준으로 계산 (전신 보장)
        crop_h_for_ratio = int(runner_padded_h / target_size_ratio)
        crop_w_for_ratio = int(crop_h_for_ratio * ar)

        # 러너 전신이 반드시 들어가는 최소 크롭 크기
        # 러너 위치(target_h_pos, target_v_pos)를 고려해서 계산
        min_crop_w_for_runner = int(runner_padded_w / min(target_h_pos, 1 - target_h_pos) / 2)
        min_crop_h_for_runner = int(runner_padded_h / min(target_v_pos, 1 - target_v_pos) / 2)

        # 더 보수적인 계산: 러너 bbox가 완전히 포함되도록
        # 러너가 crop의 target_h_pos에 위치할 때, 양쪽 끝까지의 거리
        space_left = target_h_pos  # 러너 왼쪽 공간 비율
        space_right = 1 - target_h_pos  # 러너 오른쪽 공간 비율
        space_top = target_v_pos
        space_bottom = 1 - target_v_pos

        # 러너 전신이 들어가려면 필요한 최소 크롭 크기
        min_w_left = int((rx - 0) / space_left) if space_left > 0 else w  # 러너 왼쪽 끝 포함
        min_w_right = int((rx + rw) / (1 - space_right)) if space_right < 1 else w  # 러너 오른쪽 끝 포함
        min_h_top = int((ry - 0) / space_top) if space_top > 0 else h
        min_h_bottom = int((ry + rh) / (1 - space_bottom)) if space_bottom < 1 else h

        # 실제 필요한 최소 크롭 크기 (전신 포함 보장)
        min_crop_w = max(runner_padded_w * 2, int(rw / 0.5))  # 러너가 최대 50%를 넘지 않도록
        min_crop_h = max(runner_padded_h * 2, int(rh / 0.5))

        # 목표 크롭 크기 (러너 비율 기반) vs 최소 크롭 크기 중 큰 값 선택
        crop_w = max(crop_w_for_ratio, min_crop_w)
        crop_h = max(crop_h_for_ratio, min_crop_h)

        # 종횡비 맞추기
        if crop_w / crop_h > ar:
            # 너비가 더 넓음 -> 높이 맞춤
            crop_h = int(crop_w / ar)
        else:
            # 높이가 더 높음 -> 너비 맞춤
            crop_w = int(crop_h * ar)

        # 프레임 경계 체크 및 조정
        if crop_h > h:
            crop_h = h
            crop_w = int(crop_h * ar)
        if crop_w > w:
            crop_w = w
            crop_h = int(crop_w / ar)

        # ============================================
        # 러너 중심을 목표 위치에 배치하되, 전신이 잘리지 않도록 조정
        # ============================================

        # 초기 크롭 위치 (러너 중심 기준)
        crop_x = int(rcx - crop_w * target_h_pos)
        crop_y = int(rcy - crop_h * target_v_pos)

        # 프레임 경계 내로 조정
        crop_x = int(np.clip(crop_x, 0, w - crop_w))
        crop_y = int(np.clip(crop_y, 0, h - crop_h))

        # ============================================
        # 최종 검증: 러너 bbox가 크롭 영역 안에 완전히 포함되는지 확인
        # ============================================
        runner_left = rx
        runner_right = rx + rw
        runner_top = ry
        runner_bottom = ry + rh

        crop_left = crop_x
        crop_right = crop_x + crop_w
        crop_top = crop_y
        crop_bottom = crop_y + crop_h

        # 러너가 잘리는 경우 크롭 위치 재조정
        if runner_left < crop_left:
            crop_x = max(0, runner_left - int(rw * padding_ratio))
        if runner_right > crop_right:
            crop_x = min(w - crop_w, runner_right - crop_w + int(rw * padding_ratio))
        if runner_top < crop_top:
            crop_y = max(0, runner_top - int(rh * padding_ratio))
        if runner_bottom > crop_bottom:
            crop_y = min(h - crop_h, runner_bottom - crop_h + int(rh * padding_ratio))

        return (int(crop_x), int(crop_y), int(crop_w), int(crop_h))

    def apply_crop(
        self,
        frame: np.ndarray,
        crop_box: Tuple[int, int, int, int],
        output_size: Optional[Tuple[int, int]] = None
    ) -> np.ndarray:
        """
        크롭 적용

        Args:
            frame: 원본 프레임
            crop_box: (x, y, w, h)
            output_size: 출력 크기 (w, h), None이면 크롭 크기 그대로

        Returns:
            크롭된 프레임
        """
        x, y, w, h = crop_box
        cropped = frame[y:y+h, x:x+w]

        if output_size:
            cropped = cv2.resize(cropped, output_size, interpolation=cv2.INTER_LANCZOS4)

        return cropped

    def analyze_and_crop(
        self,
        frame: np.ndarray,
        frame_prev: Optional[np.ndarray],
        composition_type: str,
        aspect_ratio: Tuple[int, int] = (16, 9),
        output_size: Optional[Tuple[int, int]] = None
    ) -> CompositionResult:
        """
        구도 분석 및 크롭 통합 처리

        Args:
            frame: 현재 프레임
            frame_prev: 이전 프레임 (방향 분석용)
            composition_type: 구도 타입
            aspect_ratio: 출력 종횡비
            output_size: 출력 크기

        Returns:
            CompositionResult
        """
        # 1. 러너 검출
        runner = self.detect_runner(frame)

        if runner is None:
            # 러너 검출 실패시 중앙 크롭
            h, w = frame.shape[:2]
            ar_w, ar_h = aspect_ratio
            ar = ar_w / ar_h

            crop_h = h
            crop_w = int(crop_h * ar)
            if crop_w > w:
                crop_w = w
                crop_h = int(crop_w / ar)

            crop_x = (w - crop_w) // 2
            crop_y = (h - crop_h) // 2

            return CompositionResult(
                runner=None,
                motion=None,
                crop_box=(crop_x, crop_y, crop_w, crop_h),
                composition_type=composition_type,
                metadata={"fallback": "center_crop", "reason": "no_runner_detected"}
            )

        # 2. 움직임 방향 검출
        motion = self.detect_motion_direction(
            frame,
            frame_prev,
            runner.bbox
        )

        # 3. 크롭 박스 계산
        crop_box = self.calculate_crop_box(
            frame,
            runner,
            motion,
            composition_type,
            aspect_ratio
        )

        # 4. 메타데이터 생성
        h, w = frame.shape[:2]
        cx, cy = crop_box[0] + crop_box[2] // 2, crop_box[1] + crop_box[3] // 2
        runner_in_crop_x = (runner.center[0] - crop_box[0]) / crop_box[2]
        runner_in_crop_y = (runner.center[1] - crop_box[1]) / crop_box[3]

        metadata = {
            "runner_size_ratio": runner.size_ratio,
            "runner_position": {"x": runner_in_crop_x, "y": runner_in_crop_y},
            "motion_direction": motion.direction,
            "motion_confidence": motion.confidence,
            "leading_space": 1 - runner_in_crop_x if motion.direction == "right" else runner_in_crop_x,
            "composition_type": composition_type
        }

        return CompositionResult(
            runner=runner,
            motion=motion,
            crop_box=crop_box,
            composition_type=composition_type,
            metadata=metadata
        )

    def validate_composition(
        self,
        result: CompositionResult,
        frame_shape: Optional[Tuple[int, int]] = None
    ) -> Tuple[bool, List[str]]:
        """
        구도 검증 (금지 사항 체크)

        Returns:
            (통과 여부, 위반 사항 리스트)
        """
        violations = []
        meta = result.metadata

        # 정중앙 배치 체크
        if result.runner:
            rx = meta.get("runner_position", {}).get("x", 0.5)
            if abs(rx - 0.5) < 0.05:
                violations.append("러너가 정중앙에 배치됨")

        # 진행 방향 여백 체크
        leading = meta.get("leading_space", 0)
        if result.motion and result.motion.direction != "unknown":
            if leading < 0.40:
                violations.append(f"진행 방향 여백 부족 ({leading:.0%})")

        # 환경샷이 아닌데 러너가 너무 작음
        if result.composition_type != "environmental":
            size = meta.get("runner_size_ratio", 0)
            if size < 0.10:
                violations.append(f"러너가 너무 작음 ({size:.0%})")

        # ★ 러너 전신 잘림 체크 (가장 중요)
        if result.runner and result.crop_box:
            rx, ry, rw, rh = result.runner.bbox
            cx, cy, cw, ch = result.crop_box

            # 러너가 크롭 영역 밖으로 나가는지 체크
            if rx < cx:
                violations.append(f"러너 왼쪽이 잘림 ({cx - rx}px)")
            if rx + rw > cx + cw:
                violations.append(f"러너 오른쪽이 잘림 ({(rx + rw) - (cx + cw)}px)")
            if ry < cy:
                violations.append(f"러너 위쪽(머리)이 잘림 ({cy - ry}px)")
            if ry + rh > cy + ch:
                violations.append(f"러너 아래쪽(발)이 잘림 ({(ry + rh) - (cy + ch)}px)")

        return len(violations) == 0, violations
