#!/usr/bin/env python3
"""
AI Video Editor - CLI 진입점

사용법:
    python main.py input.mp4 -d 10 -s nike --local
    python main.py input.mp4 --duration 30 --style tiktok --photos 3
"""
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# 환경변수 로드
load_dotenv()

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import VideoPipeline
from src.core.config_loader import ConfigLoader


def main():
    console = Console()

    # 인자 파서
    parser = argparse.ArgumentParser(
        description="AI 기반 자동 영상 편집기 - 러닝/운동 영상을 숏폼으로 변환",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    python main.py my_run.mp4 -d 10 -s action --local     # 액션 스타일 (스포츠 광고)
    python main.py marathon.mp4 -d 10 -s instagram -p 3   # 인스타그램 스타일
    python main.py workout.mp4 -d 10 -s tiktok            # 틱톡 바이럴 스타일
    python main.py run.mp4 -d 15 -s documentary           # 다큐멘터리 스타일
    python main.py run.mp4 -s coaching --coaching-text "자세가 좋습니다"  # 코칭 스타일

스타일 설명:
    action      스포츠 사진작가 스타일 - 결정적 순간 포착, 슬로모션 강조
    instagram   인플루언서 콘텐츠 - 멋있어 보이게, 따뜻한 색감
    tiktok      틱톡 바이럴 - 빠른 컷, 다양한 이펙트, 높은 채도
    humor       밈 편집 - 코미디 타이밍, 웃긴 순간 강조
    documentary 다큐멘터리 - 자연스러운 흐름, 최소 편집
    coaching    코칭 스타일 - 자세 분석 자막 + TTS 음성 해설
        """
    )

    # 필수 인자
    parser.add_argument(
        "input",
        nargs="?",
        help="입력 영상 파일 경로"
    )

    # 선택 인자
    parser.add_argument(
        "-d", "--duration",
        type=float,
        help="목표 영상 길이 (초). 예: 10, 30, 60"
    )

    parser.add_argument(
        "-s", "--style",
        default="action",
        choices=["action", "instagram", "tiktok", "humor", "documentary", "coaching"],
        help="편집 스타일 (기본: action). action=스포츠 액션샷, instagram=인플루언서 콘텐츠, tiktok=바이럴, humor=밈, documentary=다큐, coaching=코칭(자막+TTS)"
    )

    parser.add_argument(
        "--coaching-text",
        type=str,
        help="코칭 스타일용 텍스트 (직접 입력 또는 파일 경로)"
    )

    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="코칭 스타일에서 TTS 비활성화 (자막만)"
    )

    parser.add_argument(
        "-o", "--output",
        default="outputs",
        help="출력 디렉토리 (기본: outputs)"
    )

    parser.add_argument(
        "-p", "--photos",
        type=int,
        default=5,
        choices=range(1, 11),
        metavar="N",
        help="베스트컷 사진 개수 1-10 (기본: 5)"
    )

    parser.add_argument(
        "--photo-preset",
        default="sports_action",
        choices=["sports_action", "golden_hour", "dramatic", "clean_bright"],
        help="사진 보정 프리셋 (기본: sports_action)"
    )

    parser.add_argument(
        "--local",
        action="store_true",
        help="로컬 모델 사용 (Ollama + Claude Code CLI, API 키 불필요)"
    )

    parser.add_argument(
        "--ollama-model",
        default="qwen2.5vl:7b",
        help="Ollama 비전 모델 이름 (기본: qwen2.5vl:7b)"
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="테스트 모드 (더미 데이터 사용, 가장 빠름)"
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="캐시 사용 안 함 (항상 새로 분석)"
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="해당 영상의 캐시 삭제 후 실행"
    )

    parser.add_argument(
        "--list-styles",
        action="store_true",
        help="사용 가능한 스타일 목록 출력"
    )

    parser.add_argument(
        "--list-cache",
        action="store_true",
        help="캐시된 분석 결과 목록 출력"
    )

    args = parser.parse_args()

    # 스타일 목록 출력
    if args.list_styles:
        print_styles(console)
        return 0

    # 캐시 목록 출력
    if args.list_cache:
        print_cache_list(console)
        return 0

    # 입력 파일 확인
    if not args.input:
        parser.print_help()
        return 1

    if not args.duration and args.style != "coaching":
        console.print("[red]오류: -d/--duration 옵션이 필요합니다[/red]")
        return 1

    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]입력 파일이 없습니다: {args.input}[/red]")
        return 1

    # API 키 확인 (로컬 모드가 아닐 때만)
    qwen_key = os.getenv("QWEN_API_KEY")
    claude_key = os.getenv("ANTHROPIC_API_KEY")

    if not args.mock and not args.local:
        if not qwen_key:
            console.print("[yellow]QWEN_API_KEY 없음 - Mock Analyzer 사용[/yellow]")
        if not claude_key:
            console.print("[yellow]ANTHROPIC_API_KEY 없음 - Mock Generator 사용[/yellow]")
        console.print("[dim]팁: --local 옵션으로 로컬 모델을 사용하면 API 키가 필요 없습니다[/dim]")

    # 캐시 삭제 (옵션)
    if args.clear_cache:
        from src.core.analysis_cache import AnalysisCache
        cache = AnalysisCache(console=console)
        cache.clear_cache(str(input_path))

    # 코칭 스타일 처리
    if args.style == "coaching":
        return run_coaching_style(args, input_path, console)

    # 파이프라인 실행
    try:
        pipeline = VideoPipeline(
            qwen_api_key=qwen_key,
            claude_api_key=claude_key,
            use_mock=args.mock,
            use_local=args.local,
            ollama_model=args.ollama_model,
            use_cache=not args.no_cache  # --no-cache면 캐시 비활성화
        )

        result = pipeline.process_sync(
            input_video=str(input_path),
            target_duration=args.duration,
            style=args.style,
            output_dir=args.output,
            photo_count=args.photos,
            photo_preset=args.photo_preset
        )

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]사용자에 의해 중단됨[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]오류 발생: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


def run_coaching_style(args, input_path: Path, console: Console) -> int:
    """코칭 스타일 실행 (자막 + TTS)"""
    from src.coaching import CoachingComposer

    # 코칭 텍스트 확인
    coaching_text = args.coaching_text

    if not coaching_text:
        # 예시 텍스트 사용 (테스트용)
        coaching_text = """지금 보면 상체가 조금 굳어 있어요. 어깨 힘 빼세요.
팔이 몸 앞에서 흔들리는데, 이러면 허리랑 무릎에 부담 옵니다.
팔은 옆으로, 리듬만 주세요.
발은 너무 앞쪽으로 찍어요. 살짝 몸 밑으로 떨어뜨리세요.
보폭 줄이고, 템포를 올리면 훨씬 편해질 겁니다."""
        console.print("[yellow]--coaching-text 없음, 예시 텍스트 사용[/yellow]")

    # 파일 경로인 경우 읽기
    if Path(coaching_text).exists():
        with open(coaching_text, 'r', encoding='utf-8') as f:
            coaching_text = f.read()
        console.print(f"[dim]코칭 텍스트 파일 로드: {coaching_text[:50]}...[/dim]")

    try:
        # 출력 경로 설정
        output_dir = Path(args.output) / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_video = output_dir / f"{input_path.stem}_coaching_{timestamp}.mp4"

        # 코칭 컴포저 실행
        composer = CoachingComposer(
            tts_enabled=not args.no_tts,
            subtitle_enabled=True,
            console=console
        )

        console.print()
        console.print("[bold cyan]═══ 코칭 영상 생성 ═══[/bold cyan]")
        console.print(f"입력: {input_path}")
        console.print(f"TTS: {'활성화' if not args.no_tts else '비활성화'}")
        console.print()

        result = composer.compose(
            input_video=str(input_path),
            coaching_text=coaching_text,
            output_video=str(output_video)
        )

        console.print()
        console.print(f"[green]✓ 완료: {result}[/green]")
        return 0

    except Exception as e:
        console.print(f"[red]코칭 영상 생성 실패: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


def print_styles(console: Console):
    """사용 가능한 스타일 출력"""
    try:
        config = ConfigLoader("configs")
        styles_config = config._load_yaml("editing_styles.yaml")
        styles = styles_config.get("styles", {})

        table = Table(title="사용 가능한 편집 스타일")
        table.add_column("스타일", style="cyan")
        table.add_column("이름", style="green")
        table.add_column("설명")
        table.add_column("특징", style="dim")

        for key, value in styles.items():
            chars = value.get("characteristics", {})
            features = f"pacing={chars.get('pacing', '-')}, sync={chars.get('music_sync', '-')}"
            table.add_row(
                key,
                value.get("name", key),
                value.get("description", ""),
                features
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]스타일 목록을 불러올 수 없습니다: {e}[/red]")


def print_cache_list(console: Console):
    """캐시된 분석 결과 목록 출력"""
    from src.core.analysis_cache import AnalysisCache

    cache = AnalysisCache(console=console)

    # 분석 결과 목록
    analyses = cache.list_cached_analyses()
    if analyses:
        table = Table(title="캐시된 분석 결과")
        table.add_column("영상", style="cyan")
        table.add_column("분석 시간", style="green")
        table.add_column("길이(초)")
        table.add_column("프레임 수")
        table.add_column("파일", style="dim")

        for item in analyses:
            table.add_row(
                item["video"],
                item["analyzed_at"][:19],  # ISO format 자르기
                f"{item['duration']:.1f}",
                str(item["frames"]),
                item["file"]
            )
        console.print(table)
    else:
        console.print("[yellow]캐시된 분석 결과가 없습니다[/yellow]")

    # 대본 목록
    scripts = cache.list_cached_scripts()
    if scripts:
        table = Table(title="캐시된 편집 대본")
        table.add_column("영상", style="cyan")
        table.add_column("스타일", style="magenta")
        table.add_column("목표(초)")
        table.add_column("생성 시간", style="green")
        table.add_column("세그먼트 수")
        table.add_column("파일", style="dim")

        for item in scripts:
            table.add_row(
                item["video"],
                item["style"],
                str(int(item["target_duration"])),
                item["generated_at"][:19],
                str(item["segments"]),
                item["file"]
            )
        console.print(table)
    else:
        console.print("[yellow]캐시된 대본이 없습니다[/yellow]")

    console.print(f"\n[dim]캐시 위치: outputs/cache/[/dim]")


if __name__ == "__main__":
    sys.exit(main())
