"""
코칭 대본 생성기
LLM을 사용하여 자세 분석 텍스트를 영상 길이에 맞는 코칭 대본으로 변환
"""
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import json
import subprocess
from rich.console import Console

# Ollama import
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


@dataclass
class CoachingLine:
    """코칭 대본 한 줄"""
    text: str
    priority: int  # 1=필수, 2=중요, 3=권장
    estimated_duration: float  # 예상 TTS 길이 (초)


@dataclass
class CoachingScript:
    """코칭 대본"""
    lines: List[CoachingLine]
    total_duration: float  # 예상 총 TTS 길이
    video_duration: float  # 원본 영상 길이

    def get_texts(self) -> List[str]:
        """텍스트만 추출"""
        return [line.text for line in self.lines]


class CoachingScriptWriter:
    """
    LLM을 사용한 코칭 대본 생성기

    역할:
    1. 입력 텍스트를 분석하여 중요도 순으로 정리
    2. 영상 길이에 맞춰 대본 길이 조절 (±2초 오차)
    3. 너무 긴 경우 덜 중요한 문장 제거
    """

    CHARS_PER_SECOND = 5.0  # 한국어 TTS 기준 초당 글자 수

    def __init__(
        self,
        model: str = "qwen2.5vl:7b",
        console: Optional[Console] = None
    ):
        self.model = model
        self.console = console or Console()

        # 코치 스타일 프롬프트
        self.system_prompt = """당신은 러닝 코칭 대본 작가입니다.

## 역할
자세 분석 텍스트를 받아서, 영상에 사용할 코칭 대본을 작성합니다.

## 규칙
1. 입력된 모든 내용을 최대한 포함 (빠뜨리지 않기)
2. 각 문장은 20자 이내로 짧고 명확하게
3. "~해보세요", "~하세요" 같은 부드러운 어투
4. 기술 용어 대신 쉬운 말 사용
5. TTS로 읽었을 때 자연스럽게

## 출력 형식
반드시 아래 JSON 형식으로만 출력하세요:
{
  "lines": [
    {"text": "문장1", "priority": 1},
    {"text": "문장2", "priority": 2}
  ]
}

priority: 1=필수(핵심 교정), 2=중요(보조 교정), 3=권장(격려/팁)"""

    def estimate_tts_duration(self, text: str) -> float:
        """텍스트의 TTS 예상 길이 계산"""
        # 한국어 기준 초당 약 5글자
        duration = len(text) / self.CHARS_PER_SECOND
        return max(1.5, duration + 0.3)  # 최소 1.5초, 여유 0.3초 추가

    def generate_script(
        self,
        analysis_text: str,
        video_duration: float,
        tolerance: float = 2.0
    ) -> CoachingScript:
        """
        코칭 대본 생성

        Args:
            analysis_text: 자세 분석 텍스트
            video_duration: 영상 길이 (초)
            tolerance: 허용 오차 (초), 기본 ±2초

        Returns:
            CoachingScript 객체
        """
        target_duration = video_duration
        min_duration = video_duration - tolerance
        max_duration = video_duration + tolerance

        self.console.print(f"[cyan]코칭 대본 생성 중...[/cyan]")
        self.console.print(f"  영상 길이: {video_duration:.1f}초")
        self.console.print(f"  목표 TTS 길이: {min_duration:.1f}~{max_duration:.1f}초")

        # 1. LLM으로 대본 생성
        raw_lines = self._generate_with_llm(analysis_text, video_duration)

        if not raw_lines:
            # LLM 실패 시 폴백: 원본 텍스트 파싱
            self.console.print("[yellow]LLM 생성 실패 - 원본 텍스트 사용[/yellow]")
            raw_lines = self._parse_fallback(analysis_text)

        # 2. 예상 길이 계산 및 조절
        lines = self._adjust_to_duration(raw_lines, min_duration, max_duration)

        # 3. 총 길이 계산
        total_duration = sum(line.estimated_duration for line in lines)

        self.console.print(f"  생성된 문장: {len(lines)}개")
        self.console.print(f"  예상 TTS 길이: {total_duration:.1f}초")

        return CoachingScript(
            lines=lines,
            total_duration=total_duration,
            video_duration=video_duration
        )

    def _generate_with_llm(
        self,
        analysis_text: str,
        video_duration: float
    ) -> List[CoachingLine]:
        """LLM으로 대본 생성"""

        # 예상 문장 수 계산 (문장당 평균 2.5초 가정)
        estimated_lines = int(video_duration / 2.5)

        user_prompt = f"""## 입력 텍스트
{analysis_text}

## 제약 조건
- 최종 영상 길이: {video_duration:.1f}초
- 예상 문장 수: {estimated_lines}개 내외
- 각 문장 TTS 예상 시간: 약 2-3초
- 중요: 입력된 모든 내용을 최대한 포함할 것
- 총 TTS 시간이 영상 길이보다 약간 짧아야 함 (영상이 더 길게)

## 요청
위 텍스트의 모든 교정 사항을 빠짐없이 코칭 대본으로 변환해주세요.
내용을 줄이기보다 짧은 문장으로 나눠서 모두 포함하세요."""

        try:
            if OLLAMA_AVAILABLE:
                response = ollama.chat(
                    model=self.model,
                    messages=[
                        {'role': 'system', 'content': self.system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ]
                )
                content = response['message']['content']
            else:
                # Claude Code CLI 사용
                content = self._call_claude_cli(user_prompt)

            return self._parse_llm_response(content)

        except Exception as e:
            self.console.print(f"[yellow]LLM 호출 실패: {e}[/yellow]")
            return []

    def _call_claude_cli(self, prompt: str) -> str:
        """Claude Code CLI 호출"""
        full_prompt = f"{self.system_prompt}\n\n{prompt}"

        try:
            result = subprocess.run(
                ["claude", "-p", full_prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.stdout.strip()
        except Exception as e:
            self.console.print(f"[yellow]Claude CLI 실패: {e}[/yellow]")
            return ""

    def _parse_llm_response(self, content: str) -> List[CoachingLine]:
        """LLM 응답 파싱"""
        lines = []

        try:
            # JSON 추출 시도
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())

                for item in data.get('lines', []):
                    text = item.get('text', '').strip()
                    priority = item.get('priority', 2)

                    if text:
                        lines.append(CoachingLine(
                            text=text,
                            priority=priority,
                            estimated_duration=self.estimate_tts_duration(text)
                        ))
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 줄 단위로 파싱
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('{') and not line.startswith('}'):
                    # 따옴표나 특수문자 제거
                    clean = line.strip('"\'- ')
                    if clean and len(clean) > 3:
                        lines.append(CoachingLine(
                            text=clean,
                            priority=2,
                            estimated_duration=self.estimate_tts_duration(clean)
                        ))

        return lines

    def _parse_fallback(self, text: str) -> List[CoachingLine]:
        """원본 텍스트 파싱 (폴백)"""
        lines = []

        # 줄바꿈 또는 문장부호로 분리
        import re
        sentences = re.split(r'[.\n]+', text)

        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if sentence and len(sentence) > 3:
                lines.append(CoachingLine(
                    text=sentence,
                    priority=min(3, i + 1),  # 앞에 있을수록 중요
                    estimated_duration=self.estimate_tts_duration(sentence)
                ))

        return lines

    def _adjust_to_duration(
        self,
        lines: List[CoachingLine],
        min_duration: float,
        max_duration: float
    ) -> List[CoachingLine]:
        """대본 길이를 영상 길이에 맞게 조절 - 최대한 많이 포함"""

        if not lines:
            return []

        # 중요도 순으로 정렬
        sorted_lines = sorted(lines, key=lambda x: x.priority)

        result = []
        total = 0.0
        gap_per_line = 0.5  # 문장 간 간격

        for line in sorted_lines:
            new_total = total + line.estimated_duration + gap_per_line

            # 최대 길이까지 최대한 포함 (영상보다 TTS가 짧아야 함)
            if new_total > max_duration and result:
                # 이미 충분히 들어갔으면 중단
                break

            result.append(line)
            total = new_total

        # TTS가 영상보다 길면 마지막 문장들 제거
        while total > max_duration and len(result) > 1:
            removed = result.pop()
            total -= (removed.estimated_duration + gap_per_line)
            self.console.print(f"[dim]  - 제거: {removed.text[:20]}... (길이 초과)[/dim]")

        self.console.print(f"[dim]  TTS 예상: {total:.1f}초, 영상: {max_duration:.1f}초[/dim]")

        return result
