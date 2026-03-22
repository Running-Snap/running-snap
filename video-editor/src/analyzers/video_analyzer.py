"""
전체 영상 분석 오케스트레이터
설정에 따라 프레임을 샘플링하고 분석 결과를 집계
"""
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
import cv2
from rich.progress import Progress
from rich.console import Console

from ..core.config_loader import ConfigLoader
from ..core.models import (
    FrameAnalysis,
    VideoAnalysis,
    DurationType
)
from ..core.exceptions import AnalysisError
from .frame_analyzer import FrameAnalyzer


class VideoAnalyzer:
    """전체 영상 분석 오케스트레이터"""

    def __init__(
        self,
        config_loader: ConfigLoader,
        frame_analyzer: FrameAnalyzer,
        console: Optional[Console] = None
    ):
        """
        Args:
            config_loader: 설정 로더
            frame_analyzer: 프레임 분석기 인스턴스
            console: Rich 콘솔 (로깅용)
        """
        self.config = config_loader
        self.frame_analyzer = frame_analyzer
        self.console = console or Console()

    async def analyze(
        self,
        video_path: str,
        target_duration: float,
        max_concurrent: int = 5,
        show_progress: bool = True,
        max_frames: int = 0
    ) -> VideoAnalysis:
        """
        전체 영상 분석

        Args:
            video_path: 입력 영상 경로
            target_duration: 목표 출력 길이 (분석 프로파일 선택에 사용)
            max_concurrent: 동시 분석 프레임 수
            show_progress: 진행률 표시 여부
            max_frames: 최대 분석 프레임 수 (0이면 제한 없음)

        Returns:
            VideoAnalysis 객체
        """
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            raise AnalysisError(f"영상 파일이 없습니다: {video_path}")

        # 1. 영상 메타데이터 추출
        metadata = self._get_video_metadata(str(video_path_obj))

        # 2. 분석 프로파일 선택 (target_duration 기준)
        duration_type = DurationType.from_duration(target_duration)
        profile = self.config.get_analysis_profile(duration_type)

        self.console.print(f"[cyan]분석 프로파일: {duration_type.value}[/cyan]")
        self.console.print(f"[dim]영상 길이: {metadata['duration']:.1f}초, FPS: {metadata['fps']}[/dim]")

        # 3. 프레임 샘플링
        sample_rate = profile.get("frame_sample_rate", 1)
        frames_data = self._extract_frames(str(video_path_obj), sample_rate)

        # max_frames가 설정되어 있으면 균일하게 샘플링
        if max_frames > 0 and len(frames_data) > max_frames:
            step = len(frames_data) // max_frames
            frames_data = frames_data[::step][:max_frames]
            self.console.print(f"[yellow]프레임 수 제한: {max_frames}개로 샘플링[/yellow]")

        self.console.print(f"[dim]분석할 프레임 수: {len(frames_data)}개[/dim]")

        # 4. 프레임 분석 (병렬)
        analysis_prompt = profile.get("analysis_prompt", "")
        frame_analyses = await self._analyze_frames_parallel(
            frames_data,
            analysis_prompt,
            max_concurrent,
            show_progress
        )

        # 5. 결과 집계
        highlights = self._identify_highlights(frame_analyses)
        overall_motion = self._calculate_overall_motion(frame_analyses)
        dominant_lighting = self._get_dominant_lighting(frame_analyses)
        story_beats = self._analyze_story_beats(frame_analyses, duration_type)
        summary = self._generate_summary(frame_analyses, profile)

        return VideoAnalysis(
            source_path=str(video_path_obj),
            duration=metadata["duration"],
            fps=metadata["fps"],
            resolution=metadata["resolution"],
            duration_type=duration_type,
            frames=frame_analyses,
            highlights=highlights,
            story_beats=story_beats,
            overall_motion=overall_motion,
            dominant_lighting=dominant_lighting,
            summary=summary
        )

    def _get_video_metadata(self, video_path: str) -> dict:
        """영상 메타데이터 추출"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise AnalysisError(f"영상을 열 수 없습니다: {video_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0

            return {
                "duration": duration,
                "fps": fps,
                "frame_count": frame_count,
                "resolution": (width, height)
            }
        finally:
            cap.release()

    def _extract_frames(
        self,
        video_path: str,
        sample_rate: float
    ) -> List[Tuple[float, np.ndarray]]:
        """
        지정된 샘플 레이트로 프레임 추출

        Args:
            video_path: 영상 경로
            sample_rate: 초당 추출할 프레임 수

        Returns:
            [(timestamp, frame), ...] 리스트
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise AnalysisError(f"영상을 열 수 없습니다: {video_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps

            # 샘플링 간격 계산
            interval_seconds = 1.0 / sample_rate

            frames_data = []
            current_time = 0.0

            while current_time < duration:
                # 해당 타임스탬프의 프레임으로 이동
                frame_number = int(current_time * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

                ret, frame = cap.read()
                if not ret:
                    break

                frames_data.append((current_time, frame.copy()))
                current_time += interval_seconds

            return frames_data

        finally:
            cap.release()

    async def _analyze_frames_parallel(
        self,
        frames_data: List[Tuple[float, np.ndarray]],
        analysis_prompt: str,
        max_concurrent: int,
        show_progress: bool
    ) -> List[FrameAnalysis]:
        """프레임들을 병렬로 분석"""
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[FrameAnalysis] = []

        async def analyze_with_semaphore(timestamp: float, frame: np.ndarray) -> FrameAnalysis:
            async with semaphore:
                return await self.frame_analyzer.analyze_frame(
                    frame, timestamp, analysis_prompt
                )

        if show_progress:
            with Progress() as progress:
                task = progress.add_task(
                    "[cyan]프레임 분석 중...",
                    total=len(frames_data)
                )

                tasks = []
                for timestamp, frame in frames_data:
                    tasks.append(analyze_with_semaphore(timestamp, frame))

                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    progress.advance(task)
        else:
            tasks = [
                analyze_with_semaphore(ts, frame)
                for ts, frame in frames_data
            ]
            results = await asyncio.gather(*tasks)

        # 타임스탬프 순으로 정렬
        results.sort(key=lambda x: x.timestamp)
        return results

    def _identify_highlights(
        self,
        frames: List[FrameAnalysis],
        top_n: int = 5
    ) -> List[float]:
        """
        하이라이트 순간 식별
        - action_peak이 True인 프레임
        - aesthetic_score가 높은 프레임
        - motion_level이 높은 프레임
        """
        # 점수 계산
        scored_frames = []
        for frame in frames:
            score = 0.0
            if frame.is_action_peak:
                score += 0.4
            score += frame.aesthetic_score * 0.3
            score += frame.motion_level * 0.2
            score += frame.composition_score * 0.1

            scored_frames.append((frame.timestamp, score))

        # 상위 N개 선택 (최소 간격 유지)
        scored_frames.sort(key=lambda x: x[1], reverse=True)

        highlights = []
        min_gap = 1.0  # 최소 1초 간격

        for timestamp, score in scored_frames:
            if len(highlights) >= top_n:
                break

            # 기존 하이라이트와 충분한 간격이 있는지 확인
            is_far_enough = all(
                abs(timestamp - h) >= min_gap for h in highlights
            )
            if is_far_enough:
                highlights.append(timestamp)

        return sorted(highlights)

    def _calculate_overall_motion(self, frames: List[FrameAnalysis]) -> str:
        """전체 영상의 평균 움직임 수준"""
        if not frames:
            return "unknown"

        avg_motion = sum(f.motion_level for f in frames) / len(frames)

        if avg_motion < 0.3:
            return "low"
        elif avg_motion < 0.6:
            return "medium"
        else:
            return "high"

    def _get_dominant_lighting(self, frames: List[FrameAnalysis]) -> str:
        """가장 빈번한 조명 상태"""
        if not frames:
            return "unknown"

        lighting_counts: dict = {}
        for frame in frames:
            lighting_counts[frame.lighting] = lighting_counts.get(frame.lighting, 0) + 1

        return max(lighting_counts, key=lighting_counts.get)

    def _analyze_story_beats(
        self,
        frames: List[FrameAnalysis],
        duration_type: DurationType
    ) -> Optional[dict]:
        """스토리 비트 분석 (medium/long 영상용)"""
        if duration_type == DurationType.SHORT or not frames:
            return None

        # 영상을 구간별로 나누어 분석
        total_duration = frames[-1].timestamp if frames else 0

        if duration_type == DurationType.MEDIUM:
            # 5구간: hook, setup, confrontation, climax, resolution
            sections = ["hook", "setup", "confrontation", "climax", "resolution"]
            section_ranges = [0.1, 0.3, 0.6, 0.9, 1.0]
        else:
            # 3막: act1, act2, act3
            sections = ["act1", "act2", "act3"]
            section_ranges = [0.25, 0.75, 1.0]

        story_beats = {}
        prev_end = 0.0

        for section_name, end_ratio in zip(sections, section_ranges):
            start_time = prev_end * total_duration
            end_time = end_ratio * total_duration

            section_frames = [
                f for f in frames
                if start_time <= f.timestamp < end_time
            ]

            if section_frames:
                avg_motion = sum(f.motion_level for f in section_frames) / len(section_frames)
                avg_aesthetic = sum(f.aesthetic_score for f in section_frames) / len(section_frames)
                dominant_emotion = self._get_dominant_emotion(section_frames)

                story_beats[section_name] = {
                    "start": start_time,
                    "end": end_time,
                    "avg_motion": avg_motion,
                    "avg_aesthetic": avg_aesthetic,
                    "dominant_emotion": dominant_emotion,
                    "has_peak": any(f.is_action_peak for f in section_frames)
                }

            prev_end = end_ratio

        return story_beats

    def _get_dominant_emotion(self, frames: List[FrameAnalysis]) -> str:
        """프레임들에서 가장 빈번한 감정"""
        if not frames:
            return "neutral"

        emotion_counts: dict = {}
        for frame in frames:
            if frame.emotional_tone:
                emotion_counts[frame.emotional_tone] = emotion_counts.get(frame.emotional_tone, 0) + 1

        if not emotion_counts:
            return "neutral"

        return max(emotion_counts, key=emotion_counts.get)

    def _generate_summary(
        self,
        frames: List[FrameAnalysis],
        profile: dict
    ) -> str:
        """분석 결과 요약 생성"""
        if not frames:
            return "분석된 프레임이 없습니다."

        total_frames = len(frames)
        action_peaks = sum(1 for f in frames if f.is_action_peak)
        avg_aesthetic = sum(f.aesthetic_score for f in frames) / total_frames
        avg_motion = sum(f.motion_level for f in frames) / total_frames

        faces_detected = sum(1 for f in frames if f.faces_detected > 0)
        face_ratio = faces_detected / total_frames

        summary_parts = [
            f"총 {total_frames}개 프레임 분석 완료.",
            f"액션 피크: {action_peaks}개 발견.",
            f"평균 미학 점수: {avg_aesthetic:.2f}",
            f"평균 움직임: {avg_motion:.2f}",
            f"얼굴 감지 비율: {face_ratio:.0%}"
        ]

        if avg_motion > 0.6:
            summary_parts.append("전반적으로 역동적인 영상.")
        elif avg_motion < 0.3:
            summary_parts.append("전반적으로 정적인 영상.")

        return " ".join(summary_parts)
