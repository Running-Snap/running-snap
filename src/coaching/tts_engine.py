"""
TTS 엔진 모듈
텍스트를 음성으로 변환하고 길이 측정
"""
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from rich.console import Console

# TTS 엔진 import (설치 여부에 따라 폴백)
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    print("gTTS 미설치 - pip install gtts")

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("pydub 미설치 - pip install pydub")


@dataclass
class TTSResult:
    """TTS 생성 결과"""
    audio_file: str
    duration: float  # 초 단위
    text: str
    success: bool = True
    error: Optional[str] = None


class TTSEngine:
    """
    텍스트를 음성으로 변환하는 엔진
    gTTS (온라인) 또는 pyttsx3 (오프라인) 지원
    """

    def __init__(
        self,
        engine: str = "gtts",
        language: str = "ko",
        output_dir: Optional[str] = None,
        console: Optional[Console] = None
    ):
        """
        Args:
            engine: TTS 엔진 선택 ('gtts', 'pyttsx3')
            language: 언어 코드 (기본: 'ko')
            output_dir: 음성 파일 저장 디렉토리
            console: Rich Console 객체
        """
        self.engine = engine
        self.language = language
        self.console = console or Console()

        # 출력 디렉토리 설정
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("outputs/cache/tts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 엔진 유효성 검사
        self._validate_engine()

    def _validate_engine(self):
        """사용 가능한 엔진 확인"""
        if self.engine == "gtts" and not GTTS_AVAILABLE:
            self.console.print("[yellow]gTTS 미설치 - pyttsx3로 폴백[/yellow]")
            self.engine = "pyttsx3"

        if self.engine == "pyttsx3" and not PYTTSX3_AVAILABLE:
            self.console.print("[yellow]pyttsx3 미설치 - 더미 모드[/yellow]")
            self.engine = "dummy"

    def generate(
        self,
        text: str,
        filename: Optional[str] = None,
        index: int = 0
    ) -> TTSResult:
        """
        텍스트를 음성 파일로 변환

        Args:
            text: 변환할 텍스트
            filename: 저장할 파일명 (없으면 자동 생성)
            index: 파일 인덱스 (자동 파일명용)

        Returns:
            TTSResult: 생성 결과 (파일 경로, 길이 등)
        """
        if not filename:
            filename = f"coaching_{index:03d}.mp3"

        output_path = self.output_dir / filename

        try:
            if self.engine == "gtts":
                return self._generate_gtts(text, output_path)
            elif self.engine == "pyttsx3":
                return self._generate_pyttsx3(text, output_path)
            else:
                return self._generate_dummy(text, output_path)

        except Exception as e:
            self.console.print(f"[red]TTS 생성 실패: {e}[/red]")
            return TTSResult(
                audio_file=str(output_path),
                duration=self._estimate_duration(text),
                text=text,
                success=False,
                error=str(e)
            )

    def _generate_gtts(self, text: str, output_path: Path) -> TTSResult:
        """gTTS로 음성 생성"""
        tts = gTTS(text=text, lang=self.language)
        tts.save(str(output_path))

        # 길이 측정
        duration = self._measure_duration(output_path)

        return TTSResult(
            audio_file=str(output_path),
            duration=duration,
            text=text
        )

    def _generate_pyttsx3(self, text: str, output_path: Path) -> TTSResult:
        """pyttsx3로 음성 생성 (오프라인)"""
        engine = pyttsx3.init()

        # 한국어 음성 설정 시도
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'korean' in voice.name.lower() or 'ko' in voice.id.lower():
                engine.setProperty('voice', voice.id)
                break

        engine.save_to_file(text, str(output_path))
        engine.runAndWait()

        duration = self._measure_duration(output_path)

        return TTSResult(
            audio_file=str(output_path),
            duration=duration,
            text=text
        )

    def _generate_dummy(self, text: str, output_path: Path) -> TTSResult:
        """TTS 엔진 없을 때 더미 결과 (테스트용)"""
        # 빈 오디오 파일 생성 (실제로는 침묵)
        duration = self._estimate_duration(text)

        return TTSResult(
            audio_file=str(output_path),
            duration=duration,
            text=text,
            success=False,
            error="TTS 엔진 없음 - 더미 모드"
        )

    def _measure_duration(self, audio_path: Path) -> float:
        """음성 파일 길이 측정"""
        if not PYDUB_AVAILABLE:
            return self._estimate_duration("")

        try:
            audio = AudioSegment.from_mp3(str(audio_path))
            return len(audio) / 1000.0  # 밀리초 → 초
        except Exception:
            return self._estimate_duration("")

    def _estimate_duration(self, text: str, chars_per_second: float = 5.0) -> float:
        """
        텍스트 길이로 대략적인 음성 길이 추정
        한국어 기준: 초당 약 5글자
        """
        if not text:
            return 2.0
        estimated = len(text) / chars_per_second
        return max(1.5, estimated + 0.5)  # 최소 1.5초

    def generate_batch(
        self,
        texts: List[str],
        prefix: str = "coaching"
    ) -> List[TTSResult]:
        """
        여러 텍스트를 일괄 변환

        Args:
            texts: 텍스트 리스트
            prefix: 파일명 접두사

        Returns:
            TTSResult 리스트
        """
        results = []

        for i, text in enumerate(texts):
            filename = f"{prefix}_{i:03d}.mp3"
            result = self.generate(text, filename, i)
            results.append(result)

            if result.success:
                self.console.print(f"  [dim]✓ TTS {i+1}/{len(texts)}: {text[:20]}...[/dim]")

        return results

    def clear_cache(self):
        """캐시된 TTS 파일 삭제"""
        import shutil
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.console.print("[dim]TTS 캐시 삭제됨[/dim]")
