"""커스텀 예외 클래스"""

class VideoEditorError(Exception):
    """기본 예외"""
    pass

class ConfigError(VideoEditorError):
    """설정 관련 에러"""
    pass

class AnalysisError(VideoEditorError):
    """분석 관련 에러"""
    pass

class ScriptGenerationError(VideoEditorError):
    """대본 생성 관련 에러"""
    pass

class RenderError(VideoEditorError):
    """렌더링 관련 에러"""
    pass

class PhotoProcessingError(VideoEditorError):
    """사진 처리 관련 에러"""
    pass

class APIError(VideoEditorError):
    """외부 API 관련 에러"""
    def __init__(self, service: str, message: str):
        self.service = service
        super().__init__(f"[{service}] {message}")
