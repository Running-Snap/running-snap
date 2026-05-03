"""
video_editor.py
===============
VideoEditor — 공개 API 진입점.

사용:
    from src.video_editor import VideoEditor

    result = VideoEditor().edit(
        video_path = "/path/to/video.mp4",
        duration   = 30.0,
        style      = "instagram",          # action / instagram / tiktok / humor / documentary
        feedback_data = {...},             # 선택: LLM 피드백 JSON
        with_skeleton = True,             # 선택: MediaPipe 스켈레톤 오버레이
        output_dir = "outputs/videos",
    )

    if result.success:
        print(result.video_path)
    else:
        print(result.error)
"""
from __future__ import annotations

import os
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .preprocessor      import preprocess, VideoInfo
from .instruction_builder import InstructionBuilder
from .template_executor  import TemplateExecutor


VALID_STYLES = {"action", "instagram", "tiktok", "humor", "documentary"}


# ════════════════════════════════════════════════════════════════════
# 결과 객체
# ════════════════════════════════════════════════════════════════════

@dataclass
class VideoEditResult:
    success:    bool
    video_path: str = ""
    error:      str = ""

    # 부가 정보 (성공 시)
    duration_sec:  float = 0.0
    file_size_mb:  float = 0.0
    style:         str   = ""
    template_id:   str   = ""


# ════════════════════════════════════════════════════════════════════
# 메인 클래스
# ════════════════════════════════════════════════════════════════════

class VideoEditor:
    """
    영상 자동 편집기.

    Args:
        verbose: 상세 로그 출력 여부 (기본 True)
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def edit(
        self,
        video_path:    str,
        duration:      float,
        style:         str,
        feedback_data: Optional[Dict[str, Any]] = None,
        with_skeleton: bool = False,
        output_dir:    str  = "outputs/videos",
        output_name:   Optional[str] = None,
    ) -> VideoEditResult:
        """
        영상 편집 실행.

        Args:
            video_path:    원본 영상 로컬 경로
            duration:      목표 출력 길이 (초)
            style:         편집 스타일
                           "action" / "instagram" / "tiktok" / "humor" / "documentary"
            feedback_data: LLM 자세분석 피드백 JSON (선택)
                           {"score":, "feedbacks":[], "pose_stats":{}}
            with_skeleton: MediaPipe 스켈레톤 오버레이 적용 여부 (선택)
            output_dir:    출력 디렉터리 (기본 "outputs/videos")
            output_name:   출력 파일 이름 (기본: {style}_{timestamp}.mp4)

        Returns:
            VideoEditResult
        """
        # ── 입력 검증 ────────────────────────────────────────────────
        validation_error = self._validate(video_path, duration, style)
        if validation_error:
            return VideoEditResult(success=False, error=validation_error)

        # ── 출력 경로 설정 ───────────────────────────────────────────
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = output_name or f"{style}_{ts}.mp4"
        out_path = str(Path(output_dir) / name)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = self._run(
                    video_path, duration, style,
                    feedback_data, with_skeleton,
                    out_path, tmpdir,
                )
            return result

        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if self.verbose:
                traceback.print_exc()
            return VideoEditResult(success=False, error=msg)

    # ════════════════════════════════════════════════════════════════
    # 내부 파이프라인
    # ════════════════════════════════════════════════════════════════

    def _run(
        self,
        video_path: str,
        duration: float,
        style: str,
        feedback_data: Optional[Dict],
        with_skeleton: bool,
        out_path: str,
        tmpdir: str,
    ) -> VideoEditResult:

        self._log(f"\n{'='*56}")
        self._log(f"  VideoEditor.edit()")
        self._log(f"  style={style}  duration={duration}s")
        self._log(f"  source={video_path}")
        self._log(f"{'='*56}")

        # ── Step 1: 전처리 (rotation fix + loop) ────────────────────
        self._log("\n[1/4] 전처리...")
        info = preprocess(video_path, duration, tmpdir)
        src_for_template = info.path

        # ── Step 2: 스켈레톤 (선택) ──────────────────────────────────
        if with_skeleton and feedback_data:
            self._log("\n[2/4] MediaPipe 스켈레톤...")
            skel_path = self._apply_skeleton(info, feedback_data, tmpdir)
            if skel_path:
                src_for_template = skel_path
            else:
                self._log("  [경고] 스켈레톤 적용 실패, 원본 사용")
        else:
            self._log("\n[2/4] 스켈레톤 건너뜀")

        # ── Step 3: EditInstruction 생성 ────────────────────────────
        self._log("\n[3/4] Instruction 생성...")
        builder = InstructionBuilder(style=style)
        instruction = builder.build(
            source_info=info,
            target_duration=duration,
            feedback_data=feedback_data,
        )
        total_dur = instruction["meta"]["target_duration_seconds"]
        n_seg = len(instruction["timeline"]["segments"])
        n_ov  = len(instruction["overlays"])
        self._log(f"  세그먼트 {n_seg}개  오버레이 {n_ov}개  → {total_dur:.1f}s")

        # ── Step 4: 렌더링 ───────────────────────────────────────────
        self._log("\n[4/4] 렌더링...")
        executor = TemplateExecutor(verbose=self.verbose)
        executor.execute(instruction, src_for_template, out_path)

        if not Path(out_path).exists():
            return VideoEditResult(success=False, error="렌더링 후 파일이 존재하지 않음")

        size_mb = Path(out_path).stat().st_size / 1024 / 1024
        self._log(f"\n완료: {out_path} ({size_mb:.1f} MB)")

        return VideoEditResult(
            success=True,
            video_path=out_path,
            duration_sec=total_dur,
            file_size_mb=round(size_mb, 2),
            style=style,
            template_id=instruction.get("template_id", ""),
        )

    def _apply_skeleton(
        self,
        info: VideoInfo,
        feedback_data: Dict,
        tmpdir: str,
    ) -> Optional[str]:
        try:
            from .pose_skeleton_renderer import apply_skeleton_feedback
            skel_path = os.path.join(tmpdir, "loop_skel.mp4")
            ok = apply_skeleton_feedback(
                info.path, skel_path, feedback_data,
                loop_count=info.loop_count,
                model_path="models/pose_landmarker_full.task",
            )
            return skel_path if ok and Path(skel_path).exists() else None
        except Exception as e:
            self._log(f"  [오류] 스켈레톤: {e}")
            return None

    # ════════════════════════════════════════════════════════════════
    # 유틸
    # ════════════════════════════════════════════════════════════════

    def _validate(self, video_path: str, duration: float, style: str) -> str:
        """오류 메시지 반환 (없으면 빈 문자열)"""
        if not os.path.exists(video_path):
            return f"영상 파일 없음: {video_path}"
        if duration <= 0:
            return f"duration은 양수여야 합니다: {duration}"
        if style.lower() not in VALID_STYLES:
            return (
                f"지원하지 않는 스타일: '{style}'. "
                f"가능: {sorted(VALID_STYLES)}"
            )
        return ""

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)
