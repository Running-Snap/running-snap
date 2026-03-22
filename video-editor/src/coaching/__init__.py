"""코칭 모듈 - 자세 분석 텍스트 → 자막 + TTS 영상 생성"""
from .tts_engine import TTSEngine
from .subtitle_generator import SubtitleGenerator
from .coaching_composer import CoachingComposer
from .script_writer import CoachingScriptWriter, CoachingScript, CoachingLine
from .video_editor import CoachingVideoEditor, EditSegment

__all__ = [
    "TTSEngine",
    "SubtitleGenerator",
    "CoachingComposer",
    "CoachingScriptWriter",
    "CoachingScript",
    "CoachingLine",
    "CoachingVideoEditor",
    "EditSegment",
]
