"""
running_pipeline.py
===================
러닝 영상 통합 파이프라인.

단일 소스 영상에서 3가지 출력물을 생성:
  1. 베스트컷 포스터   (JPG) — event_config 기반 PIL 합성
  2. 인증영상          (MP4) — Nike 스타일 km/시간 카운터
  3. 자세분석 영상     (MP4) — skeleton overlay + feedback 카드
     (feedback_data가 없으면 생략)

Qwen VLM 분석을 통해 사용자가 실제 등장하는 구간만 사용.
API key 없을 경우 자동으로 비례 분배 방식으로 fallback.

사용:
    from src.running_pipeline import RunningPipeline, RunResult

    result = RunningPipeline(qwen_api_key="sk-...").run(
        video_path   = "/path/to/video.mp4",
        event_config = {
            "title":        "BLOSSOM\\nRUNNING",
            "location":     "Chungnam National Univ.",
            "sublocation":  "N9-2",
            "time":         "P.M. 03:00",
            "date":         "2026.04.03",
            "distance_km":  5.2,
            "run_time":     "34'18\\"",
            "pace":         "6'35\\"/km",
            "color_scheme": "warm",
        },
        feedback_data = { ... },   # 없으면 자세분석 건너뜀
        output_dir    = "outputs",
    )
    print(result.poster_path)
    print(result.cert_path)
    print(result.pose_path)
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .preprocessor       import preprocess, VideoInfo
from .template_executor  import TemplateExecutor
from .instruction_builder import InstructionBuilder
from .poster_maker       import PosterMaker, find_best_poster_frame
from .cert_builder       import CertBuilder
from .event_cert_builder import EventCertBuilder


# ════════════════════════════════════════════════════════════════════
# 결과 객체
# ════════════════════════════════════════════════════════════════════

@dataclass
class RunResult:
    success:     bool
    poster_path: str = ""
    cert_path:   str = ""
    pose_path:   str = ""   # feedback_data 없으면 빈 문자열
    error:       str = ""
    highlights:  List[float] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# 파이프라인
# ════════════════════════════════════════════════════════════════════

class RunningPipeline:
    """
    러닝 영상 통합 파이프라인.

    Args:
        qwen_api_key: DashScope API 키 (없으면 Qwen 분석 건너뜀)
        verbose:      로그 출력 여부
    """

    def __init__(self, qwen_api_key: Optional[str] = None, verbose: bool = True):
        self.api_key = qwen_api_key
        self.verbose = verbose
        # API 키 없으면 Ollama 로컬 모드로 자동 전환
        if not qwen_api_key and verbose:
            print("  [분석] DashScope API 키 없음 → Ollama qwen2.5vl:7b 자동 시도")

    def run(
        self,
        video_path:    str,
        event_config:  Dict[str, Any],
        feedback_data: Optional[Dict[str, Any]] = None,
        output_dir:    str = "outputs",
        name_prefix:   str = "",
        cert_mode:     str = "full",   # "full" = slowmo+zoom / "simple" = 원본 1x 그대로
    ) -> RunResult:
        """
        영상 파이프라인 실행.

        Args:
            video_path:    원본 영상 경로
            event_config:  포스터/인증영상 이벤트 정보 (title, location, date, ...)
            feedback_data: 자세분석 JSON (없으면 pose 영상 생략)
            output_dir:    출력 디렉터리 루트
            name_prefix:   파일명 접두사 (기본: "run")
            cert_mode:     "full"   → intro+slowmo+zoom 포함 인증영상
                           "simple" → 슬로우모·줌 없이 원본 1x 재생
        """
        if not os.path.exists(video_path):
            return RunResult(success=False, error=f"영상 없음: {video_path}")

        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = name_prefix or "run"
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                return self._run(
                    video_path, event_config, feedback_data,
                    output_dir, prefix, ts, tmpdir, cert_mode,
                )
        except Exception as e:
            if self.verbose:
                traceback.print_exc()
            return RunResult(success=False, error=f"{type(e).__name__}: {e}")

    # ── 내부 파이프라인 ───────────────────────────────────────────

    def _run(
        self,
        video_path: str,
        event_config: Dict[str, Any],
        feedback_data: Optional[Dict],
        output_dir: str,
        prefix: str,
        ts: str,
        tmpdir: str,
        cert_mode: str = "full",
    ) -> RunResult:

        self._log(f"\n{'='*60}")
        self._log(f"  RunningPipeline")
        self._log(f"  source: {video_path}")
        self._log(f"{'='*60}")

        # ── Step 1: 전처리 ───────────────────────────────────────────
        self._log("\n[1/5] 전처리 (rotation fix + loop)...")
        n_feedbacks = len(feedback_data.get("feedbacks", [])) if feedback_data else 0
        target_dur  = self._estimate_target_duration(event_config, n_feedbacks)
        info = preprocess(video_path, target_duration=target_dur, tmpdir=tmpdir)
        self._log(f"  {info.width}x{info.height}  {info.duration:.1f}s  (루프 {info.loop_count}x)")

        # ── Step 2: Qwen 분석 → highlights ───────────────────────────
        self._log("\n[2/5] Qwen 분석...")
        # 캐시 키는 원본 영상 경로 기준 (temp loop.mp4가 아닌 원본)
        highlights = self._analyze(video_path, target_dur)
        if highlights:
            self._log(f"  highlights: {[f'{h:.2f}s' for h in highlights]}")
        else:
            self._log("  Qwen 분석 건너뜀 → 비례 분배 사용")

        # 포스터용 베스트 프레임 선택 (중앙 위치 + 1/3 크기 조건)
        self._log("\n[3/5] 포스터 베스트 프레임 선택 (중앙 위치 + 화면 1/3 크기)...")
        poster_time = self._pick_poster_frame(highlights, info)

        result = RunResult(success=True, highlights=highlights)

        # ── Step 3: 베스트컷 포스터 ──────────────────────────────────
        self._log(f"  선택된 프레임: {poster_time:.2f}s")
        poster_path = os.path.join(output_dir, f"{prefix}_poster_{ts}.jpg")
        made = PosterMaker().make(
            video_path   = info.path,
            frame_time   = poster_time,
            event_config = event_config,
            output_path  = poster_path,
            color_grade  = True,    # 색보정 적용 (밝기/대비/채도 보정으로 더 선명하게)
        )
        result.poster_path = made or ""

        # ── Step 4: 인증영상 ──────────────────────────────────────────
        mode_label = "simple (슬로우모·줌 없음)" if cert_mode == "simple" else "full (slowmo+zoom)"
        self._log(f"\n[4/5] 인증영상 ({mode_label})...")
        cert_path = os.path.join(output_dir, f"{prefix}_cert_{ts}.mp4")
        self._make_cert(info, event_config, highlights, cert_path, cert_mode)
        result.cert_path = cert_path if Path(cert_path).exists() else ""

        # ── Step 5: 자세분석 영상 ─────────────────────────────────────
        if feedback_data:
            self._log("\n[5/5] 자세분석 영상 (skeleton + feedback)...")
            pose_path = os.path.join(output_dir, f"{prefix}_pose_{ts}.mp4")
            self._make_pose(info, feedback_data, highlights, pose_path, tmpdir)
            result.pose_path = pose_path if Path(pose_path).exists() else ""
        else:
            self._log("\n[5/5] 자세분석 건너뜀 (feedback_data 없음)")

        self._log(f"\n{'='*60}")
        self._log(f"  완료!")
        if result.poster_path: self._log(f"  포스터: {result.poster_path}")
        if result.cert_path:   self._log(f"  인증영상: {result.cert_path}")
        if result.pose_path:   self._log(f"  자세분석: {result.pose_path}")
        self._log(f"{'='*60}")

        return result

    # ── Qwen 분석 ─────────────────────────────────────────────────

    def _analyze(self, video_path: str, target_dur: float) -> List[float]:
        """
        영상 하이라이트 타임스탬프 추출.

        우선순위:
          0. 캐시 히트 (이전 분석 결과 재사용)
          1. DashScope API (qwen_api_key 제공 시)
          2. Ollama 로컬 qwen2.5vl:7b (API 없을 때 자동 시도)
          3. 빈 배열 fallback (Ollama도 없으면)
        """
        try:
            from .analyzers.frame_analyzer import FrameAnalyzer, OllamaFrameAnalyzer
            from .analyzers.video_analyzer import VideoAnalyzer
            from .core.config_loader import ConfigLoader
            from .core.analysis_cache import AnalysisCache

            cache = AnalysisCache()

            # ── 캐시 확인 ──────────────────────────────────────────
            cached = cache.load_analysis(video_path)
            if cached:
                self._log(f"  [캐시] 이전 분석 재사용 → 하이라이트 {len(cached.highlights)}개")
                return cached.highlights

            config = ConfigLoader()

            if self.api_key:
                self._log("  Qwen API (DashScope) 사용")
                frame_analyzer = FrameAnalyzer(self.api_key)
                max_concurrent = 5
            else:
                import urllib.request
                try:
                    urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
                    self._log("  Ollama 로컬 qwen2.5vl:7b 사용")
                    frame_analyzer = OllamaFrameAnalyzer(model="qwen2.5vl:7b")
                    max_concurrent = 1   # Ollama는 순차 처리
                except Exception:
                    self._log("  [경고] Ollama 미응답 → 비례 분배 fallback")
                    return []

            analyzer = VideoAnalyzer(
                config_loader  = config,
                frame_analyzer = frame_analyzer,
            )
            analysis = asyncio.run(
                analyzer.analyze(video_path, target_duration=target_dur,
                                 max_frames=3, show_progress=False,
                                 max_concurrent=max_concurrent)
            )
            self._log(f"  하이라이트 {len(analysis.highlights)}개 추출 완료")

            # ── 결과 캐시 저장 ─────────────────────────────────────
            cache.save_analysis(video_path, analysis)
            self._log(f"  [캐시] 분석 결과 저장 → 다음 실행 시 재사용")

            return analysis.highlights
        except Exception as e:
            self._log(f"  [경고] Qwen 분석 실패: {e}")
            return []

    # ── 포스터 프레임 선택 ────────────────────────────────────────

    def _pick_poster_frame(self, highlights: List[float], info: VideoInfo) -> float:
        """
        후보 프레임 중 러너가 크고 중앙에 잘 나온 프레임 선택.
        MediaPipe → HOG 순으로 시도, 둘 다 없으면 중간 프레임.
        """
        orig = info.original_duration or info.duration

        # 후보 시각 목록: 15개로 늘려서 더 촘촘하게 탐색
        if highlights:
            candidates = highlights[:]
        else:
            n = 15
            candidates = [round(orig * (0.05 + i * 0.90 / (n - 1)), 2) for i in range(n)]

        _model_candidates = [
            str(Path(__file__).parents[2] / "backend" / "pose_landmarker_heavy.task"),
            "/home/ubuntu/backend/pose_landmarker_heavy.task",
            "models/pose_landmarker_full.task",
        ]
        _model_path = next((p for p in _model_candidates if Path(p).exists()), "models/pose_landmarker_full.task")

        return find_best_poster_frame(
            video_path     = info.path,
            candidate_times    = candidates,
            model_path         = _model_path,
            target_size_ratio  = 0.65,   # 포스터: 러너가 화면의 65% 차지가 이상적
            verbose            = self.verbose,
        )

    # ── 인증영상 ─────────────────────────────────────────────────

    def _make_cert(
        self,
        info: VideoInfo,
        event_config: Dict,
        highlights: List[float],
        out_path: str,
        cert_mode: str = "full",
    ) -> None:
        orig = info.original_duration or info.duration
        if cert_mode == "event":
            # 이벤트 스타일 — 통계 없이 이벤트명/날짜/시간/장소만 표시
            instruction = EventCertBuilder.build(orig, event_config)
        elif cert_mode == "simple":
            instruction = CertBuilder.build_simple(orig, event_config)
        else:
            instruction = CertBuilder.build_full(info, event_config, highlights)
        executor = TemplateExecutor(verbose=self.verbose)
        executor.execute(instruction, info.path, out_path)

    # ── 자세분석 영상 ─────────────────────────────────────────────

    def _make_pose(
        self,
        info: VideoInfo,
        feedback_data: Dict,
        highlights: List[float],
        out_path: str,
        tmpdir: str,
    ) -> None:
        skel_path = os.path.join(tmpdir, "skel.mp4")

        _pose_model_candidates = [
            str(Path(__file__).parents[2] / "backend" / "pose_landmarker_heavy.task"),
            "/home/ubuntu/backend/pose_landmarker_heavy.task",
            "models/pose_landmarker_full.task",
        ]
        _pose_model_path = next((p for p in _pose_model_candidates if Path(p).exists()), "models/pose_landmarker_full.task")

        # skeleton overlay
        try:
            from .pose_skeleton_renderer import apply_skeleton_feedback
            ok = apply_skeleton_feedback(
                source_video  = info.path,
                output_video  = skel_path,
                feedback_data = feedback_data,
                loop_count    = info.loop_count,
                model_path    = _pose_model_path,
                highlights    = highlights or None,
            )
            if not ok or not Path(skel_path).exists():
                self._log("  [경고] skeleton 실패 → 원본으로 진행")
                skel_path = info.path
        except Exception as e:
            self._log(f"  [경고] skeleton 오류: {e}")
            skel_path = info.path

        # instruction (feedback 기반)
        builder = InstructionBuilder(style="action")
        instruction = builder.build(
            source_info    = info,
            target_duration= info.duration,
            feedback_data  = feedback_data,
            highlights     = highlights or None,
        )

        executor = TemplateExecutor(verbose=self.verbose)
        executor.execute(instruction, skel_path, out_path)

    # ── 유틸 ──────────────────────────────────────────────────────

    def _estimate_target_duration(self, event_config: Dict, n_feedbacks: int) -> float:
        """출력 목표 길이 추정."""
        if n_feedbacks > 0:
            return 6.0 + n_feedbacks * 3.5   # 피드백마다 약 3.5초
        return 12.0   # 인증영상 기본

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)
