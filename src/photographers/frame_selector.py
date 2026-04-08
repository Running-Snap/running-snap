"""
베스트컷 프레임 선별기
분석 결과를 기반으로 가장 미학적인 순간 선택
스타일별 구도 적용 및 비율 변환 지원
"""
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import numpy as np
import cv2
from rich.console import Console

from ..core.config_loader import ConfigLoader
from ..core.models import VideoAnalysis, FrameAnalysis, PhotoCandidate, OutputConfig, OutputRatio
from ..core.exceptions import PhotoProcessingError
from .composition_analyzer import CompositionAnalyzer, CompositionResult
from ..renderers.effects.reframe import SmartReframer, SubjectTracker, SubjectPosition


class FrameSelector:
    """베스트컷 프레임 선별기"""

    def __init__(
        self,
        config_loader: ConfigLoader,
        console: Optional[Console] = None
    ):
        self.config = config_loader
        self.console = console or Console()

        # 설정 로드
        self.criteria = config_loader.get_photo_selection_criteria()
        self.weights = self._get_scoring_weights()

        # 구도 분석기 초기화
        self.composition_analyzer = CompositionAnalyzer(config_loader, console)

        # 구도 스타일 설정 로드
        self.composition_config = self._load_composition_config()

        # Smart Reframe 초기화
        self._reframer = SmartReframer()
        self._subject_tracker = SubjectTracker()

    def _get_scoring_weights(self) -> dict:
        """점수 가중치 로드"""
        try:
            config = self.config._load_yaml("photo_grading.yaml")
            return config.get("scoring_weights", {
                "aesthetic_score": 0.30,
                "composition_score": 0.25,
                "emotional_impact": 0.25,
                "technical_quality": 0.20
            })
        except Exception:
            return {
                "aesthetic_score": 0.30,
                "composition_score": 0.25,
                "emotional_impact": 0.25,
                "technical_quality": 0.20
            }

    def _load_composition_config(self) -> dict:
        """구도 스타일 설정 로드"""
        try:
            return self.config._load_yaml("composition_styles.yaml")
        except Exception:
            return {}

    def select_best_frames(
        self,
        video_path: str,
        analysis: VideoAnalysis,
        count: int = 5,
        output_dir: Optional[str] = None,
        style: str = "action",
        apply_composition: bool = True,
        output_config: Optional[OutputConfig] = None
    ) -> List[PhotoCandidate]:
        """
        베스트컷 선별 (스타일별 구도 적용)

        Args:
            video_path: 원본 영상 경로
            analysis: 영상 분석 결과
            count: 선택할 베스트컷 수
            output_dir: 프레임 저장 디렉토리
            style: 편집 스타일 (구도 매핑에 사용)
            apply_composition: 구도 자동 조정 적용 여부
            output_config: 출력 설정 (비율 등, None이면 스타일에서 자동)

        Returns:
            PhotoCandidate 리스트
        """
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            raise PhotoProcessingError(f"영상 파일이 없습니다: {video_path}")

        # 출력 설정 (비율)
        if output_config is None:
            output_config = OutputConfig.from_style(style, self.config)

        self.console.print(f"[cyan]베스트컷 선별 중... (목표: {count}장, 비율: {output_config.ratio})[/cyan]")

        # 1. 모든 프레임 점수 계산
        candidates = self._score_all_frames(analysis.frames)

        # 2. 최소 기준 필터링
        threshold = self.criteria.get("aesthetic_score_threshold", 0.5)
        filtered = [c for c in candidates if c.aesthetic_score >= threshold]

        if not filtered:
            self.console.print("[yellow]기준을 충족하는 프레임이 없어 전체에서 선택합니다[/yellow]")
            filtered = candidates

        # 3. 스타일별 구도 매핑 확인
        style_mapping = self._get_style_mapping(style)

        if apply_composition and style_mapping:
            # 구도 기반 선별
            selected = self._select_with_composition(
                video_path=str(video_path_obj),
                candidates=filtered,
                count=count,
                style_mapping=style_mapping
            )
        else:
            # 기존 방식 (다양성 기반)
            min_gap = self.criteria.get("diversity", {}).get("min_time_gap", 1.0)
            selected = self._select_with_diversity(filtered, count, min_gap)

        # 4. 프레임 추출 및 저장 (구도 + 비율 적용)
        if output_dir:
            output_dir_path = Path(output_dir)
            output_dir_path.mkdir(parents=True, exist_ok=True)

            if apply_composition and style_mapping:
                self._extract_with_composition(
                    video_path=str(video_path_obj),
                    selected=selected,
                    output_dir=output_dir_path,
                    style_mapping=style_mapping,
                    output_config=output_config
                )
            else:
                self._extract_frames_basic(
                    video_path=str(video_path_obj),
                    selected=selected,
                    output_dir=output_dir_path,
                    output_config=output_config
                )

        self.console.print(f"[green]✓ {len(selected)}장의 베스트컷 선별 완료[/green]")
        return selected

    def _get_style_mapping(self, style: str) -> Optional[Dict[str, Any]]:
        """스타일에 해당하는 구도 매핑 가져오기"""
        style_mappings = self.composition_config.get("style_mappings", {})
        return style_mappings.get(style)

    def _select_with_composition(
        self,
        video_path: str,
        candidates: List[PhotoCandidate],
        count: int,
        style_mapping: Dict[str, Any]
    ) -> List[PhotoCandidate]:
        """
        구도 기반 베스트컷 선별

        - 주 구도로 N장 (distribution.primary)
        - 보조 구도로 나머지 장

        Args:
            video_path: 영상 경로
            candidates: 후보 프레임들
            count: 총 선택 수
            style_mapping: 스타일 구도 매핑

        Returns:
            선택된 PhotoCandidate 리스트
        """
        primary_comp = style_mapping.get("primary_composition", "action_shot")
        secondary_comp = style_mapping.get("secondary_composition", "dynamic_closeup")
        distribution = style_mapping.get("distribution", {"primary": 3, "secondary": 2})

        primary_count = min(distribution.get("primary", 3), count)
        secondary_count = count - primary_count

        # 점수순 정렬
        sorted_candidates = sorted(
            candidates,
            key=lambda c: c.overall_score,
            reverse=True
        )

        # 다양성을 위한 최소 간격
        min_gap = self.criteria.get("diversity", {}).get("min_time_gap", 1.0)

        # 주 구도용 프레임 선택
        primary_selected = self._select_for_composition(
            sorted_candidates,
            primary_count,
            min_gap,
            composition_type=primary_comp
        )

        # 보조 구도용 프레임 선택 (이미 선택된 것 제외)
        remaining = [c for c in sorted_candidates if c not in primary_selected]
        secondary_selected = self._select_for_composition(
            remaining,
            secondary_count,
            min_gap,
            composition_type=secondary_comp,
            exclude_timestamps=[c.timestamp for c in primary_selected]
        )

        # 결합 및 정렬
        all_selected = primary_selected + secondary_selected

        # 구도 정보 저장 (metadata로)
        for c in primary_selected:
            c.frame_path = f"__composition__:{primary_comp}"
        for c in secondary_selected:
            c.frame_path = f"__composition__:{secondary_comp}"

        return sorted(all_selected, key=lambda c: c.timestamp)

    def _select_for_composition(
        self,
        candidates: List[PhotoCandidate],
        count: int,
        min_gap: float,
        composition_type: str,
        exclude_timestamps: List[float] = None
    ) -> List[PhotoCandidate]:
        """특정 구도 타입에 적합한 프레임 선택"""
        if exclude_timestamps is None:
            exclude_timestamps = []

        selected = []

        for candidate in candidates:
            if len(selected) >= count:
                break

            # 제외 타임스탬프 체크
            if candidate.timestamp in exclude_timestamps:
                continue

            # 다양성 체크
            is_diverse = all(
                abs(candidate.timestamp - s.timestamp) >= min_gap
                for s in selected
            )

            if is_diverse:
                selected.append(candidate)

        return selected

    def _extract_with_composition(
        self,
        video_path: str,
        selected: List[PhotoCandidate],
        output_dir: Path,
        style_mapping: Dict[str, Any],
        output_config: Optional[OutputConfig] = None
    ):
        """구도 적용하여 프레임 추출 (스마트 리프레임 포함)"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise PhotoProcessingError(f"영상을 열 수 없습니다: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_prev = None

        # 출력 비율 파싱
        if output_config:
            output_ratio = OutputRatio.from_string(output_config.ratio)
            out_width, out_height = output_ratio.dimensions
            aspect_ratio = self._parse_ratio(output_config.ratio)
        else:
            out_width, out_height = 1920, 1080
            aspect_ratio = (16, 9)

        try:
            for i, candidate in enumerate(selected):
                # 구도 타입 추출
                comp_marker = candidate.frame_path or ""
                if comp_marker.startswith("__composition__:"):
                    composition_type = comp_marker.split(":")[1]
                else:
                    composition_type = style_mapping.get("primary_composition", "action_shot")

                # 현재 프레임 추출
                frame_number = int(candidate.timestamp * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()

                if not ret:
                    continue

                # 이전 프레임 추출 (방향 분석용)
                if candidate.timestamp > 0.1:
                    prev_frame_number = int((candidate.timestamp - 0.1) * fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, prev_frame_number)
                    ret_prev, frame_prev = cap.read()
                    if not ret_prev:
                        frame_prev = None

                    # 다시 현재 프레임으로
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                    cap.read()

                # 스마트 리프레임: 피사체 기반 크롭
                if output_config and output_config.ratio != "16:9":
                    cropped = self._apply_smart_reframe(
                        frame, output_config, candidate.timestamp
                    )
                else:
                    # 기존 구도 분석 및 크롭 (16:9용)
                    result = self.composition_analyzer.analyze_and_crop(
                        frame=frame,
                        frame_prev=frame_prev,
                        composition_type=composition_type,
                        aspect_ratio=aspect_ratio,
                        output_size=None
                    )

                    if result.crop_box:
                        cropped = self.composition_analyzer.apply_crop(
                            frame,
                            result.crop_box,
                            output_size=(out_width, out_height)
                        )
                    else:
                        cropped = cv2.resize(frame, (out_width, out_height))

                # 저장
                frame_path = output_dir / f"best_{i+1}_{candidate.timestamp:.2f}s.png"
                cv2.imwrite(str(frame_path), cropped)
                candidate.frame_path = str(frame_path)

                # 메타데이터 저장 (JSON)
                meta_path = output_dir / f"best_{i+1}_{candidate.timestamp:.2f}s_meta.json"
                self._save_photo_metadata(meta_path, candidate, output_config)

                frame_prev = frame

        finally:
            cap.release()

    def _apply_smart_reframe(
        self,
        frame: np.ndarray,
        output_config: OutputConfig,
        timestamp: float
    ) -> np.ndarray:
        """스마트 리프레임 적용 (피사체 추적 기반)"""
        h, w = frame.shape[:2]

        # 피사체 감지
        subject_pos = self._subject_tracker._detect_subject(frame, timestamp)

        if subject_pos and subject_pos.confidence > 0.3:
            # 피사체 기반 크롭
            reframed = self._reframer.reframe_image(
                frame, output_config.ratio, subject_pos
            )
        else:
            # 피사체 없으면 중앙 크롭
            target_ratio = output_config.width / output_config.height
            source_ratio = w / h

            if source_ratio > target_ratio:
                # 원본이 더 넓음 → 좌우 자르기
                new_w = int(h * target_ratio)
                x_start = (w - new_w) // 2
                reframed = frame[:, x_start:x_start + new_w]
            else:
                # 원본이 더 좁음 → 상하 자르기
                new_h = int(w / target_ratio)
                y_start = (h - new_h) // 2
                reframed = frame[y_start:y_start + new_h, :]

        # 최종 크기 조정
        return cv2.resize(reframed, (output_config.width, output_config.height))

    def _extract_frames_basic(
        self,
        video_path: str,
        selected: List[PhotoCandidate],
        output_dir: Path,
        output_config: Optional[OutputConfig] = None
    ):
        """기본 프레임 추출 (스마트 리프레임 적용)"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise PhotoProcessingError(f"영상을 열 수 없습니다: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)

        try:
            for i, candidate in enumerate(selected):
                frame_number = int(candidate.timestamp * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()

                if ret:
                    # 비율 변환 적용
                    if output_config:
                        frame = self._apply_smart_reframe(
                            frame, output_config, candidate.timestamp
                        )

                    frame_path = output_dir / f"best_{i+1}_{candidate.timestamp:.2f}s.png"
                    cv2.imwrite(str(frame_path), frame)
                    candidate.frame_path = str(frame_path)

        finally:
            cap.release()

    def _save_composition_metadata(
        self,
        path: Path,
        result: CompositionResult,
        candidate: PhotoCandidate
    ):
        """구도 메타데이터 저장"""
        import json

        metadata = {
            "timestamp": candidate.timestamp,
            "overall_score": candidate.overall_score,
            "composition_type": result.composition_type,
            **result.metadata
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _save_photo_metadata(
        self,
        path: Path,
        candidate: PhotoCandidate,
        output_config: Optional[OutputConfig] = None
    ):
        """사진 메타데이터 저장"""
        import json

        metadata = {
            "timestamp": candidate.timestamp,
            "overall_score": candidate.overall_score,
            "aesthetic_score": candidate.aesthetic_score,
            "composition_score": candidate.composition_score,
            "emotional_impact": candidate.emotional_impact,
            "technical_quality": candidate.technical_quality,
        }

        if output_config:
            metadata["output"] = {
                "ratio": output_config.ratio,
                "width": output_config.width,
                "height": output_config.height
            }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _parse_ratio(self, ratio_str: str) -> Tuple[int, int]:
        """비율 문자열을 튜플로 파싱 (예: '9:16' -> (9, 16))"""
        try:
            parts = ratio_str.split(':')
            return (int(parts[0]), int(parts[1]))
        except Exception:
            return (16, 9)

    def _score_all_frames(
        self,
        frames: List[FrameAnalysis]
    ) -> List[PhotoCandidate]:
        """모든 프레임의 종합 점수 계산"""
        candidates = []

        for frame in frames:
            # 감정 임팩트 점수 계산
            emotional_impact = self._calculate_emotional_impact(frame)

            # 기술적 품질 점수 계산
            technical_quality = self._calculate_technical_quality(frame)

            # 종합 점수
            overall_score = (
                frame.aesthetic_score * self.weights.get("aesthetic_score", 0.3) +
                frame.composition_score * self.weights.get("composition_score", 0.25) +
                emotional_impact * self.weights.get("emotional_impact", 0.25) +
                technical_quality * self.weights.get("technical_quality", 0.2)
            )

            candidates.append(PhotoCandidate(
                timestamp=frame.timestamp,
                aesthetic_score=frame.aesthetic_score,
                composition_score=frame.composition_score,
                emotional_impact=emotional_impact,
                technical_quality=technical_quality,
                overall_score=overall_score
            ))

        return candidates

    def _calculate_emotional_impact(self, frame: FrameAnalysis) -> float:
        """감정 임팩트 점수 계산"""
        score = 0.5

        if frame.is_action_peak:
            score += 0.3

        high_impact_emotions = ["triumphant", "joyful", "determined", "struggling"]
        if frame.emotional_tone in high_impact_emotions:
            score += 0.2

        if frame.faces_detected > 0:
            score += 0.1

        return min(1.0, score)

    def _calculate_technical_quality(self, frame: FrameAnalysis) -> float:
        """기술적 품질 점수 계산"""
        score = 0.7

        if frame.lighting == "good":
            score += 0.2
        elif frame.lighting == "moderate":
            score += 0.1
        else:
            score -= 0.2

        if frame.motion_level > 0.8:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _select_with_diversity(
        self,
        candidates: List[PhotoCandidate],
        count: int,
        min_gap: float
    ) -> List[PhotoCandidate]:
        """다양성을 확보하며 상위 N개 선택 (기존 방식)"""
        sorted_candidates = sorted(
            candidates,
            key=lambda c: c.overall_score,
            reverse=True
        )

        selected = []

        for candidate in sorted_candidates:
            if len(selected) >= count:
                break

            is_diverse = all(
                abs(candidate.timestamp - s.timestamp) >= min_gap
                for s in selected
            )

            if is_diverse:
                selected.append(candidate)

        if len(selected) < count:
            selected_timestamps = {s.timestamp for s in selected}

            for candidate in sorted_candidates:
                if len(selected) >= count:
                    break
                if candidate.timestamp not in selected_timestamps:
                    selected.append(candidate)

        return sorted(selected, key=lambda c: c.timestamp)

    def _extract_frame_at_timestamp(
        self,
        video_path: str,
        timestamp: float
    ) -> Optional[np.ndarray]:
        """특정 타임스탬프의 프레임 추출"""
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            return None

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int(timestamp * fps)

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()

            if ret:
                return frame
            return None

        finally:
            cap.release()

    def extract_frames_batch(
        self,
        video_path: str,
        timestamps: List[float],
        output_dir: str
    ) -> List[str]:
        """여러 타임스탬프의 프레임을 배치로 추출"""
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise PhotoProcessingError(f"영상을 열 수 없습니다: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        saved_paths = []

        try:
            for ts in timestamps:
                frame_number = int(ts * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()

                if ret:
                    path = output_dir_path / f"frame_{ts:.2f}s.png"
                    cv2.imwrite(str(path), frame)
                    saved_paths.append(str(path))

        finally:
            cap.release()

        return saved_paths
