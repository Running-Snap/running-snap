"""
메인 파이프라인 오케스트레이터
전체 처리 흐름을 관리
"""
import os
import asyncio
import time
from pathlib import Path
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .core.config_loader import ConfigLoader
from .core.models import (
    VideoAnalysis,
    EditScript,
    ProcessingResult,
    DurationType
)
from .core.exceptions import VideoEditorError
from .core.analysis_cache import AnalysisCache
from .analyzers import VideoAnalyzer, FrameAnalyzer, MockFrameAnalyzer, OllamaFrameAnalyzer
from .directors import ScriptGenerator, MockScriptGenerator, ClaudeCodeScriptGenerator
from .renderers import VideoRenderer
from .photographers import FrameSelector, PhotoEnhancer


class VideoPipeline:
    """메인 비디오 편집 파이프라인"""

    def __init__(
        self,
        qwen_api_key: Optional[str] = None,
        claude_api_key: Optional[str] = None,
        config_dir: str = "configs",
        use_mock: bool = False,
        use_local: bool = False,
        ollama_model: str = "qwen2.5vl:7b",
        use_cache: bool = True
    ):
        """
        Args:
            qwen_api_key: Qwen/DashScope API 키 (없으면 환경변수에서)
            claude_api_key: Anthropic API 키 (없으면 환경변수에서)
            config_dir: 설정 파일 디렉토리
            use_mock: True면 Mock 분석기/생성기 사용 (테스트용)
            use_local: True면 로컬 모델 사용 (Ollama + Claude Code CLI)
            ollama_model: Ollama 비전 모델 이름
            use_cache: True면 분석 결과/대본 캐시 사용
        """
        self.console = Console()

        # API 키 로드
        self.qwen_api_key = qwen_api_key or os.getenv("QWEN_API_KEY", "")
        self.claude_api_key = claude_api_key or os.getenv("ANTHROPIC_API_KEY", "")

        # 설정 로더
        self.config = ConfigLoader(config_dir)

        # 모드 설정
        self.use_mock = use_mock
        self.use_local = use_local
        self.ollama_model = ollama_model
        self.use_cache = use_cache

        # 캐시 시스템 초기화
        self.cache = AnalysisCache(cache_dir="outputs/cache", console=self.console)

        # 컴포넌트 초기화
        self._init_components()

    def _init_components(self):
        """컴포넌트 초기화"""
        # Analyzer 선택
        if self.use_mock:
            self.console.print("[yellow]Mock Analyzer 사용[/yellow]")
            frame_analyzer = MockFrameAnalyzer()
        elif self.use_local:
            self.console.print(f"[cyan]Ollama 로컬 Analyzer 사용 ({self.ollama_model})[/cyan]")
            frame_analyzer = OllamaFrameAnalyzer(model=self.ollama_model)
        elif self.qwen_api_key:
            self.console.print("[cyan]Qwen API Analyzer 사용[/cyan]")
            frame_analyzer = FrameAnalyzer(self.qwen_api_key)
        else:
            self.console.print("[yellow]Mock Analyzer 사용 (API 키 없음)[/yellow]")
            frame_analyzer = MockFrameAnalyzer()

        self.video_analyzer = VideoAnalyzer(
            self.config,
            frame_analyzer,
            self.console
        )

        # Script Generator 선택
        if self.use_mock:
            self.console.print("[yellow]Mock Script Generator 사용[/yellow]")
            self.script_generator = MockScriptGenerator(self.config)
        elif self.use_local:
            self.console.print("[cyan]Claude Code CLI Script Generator 사용[/cyan]")
            self.script_generator = ClaudeCodeScriptGenerator(
                self.config,
                console=self.console
            )
        elif self.claude_api_key:
            self.console.print("[cyan]Claude API Script Generator 사용[/cyan]")
            self.script_generator = ScriptGenerator(
                self.claude_api_key,
                self.config,
                console=self.console
            )
        else:
            self.console.print("[yellow]Mock Script Generator 사용 (API 키 없음)[/yellow]")
            self.script_generator = MockScriptGenerator(self.config)

        # Renderer
        self.renderer = VideoRenderer(self.config, self.console)

        # Photographer
        self.frame_selector = FrameSelector(self.config, self.console)
        self.photo_enhancer = PhotoEnhancer(self.config, self.console)

    async def process(
        self,
        input_video: str,
        target_duration: float,
        style: str = "nike",
        output_dir: str = "outputs",
        photo_count: int = 5,
        photo_preset: str = "sports_action"
    ) -> ProcessingResult:
        """
        전체 처리 파이프라인

        Args:
            input_video: 입력 영상 경로
            target_duration: 목표 출력 영상 길이 (초)
            style: 편집 스타일 (nike, tiktok, humor, cinematic, documentary)
            output_dir: 출력 디렉토리
            photo_count: 베스트컷 사진 개수 (3-5 권장)
            photo_preset: 사진 보정 프리셋

        Returns:
            ProcessingResult 객체
        """
        start_time = time.time()

        # 입력 검증
        input_path = Path(input_video)
        if not input_path.exists():
            raise VideoEditorError(f"입력 영상이 없습니다: {input_video}")

        # 스타일 검증
        available_styles = self.config.get_available_styles()
        if style not in available_styles:
            raise VideoEditorError(
                f"알 수 없는 스타일: {style}. 사용 가능: {available_styles}"
            )

        # 출력 디렉토리 설정
        output_dir = Path(output_dir)
        video_output_dir = output_dir / "videos"
        photo_output_dir = output_dir / "photos"
        temp_dir = Path("temp")

        video_output_dir.mkdir(parents=True, exist_ok=True)
        photo_output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 출력 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_video_name = f"{input_path.stem}_{style}_{int(target_duration)}s_{timestamp}.mp4"
        output_video_path = video_output_dir / output_video_name

        # 헤더 출력
        self._print_header(input_video, target_duration, style, photo_count)

        try:
            # ===== Step 1: 영상 분석 =====
            self.console.print("\n[bold cyan]Step 1/5: 영상 분석[/bold cyan]")

            # 캐시에서 분석 결과 로드 시도
            analysis = None
            if self.use_cache:
                analysis = self.cache.load_analysis(input_video)

            if analysis is None:
                # 캐시 없음 - 새로 분석
                if self.use_local:
                    max_concurrent = 1
                    max_frames = 10
                else:
                    max_concurrent = 5
                    max_frames = 0

                analysis = await self.video_analyzer.analyze(
                    video_path=input_video,
                    target_duration=target_duration,
                    max_concurrent=max_concurrent,
                    show_progress=True,
                    max_frames=max_frames
                )

                # 분석 결과 캐시에 저장
                if self.use_cache:
                    self.cache.save_analysis(input_video, analysis)

            self._print_analysis_summary(analysis)

            # ===== Step 2: 대본 생성 =====
            self.console.print("\n[bold cyan]Step 2/5: 편집 대본 생성[/bold cyan]")

            # 캐시에서 대본 로드 시도 (같은 영상 + 스타일 + 목표길이)
            script = None
            if self.use_cache:
                script = self.cache.load_script(input_video, style, target_duration)

            if script is None:
                # 캐시 없음 - 새로 생성
                script = await self.script_generator.generate(
                    video_analysis=analysis,
                    target_duration=target_duration,
                    style=style
                )

                # 대본 캐시에 저장 (프롬프트 포함)
                if self.use_cache:
                    prompt_used = ""
                    if hasattr(self.script_generator, 'get_last_prompt'):
                        prompt_used = self.script_generator.get_last_prompt()
                    self.cache.save_script(input_video, style, target_duration, script, prompt_used)

            self._print_script_summary(script)

            # ===== Step 3: 영상 렌더링 =====
            self.console.print("\n[bold cyan]Step 3/5: 영상 렌더링[/bold cyan]")
            rendered_video = self.renderer.render(
                video_path=input_video,
                script=script,
                output_path=str(output_video_path),
                show_progress=True
            )

            # ===== Step 4: 베스트컷 선별 =====
            self.console.print("\n[bold cyan]Step 4/5: 베스트컷 선별[/bold cyan]")
            candidates = self.frame_selector.select_best_frames(
                video_path=input_video,
                analysis=analysis,
                count=photo_count,
                output_dir=str(temp_dir / "frames"),
                style=style,  # 스타일 전달 (구도 적용용)
                apply_composition=True  # 구도 자동 조정 활성화
            )

            # ===== Step 5: 사진 보정 =====
            self.console.print("\n[bold cyan]Step 5/5: 사진 보정[/bold cyan]")
            enhanced_photos = []

            for i, candidate in enumerate(candidates):
                if candidate.frame_path:
                    # 입력 파일명 + 스타일 + 번호 + 타임스탬프
                    output_photo_name = f"{input_path.stem}_{style}_best{i+1}_{candidate.timestamp:.1f}s.jpg"
                    output_photo_path = photo_output_dir / output_photo_name

                    saved_path = self.photo_enhancer.enhance_and_save(
                        input_path=candidate.frame_path,
                        output_path=str(output_photo_path),
                        preset=photo_preset
                    )
                    enhanced_photos.append(saved_path)
                    self.console.print(f"  [dim]+ {output_photo_name} (점수: {candidate.overall_score:.2f})[/dim]")

            # 처리 시간
            elapsed_time = time.time() - start_time

            # 결과 생성
            result = ProcessingResult(
                video_path=rendered_video,
                video_duration=script.total_duration,
                photos=enhanced_photos,
                style_used=style,
                processing_time=elapsed_time,
                metadata={
                    "source_video": str(input_video),
                    "source_duration": analysis.duration,
                    "target_duration": target_duration,
                    "segments_count": len(script.segments),
                    "highlights_used": analysis.highlights,
                    "photo_preset": photo_preset
                }
            )

            # 완료 메시지
            self._print_completion(result)

            return result

        except Exception as e:
            self.console.print(f"\n[bold red]처리 실패: {e}[/bold red]")
            raise

        finally:
            # 임시 파일 정리 (선택적)
            # self._cleanup_temp(temp_dir)
            pass

    def process_sync(
        self,
        input_video: str,
        target_duration: float,
        style: str = "nike",
        output_dir: str = "outputs",
        photo_count: int = 5,
        photo_preset: str = "sports_action"
    ) -> ProcessingResult:
        """동기 버전의 process"""
        return asyncio.run(self.process(
            input_video=input_video,
            target_duration=target_duration,
            style=style,
            output_dir=output_dir,
            photo_count=photo_count,
            photo_preset=photo_preset
        ))

    def _print_header(
        self,
        input_video: str,
        target_duration: float,
        style: str,
        photo_count: int
    ):
        """시작 헤더 출력"""
        mode = "로컬" if self.use_local else ("Mock" if self.use_mock else "API")
        header_text = f"""[bold]AI Video Editor[/bold] ({mode} 모드)

입력: {input_video}
목표 길이: {target_duration}초
스타일: {style}
베스트컷: {photo_count}장"""

        self.console.print(Panel(header_text, title="작업 시작", border_style="cyan"))

    def _print_analysis_summary(self, analysis: VideoAnalysis):
        """분석 결과 요약 출력"""
        self.console.print(f"  [dim]원본 길이: {analysis.duration:.1f}초[/dim]")
        self.console.print(f"  [dim]분석 프레임: {len(analysis.frames)}개[/dim]")
        self.console.print(f"  [dim]하이라이트: {len(analysis.highlights)}개 발견[/dim]")
        self.console.print(f"  [dim]전체 움직임: {analysis.overall_motion}[/dim]")

    def _print_script_summary(self, script: EditScript):
        """대본 요약 출력"""
        self.console.print(f"  [dim]세그먼트: {len(script.segments)}개[/dim]")
        self.console.print(f"  [dim]총 길이: {script.total_duration:.1f}초[/dim]")
        self.console.print(f"  [dim]컬러 그레이드: {script.color_grade}[/dim]")

        # 세그먼트 상세
        for i, seg in enumerate(script.segments[:5]):  # 최대 5개만
            self.console.print(
                f"    [dim]{i+1}. {seg.purpose}: "
                f"{seg.source_start:.1f}s-{seg.source_end:.1f}s "
                f"(speed={seg.speed}x)[/dim]"
            )
        if len(script.segments) > 5:
            self.console.print(f"    [dim]... 외 {len(script.segments) - 5}개[/dim]")

    def _print_completion(self, result: ProcessingResult):
        """완료 메시지 출력"""
        completion_text = f"""[bold green]처리 완료![/bold green]

[bold]영상:[/bold]
  {result.video_path}
  길이: {result.video_duration:.1f}초

[bold]베스트컷 ({len(result.photos)}장):[/bold]"""

        for photo in result.photos:
            completion_text += f"\n  {photo}"

        completion_text += f"""

[bold]처리 시간:[/bold] {result.processing_time:.1f}초
[bold]스타일:[/bold] {result.style_used}"""

        self.console.print(Panel(completion_text, title="완료", border_style="green"))

    def _cleanup_temp(self, temp_dir: Path):
        """임시 파일 정리"""
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


# 간단한 유틸리티 함수
def create_pipeline(use_mock: bool = False, use_local: bool = False) -> VideoPipeline:
    """파이프라인 생성 헬퍼"""
    return VideoPipeline(use_mock=use_mock, use_local=use_local)
