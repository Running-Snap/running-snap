"""
프롬프트 조립기 v3.0
새로운 스타일 시스템에 맞게 프롬프트 생성
"""
from typing import List

from ..core.config_loader import ConfigLoader
from ..core.models import VideoAnalysis, DurationType, FrameAnalysis


class PromptBuilder:
    """LLM 프롬프트 조립기"""

    def __init__(self, config_loader: ConfigLoader):
        self.config = config_loader

    def build(
        self,
        video_analysis: VideoAnalysis,
        target_duration: float,
        style_name: str
    ) -> str:
        """
        최종 프롬프트 생성

        Args:
            video_analysis: 영상 분석 결과
            target_duration: 목표 출력 길이
            style_name: 편집 스타일 이름

        Returns:
            완성된 프롬프트 문자열
        """
        duration_type = DurationType.from_duration(target_duration)

        # 기본 프롬프트 로드 (system_prompt + style_prompt + allowed)
        base_prompt = self.config.get_script_prompt(duration_type, style_name)

        # 분석 결과를 프롬프트용으로 포맷
        analysis_text = self._format_analysis_for_prompt(video_analysis)

        # 스타일 정보
        style = self.config.get_style(style_name)

        # 최종 프롬프트 조립
        full_prompt = f"""{base_prompt}

---

## 영상 분석 데이터

{analysis_text}

---

## 작업 지시

위 분석 데이터를 바탕으로 약 {target_duration}초 이하의 {style.get('name', style_name)} 스타일 편집 대본을 생성해라.

중요:
1. source_start/source_end는 반드시 원본 영상 범위 내 (0 ~ {video_analysis.duration:.1f}초)
2. 하이라이트 순간들을 최대한 활용할 것: {video_analysis.highlights}
3. 목표 길이는 "약 {target_duration}초"이지 정확히 맞출 필요 없음
4. JSON만 출력하고 다른 텍스트는 포함하지 말 것
"""

        return full_prompt

    def _format_analysis_for_prompt(self, analysis: VideoAnalysis) -> str:
        """분석 결과를 프롬프트에 포함할 형태로 포맷"""

        # 기본 정보
        info_parts = [
            f"### 기본 정보",
            f"- 원본 길이: {analysis.duration:.1f}초",
            f"- 해상도: {analysis.resolution[0]}x{analysis.resolution[1]}",
            f"- FPS: {analysis.fps}",
            f"- 전체 움직임 수준: {analysis.overall_motion}",
            f"- 주요 조명: {analysis.dominant_lighting}",
            f"- 하이라이트 타임스탬프: {analysis.highlights}",
            ""
        ]

        # 프레임별 분석 요약 (너무 길면 요약)
        info_parts.append("### 프레임별 분석")

        # 최대 15개 프레임만 포함 (토큰 절약)
        frames_to_include = analysis.frames
        if len(frames_to_include) > 15:
            # 균등하게 샘플링
            step = len(frames_to_include) // 15
            frames_to_include = frames_to_include[::step][:15]

        for frame in frames_to_include:
            frame_info = self._format_frame_summary(frame)
            info_parts.append(frame_info)

        # 스토리 비트 (있는 경우)
        if analysis.story_beats:
            info_parts.append("")
            info_parts.append("### 스토리 구조")
            for section, data in analysis.story_beats.items():
                info_parts.append(
                    f"- {section} ({data['start']:.1f}s-{data['end']:.1f}s): "
                    f"motion={data['avg_motion']:.2f}, emotion={data['dominant_emotion']}, "
                    f"peak={'있음' if data['has_peak'] else '없음'}"
                )

        return "\n".join(info_parts)

    def _format_frame_summary(self, frame: FrameAnalysis) -> str:
        """단일 프레임 요약"""
        peak_marker = "⭐" if frame.is_action_peak else ""
        return (
            f"- [{frame.timestamp:.1f}s]{peak_marker} "
            f"motion={frame.motion_level:.2f}, "
            f"aesthetic={frame.aesthetic_score:.2f}, "
            f"emotion={frame.emotional_tone}, "
            f"faces={frame.faces_detected}"
        )

    def build_simple(
        self,
        video_duration: float,
        target_duration: float,
        style_name: str,
        highlights: List[float]
    ) -> str:
        """
        간단한 프롬프트 생성 (분석 결과 없이)
        테스트용 또는 빠른 처리용
        """
        duration_type = DurationType.from_duration(target_duration)
        base_prompt = self.config.get_script_prompt(duration_type, style_name)

        return f"""{base_prompt}

---

## 영상 정보
- 원본 길이: {video_duration}초
- 목표 길이: {target_duration}초
- 하이라이트: {highlights}

JSON만 출력해라.
"""
