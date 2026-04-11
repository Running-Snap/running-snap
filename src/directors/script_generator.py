"""
LLM 대본 생성기
Claude API 또는 Claude Code CLI를 사용해 편집 대본 생성
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from rich.console import Console

from ..core.config_loader import ConfigLoader
from ..core.models import (
    VideoAnalysis,
    EditScript,
    EditSegment,
)
from ..core.exceptions import ScriptGenerationError, APIError
from .prompt_builder import PromptBuilder


class ClaudeCodeScriptGenerator:
    """Claude Code CLI를 사용한 편집 대본 생성기 (API 키 불필요)"""

    def __init__(
        self,
        config_loader: ConfigLoader,
        console: Optional[Console] = None
    ):
        """
        Args:
            config_loader: 설정 로더
            console: Rich 콘솔
        """
        self.config = config_loader
        self.console = console or Console()
        self.prompt_builder = PromptBuilder(config_loader)
        self.last_prompt = ""  # 마지막 사용된 프롬프트 (디버깅/캐시용)

    async def generate(
        self,
        video_analysis: VideoAnalysis,
        target_duration: float,
        style: str,
        max_retries: int = 2
    ) -> EditScript:
        """
        편집 대본 생성 (Claude Code CLI 사용)

        Args:
            video_analysis: 영상 분석 결과
            target_duration: 목표 출력 길이 (초)
            style: 편집 스타일 이름
            max_retries: 생성 실패 시 재시도 횟수

        Returns:
            EditScript 객체
        """
        prompt = self.prompt_builder.build(
            video_analysis=video_analysis,
            target_duration=target_duration,
            style_name=style
        )

        # 프롬프트 저장 (캐시/디버깅용)
        self.last_prompt = prompt

        self.console.print(f"[dim]대본 생성 중... (Claude Code CLI, 스타일: {style})[/dim]")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Claude Code CLI 호출
                response_text = self._call_claude_cli(prompt)

                # JSON 파싱
                script_data = self._parse_response(response_text)

                # EditScript 객체 생성
                script = self._create_script(script_data, style)

                # 유효성 검증
                script = self._validate_script(
                    script,
                    video_analysis.duration,
                    target_duration
                )

                self.console.print(f"[green]✓ 대본 생성 완료 ({len(script.segments)}개 세그먼트)[/green]")
                return script

            except json.JSONDecodeError as e:
                last_error = e
                self.console.print(f"[yellow]JSON 파싱 실패, 재시도 {attempt + 1}/{max_retries + 1}[/yellow]")
            except subprocess.CalledProcessError as e:
                last_error = e
                self.console.print(f"[yellow]CLI 에러, 재시도 {attempt + 1}/{max_retries + 1}[/yellow]")
            except Exception as e:
                last_error = e
                self.console.print(f"[yellow]에러: {e}, 재시도 {attempt + 1}/{max_retries + 1}[/yellow]")

        raise ScriptGenerationError(f"대본 생성 실패: {last_error}")

    def get_last_prompt(self) -> str:
        """마지막으로 사용된 프롬프트 반환 (캐시 저장용)"""
        return self.last_prompt

    def _call_claude_cli(self, prompt: str) -> str:
        """Claude Code CLI 호출 (stdin으로 프롬프트 전달)"""
        try:
            # claude CLI 호출 - stdin으로 프롬프트 전달
            result = subprocess.run(
                ['claude', '--print'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300  # 5분
            )

            # 에러 출력 확인
            if result.returncode != 0:
                self.console.print(f"[red]Claude CLI 에러: {result.stderr}[/red]")
                raise subprocess.CalledProcessError(
                    result.returncode,
                    'claude',
                    result.stdout,
                    result.stderr
                )

            return result.stdout

        except subprocess.TimeoutExpired:
            self.console.print("[red]Claude CLI 타임아웃 (5분 초과)[/red]")
            raise

    def _parse_response(self, response_text: str) -> dict:
        """응답에서 JSON 추출 및 파싱"""
        text = response_text.strip()

        if "```json" in text:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
        elif "```" in text:
            match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)

        text = text.strip()
        if not text.startswith("{"):
            start_idx = text.find("{")
            if start_idx != -1:
                text = text[start_idx:]

        brace_count = 0
        end_idx = 0
        for i, char in enumerate(text):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break

        if end_idx > 0:
            text = text[:end_idx]

        return json.loads(text)

    def _create_script(self, data: dict, style: str) -> EditScript:
        """파싱된 데이터로 EditScript 객체 생성 (start_time/end_time 자동 계산)"""
        segments = []
        current_time = 0.0

        for seg_data in data.get("segments", []):
            source_start = float(seg_data.get("source_start", 0))
            source_end = float(seg_data.get("source_end", 0))
            speed = float(seg_data.get("speed", 1.0))

            # 출력 길이 계산: (원본 길이 / 속도)
            source_duration = source_end - source_start
            output_duration = source_duration / speed if speed > 0 else source_duration

            # start_time/end_time 자동 계산 (프롬프트에서 받은 값이 있으면 무시)
            start_time = current_time
            end_time = current_time + output_duration

            segment = EditSegment(
                start_time=start_time,
                end_time=end_time,
                source_start=source_start,
                source_end=source_end,
                speed=speed,
                effects=seg_data.get("effects", []),
                transition_in=seg_data.get("transition_in"),
                transition_out=seg_data.get("transition_out"),
                purpose=seg_data.get("purpose", "unknown")
            )
            segments.append(segment)
            current_time = end_time

        # 총 길이는 세그먼트들의 합으로 자동 계산
        total_duration = current_time

        return EditScript(
            segments=segments,
            color_grade=data.get("color_grade", "default"),
            audio_config=data.get("audio_config", {}),
            total_duration=total_duration,
            style_applied=style
        )

    def _validate_script(
        self,
        script: EditScript,
        source_duration: float,
        target_duration: float,
        tolerance: float = 3.0  # 여유 있게 3초까지 허용
    ) -> EditScript:
        """대본 유효성 검증 및 자동 수정 (타임라인 재계산 포함)"""

        # 스타일 기반 검증 규칙 적용
        script = self._apply_style_validation(script)

        validated_segments = []
        current_time = 0.0

        for seg in script.segments:
            # 소스 범위 검증
            if seg.source_start < 0:
                seg.source_start = 0
            if seg.source_end > source_duration:
                seg.source_end = source_duration
            if seg.source_start >= seg.source_end:
                continue

            # 속도 범위 검증 (전역)
            if seg.speed < 0.1:
                seg.speed = 0.1
            if seg.speed > 4.0:
                seg.speed = 4.0

            # 타임라인 재계산
            source_len = seg.source_end - seg.source_start
            output_len = source_len / seg.speed
            seg.start_time = current_time
            seg.end_time = current_time + output_len
            current_time = seg.end_time

            validated_segments.append(seg)

        if not validated_segments:
            raise ScriptGenerationError("유효한 세그먼트가 없습니다")

        actual_duration = current_time

        # 목표 길이와 차이가 많이 나면 정보 출력 (에러는 아님)
        if actual_duration > target_duration + tolerance:
            self.console.print(
                f"[yellow]정보: 대본 길이({actual_duration:.1f}초)가 "
                f"목표({target_duration}초)보다 깁니다 - LLM이 더 좋은 장면을 찾았을 수 있음[/yellow]"
            )
        elif actual_duration < target_duration - tolerance:
            self.console.print(
                f"[dim]정보: 대본 길이({actual_duration:.1f}초)가 목표({target_duration}초)보다 짧습니다 "
                f"- 좋은 장면이 부족할 수 있음[/dim]"
            )

        return EditScript(
            segments=validated_segments,
            color_grade=script.color_grade,
            audio_config=script.audio_config,
            total_duration=actual_duration,
            style_applied=script.style_applied
        )

    def _apply_style_validation(self, script: EditScript) -> EditScript:
        """스타일 설정에 따라 대본 검증 및 보정"""
        style_name = script.style_applied

        try:
            style = self.config.get_style(style_name)
            defaults = style.get("defaults", {})
            allowed = style.get("allowed", {})
        except Exception:
            # 스타일 로드 실패 시 기본값 사용
            return script

        # 1. color_grade 검증 및 기본값 적용
        allowed_grades = allowed.get("color_grades", [])
        if script.color_grade not in allowed_grades:
            default_grade = defaults.get("color_grade", "default")
            script = EditScript(
                segments=script.segments,
                color_grade=default_grade,
                audio_config=script.audio_config,
                total_duration=script.total_duration,
                style_applied=script.style_applied
            )

        # 2. 각 세그먼트 검증
        allowed_effects = allowed.get("effects", [])
        allowed_transitions = allowed.get("transitions", [])
        speed_range = allowed.get("speed_range", {"min": 0.3, "max": 2.0})
        min_speed = speed_range.get("min", 0.3)
        max_speed = speed_range.get("max", 2.0)

        for seg in script.segments:
            # 허용되지 않은 이펙트 제거
            seg.effects = [e for e in seg.effects if e in allowed_effects]

            # 허용되지 않은 트랜지션 변경
            if seg.transition_out and seg.transition_out not in allowed_transitions:
                seg.transition_out = "cut" if "cut" in allowed_transitions else None
            if seg.transition_in and seg.transition_in not in allowed_transitions:
                seg.transition_in = None

            # 속도 범위 적용
            seg.speed = max(min_speed, min(max_speed, seg.speed))

        return script


class ScriptGenerator:
    """Claude API를 사용한 편집 대본 생성기"""

    def __init__(
        self,
        api_key: str,
        config_loader: ConfigLoader,
        model: str = "claude-sonnet-4-20250514",
        console: Optional[Console] = None
    ):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.config = config_loader
        self.model = model
        self.console = console or Console()
        self.prompt_builder = PromptBuilder(config_loader)

    async def generate(
        self,
        video_analysis: VideoAnalysis,
        target_duration: float,
        style: str,
        max_retries: int = 2
    ) -> EditScript:
        import anthropic

        prompt = self.prompt_builder.build(
            video_analysis=video_analysis,
            target_duration=target_duration,
            style_name=style
        )

        self.console.print(f"[dim]대본 생성 중... (스타일: {style})[/dim]")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

                response_text = response.content[0].text
                script_data = self._parse_response(response_text)
                script = self._create_script(script_data, style)

                script = self._validate_script(
                    script,
                    video_analysis.duration,
                    target_duration
                )

                self.console.print(f"[green]✓ 대본 생성 완료 ({len(script.segments)}개 세그먼트)[/green]")
                return script

            except json.JSONDecodeError as e:
                last_error = e
                self.console.print(f"[yellow]JSON 파싱 실패, 재시도 {attempt + 1}/{max_retries + 1}[/yellow]")
            except anthropic.APIError as e:
                raise APIError("Claude", str(e))
            except Exception as e:
                last_error = e
                self.console.print(f"[yellow]에러: {e}, 재시도 {attempt + 1}/{max_retries + 1}[/yellow]")

        raise ScriptGenerationError(f"대본 생성 실패: {last_error}")

    def _parse_response(self, response_text: str) -> dict:
        text = response_text.strip()

        if "```json" in text:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
        elif "```" in text:
            match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)

        text = text.strip()
        if not text.startswith("{"):
            start_idx = text.find("{")
            if start_idx != -1:
                text = text[start_idx:]

        brace_count = 0
        end_idx = 0
        for i, char in enumerate(text):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break

        if end_idx > 0:
            text = text[:end_idx]

        return json.loads(text)

    def _create_script(self, data: dict, style: str) -> EditScript:
        """파싱된 데이터로 EditScript 객체 생성 (start_time/end_time 자동 계산)"""
        segments = []
        current_time = 0.0

        for seg_data in data.get("segments", []):
            source_start = float(seg_data.get("source_start", 0))
            source_end = float(seg_data.get("source_end", 0))
            speed = float(seg_data.get("speed", 1.0))

            # 출력 길이 계산: (원본 길이 / 속도)
            source_duration = source_end - source_start
            output_duration = source_duration / speed if speed > 0 else source_duration

            # start_time/end_time 자동 계산
            start_time = current_time
            end_time = current_time + output_duration

            segment = EditSegment(
                start_time=start_time,
                end_time=end_time,
                source_start=source_start,
                source_end=source_end,
                speed=speed,
                effects=seg_data.get("effects", []),
                transition_in=seg_data.get("transition_in"),
                transition_out=seg_data.get("transition_out"),
                purpose=seg_data.get("purpose", "unknown")
            )
            segments.append(segment)
            current_time = end_time

        total_duration = current_time

        return EditScript(
            segments=segments,
            color_grade=data.get("color_grade", "default"),
            audio_config=data.get("audio_config", {}),
            total_duration=total_duration,
            style_applied=style
        )

    def _validate_script(
        self,
        script: EditScript,
        source_duration: float,
        target_duration: float,
        tolerance: float = 3.0
    ) -> EditScript:
        """대본 유효성 검증 및 자동 수정 (타임라인 재계산 포함)"""

        # 스타일 기반 검증 규칙 적용
        script = self._apply_style_validation(script)

        validated_segments = []
        current_time = 0.0

        for seg in script.segments:
            if seg.source_start < 0:
                seg.source_start = 0
            if seg.source_end > source_duration:
                seg.source_end = source_duration
            if seg.source_start >= seg.source_end:
                continue

            if seg.speed < 0.1:
                seg.speed = 0.1
            if seg.speed > 4.0:
                seg.speed = 4.0

            # 타임라인 재계산
            source_len = seg.source_end - seg.source_start
            output_len = source_len / seg.speed
            seg.start_time = current_time
            seg.end_time = current_time + output_len
            current_time = seg.end_time

            validated_segments.append(seg)

        if not validated_segments:
            raise ScriptGenerationError("유효한 세그먼트가 없습니다")

        actual_duration = current_time

        if actual_duration > target_duration + tolerance:
            self.console.print(
                f"[yellow]정보: 대본 길이({actual_duration:.1f}초)가 "
                f"목표({target_duration}초)보다 깁니다[/yellow]"
            )
        elif actual_duration < target_duration - tolerance:
            self.console.print(
                f"[dim]정보: 대본 길이({actual_duration:.1f}초)가 목표({target_duration}초)보다 짧습니다[/dim]"
            )

        return EditScript(
            segments=validated_segments,
            color_grade=script.color_grade,
            audio_config=script.audio_config,
            total_duration=actual_duration,
            style_applied=script.style_applied
        )

    def _apply_style_validation(self, script: EditScript) -> EditScript:
        """스타일 설정에 따라 대본 검증 및 보정"""
        style_name = script.style_applied

        try:
            style = self.config.get_style(style_name)
            defaults = style.get("defaults", {})
            allowed = style.get("allowed", {})
        except Exception:
            return script

        # 1. color_grade 검증 및 기본값 적용
        allowed_grades = allowed.get("color_grades", [])
        if script.color_grade not in allowed_grades:
            default_grade = defaults.get("color_grade", "default")
            script = EditScript(
                segments=script.segments,
                color_grade=default_grade,
                audio_config=script.audio_config,
                total_duration=script.total_duration,
                style_applied=script.style_applied
            )

        # 2. 각 세그먼트 검증
        allowed_effects = allowed.get("effects", [])
        allowed_transitions = allowed.get("transitions", [])
        speed_range = allowed.get("speed_range", {"min": 0.3, "max": 2.0})
        min_speed = speed_range.get("min", 0.3)
        max_speed = speed_range.get("max", 2.0)

        for seg in script.segments:
            seg.effects = [e for e in seg.effects if e in allowed_effects]

            if seg.transition_out and seg.transition_out not in allowed_transitions:
                seg.transition_out = "cut" if "cut" in allowed_transitions else None
            if seg.transition_in and seg.transition_in not in allowed_transitions:
                seg.transition_in = None

            seg.speed = max(min_speed, min(max_speed, seg.speed))

        return script


class MockScriptGenerator:
    """테스트용 Mock 대본 생성기"""

    def __init__(self, config_loader: ConfigLoader):
        self.config = config_loader

    async def generate(
        self,
        video_analysis: VideoAnalysis,
        target_duration: float,
        style: str,
        max_retries: int = 2
    ) -> EditScript:
        """더미 대본 생성"""

        source_duration = video_analysis.duration
        highlights = video_analysis.highlights or [source_duration * 0.5]

        segments = [
            EditSegment(
                start_time=0.0,
                end_time=target_duration * 0.2,
                source_start=highlights[0] - 0.5 if highlights[0] > 0.5 else 0,
                source_end=highlights[0] + 0.5,
                speed=0.5,
                effects=["speed_ramp"],
                transition_in=None,
                transition_out="flash",
                purpose="hook"
            ),
            EditSegment(
                start_time=target_duration * 0.2,
                end_time=target_duration * 0.7,
                source_start=0,
                source_end=source_duration * 0.7,
                speed=1.2,
                effects=[],
                transition_in="flash",
                transition_out="crossfade",
                purpose="build"
            ),
            EditSegment(
                start_time=target_duration * 0.7,
                end_time=target_duration,
                source_start=highlights[-1] - 1 if len(highlights) > 0 else source_duration - 2,
                source_end=source_duration,
                speed=0.7,
                effects=["speed_ramp"],
                transition_in="crossfade",
                transition_out=None,
                purpose="payoff"
            )
        ]

        return EditScript(
            segments=segments,
            color_grade="high_contrast" if style == "nike" else "default",
            audio_config={"music_sync": True, "fade_out": 0.5},
            total_duration=target_duration,
            style_applied=style
        )
