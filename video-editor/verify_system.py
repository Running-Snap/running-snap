#!/usr/bin/env python3
"""
전체 시스템 검증 스크립트
모든 모듈이 정상적으로 로드되고 동작하는지 확인
"""
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def check_imports():
    """모든 모듈 import 확인"""
    console.print("\n[bold]1. 모듈 Import 검증[/bold]")

    modules = [
        ("src.core.config_loader", "ConfigLoader"),
        ("src.core.models", "VideoAnalysis, EditScript, ProcessingResult"),
        ("src.core.exceptions", "VideoEditorError"),
        ("src.analyzers", "FrameAnalyzer, VideoAnalyzer, MockFrameAnalyzer"),
        ("src.directors", "PromptBuilder, ScriptGenerator, MockScriptGenerator"),
        ("src.renderers", "VideoRenderer"),
        ("src.renderers.effects", "apply_speed_ramp, apply_transition"),
        ("src.photographers", "FrameSelector, PhotoEnhancer"),
        ("src.pipeline", "VideoPipeline"),
    ]

    results = []
    all_passed = True

    for module_path, components in modules:
        try:
            module = __import__(module_path, fromlist=components.split(", "))
            for comp in components.split(", "):
                comp = comp.strip()
                if hasattr(module, comp):
                    results.append((module_path, comp, "OK"))
                else:
                    results.append((module_path, comp, "Not Found"))
                    all_passed = False
        except Exception as e:
            results.append((module_path, components, f"{e}"))
            all_passed = False

    table = Table(title="Import 검증")
    table.add_column("모듈")
    table.add_column("컴포넌트")
    table.add_column("상태")

    for module, comp, status in results:
        style = "green" if status == "OK" else "red"
        table.add_row(module, comp, f"[{style}]{status}[/{style}]")

    console.print(table)
    return all_passed


def check_configs():
    """설정 파일 검증"""
    console.print("\n[bold]2. 설정 파일 검증[/bold]")

    config_files = [
        "configs/analysis_profiles.yaml",
        "configs/editing_styles.yaml",
        "configs/script_prompts.yaml",
        "configs/photo_grading.yaml",
        "configs/output_specs.yaml",
    ]

    results = []
    all_passed = True

    for config_file in config_files:
        path = Path(config_file)
        if path.exists():
            try:
                import yaml
                with open(path, 'r', encoding='utf-8') as f:
                    yaml.safe_load(f)
                results.append((config_file, "Valid YAML"))
            except Exception as e:
                results.append((config_file, f"Invalid: {e}"))
                all_passed = False
        else:
            results.append((config_file, "Not Found"))
            all_passed = False

    table = Table(title="설정 파일")
    table.add_column("파일")
    table.add_column("상태")

    for file, status in results:
        style = "green" if "Valid" in status else "red"
        table.add_row(file, f"[{style}]{status}[/{style}]")

    console.print(table)
    return all_passed


def check_config_loading():
    """ConfigLoader 동작 검증"""
    console.print("\n[bold]3. ConfigLoader 검증[/bold]")

    try:
        from src.core.config_loader import ConfigLoader
        from src.core.models import DurationType

        config = ConfigLoader("configs")

        tests = []

        # 분석 프로파일 로드
        try:
            profile = config.get_analysis_profile(DurationType.SHORT)
            tests.append(("get_analysis_profile(SHORT)", "OK"))
        except Exception as e:
            tests.append(("get_analysis_profile(SHORT)", f"{e}"))

        # 편집 스타일 로드
        try:
            style = config.get_editing_style("nike")
            tests.append(("get_editing_style('nike')", "OK"))
        except Exception as e:
            tests.append(("get_editing_style('nike')", f"{e}"))

        # 스크립트 프롬프트 로드
        try:
            prompt = config.get_script_prompt(DurationType.SHORT, "nike")
            tests.append(("get_script_prompt(SHORT, 'nike')", f"OK ({len(prompt)} chars)"))
        except Exception as e:
            tests.append(("get_script_prompt(SHORT, 'nike')", f"{e}"))

        # 사진 기준 로드
        try:
            criteria = config.get_photo_selection_criteria()
            tests.append(("get_photo_selection_criteria()", "OK"))
        except Exception as e:
            tests.append(("get_photo_selection_criteria()", f"{e}"))

        # 사용 가능한 스타일 목록
        try:
            styles = config.get_available_styles()
            tests.append(("get_available_styles()", f"OK {styles}"))
        except Exception as e:
            tests.append(("get_available_styles()", f"{e}"))

        table = Table(title="ConfigLoader 기능")
        table.add_column("메서드")
        table.add_column("결과")

        for method, result in tests:
            style = "green" if result.startswith("OK") else "red"
            table.add_row(method, f"[{style}]{result}[/{style}]")

        console.print(table)
        return all(r.startswith("OK") for _, r in tests)

    except Exception as e:
        console.print(f"[red]ConfigLoader 초기화 실패: {e}[/red]")
        return False


def check_models():
    """데이터 모델 검증"""
    console.print("\n[bold]4. 데이터 모델 검증[/bold]")

    try:
        from src.core.models import (
            DurationType,
            FrameAnalysis,
            VideoAnalysis,
            EditSegment,
            EditScript,
            PhotoCandidate,
            ProcessingResult
        )

        tests = []

        # DurationType
        try:
            dt = DurationType.from_duration(10)
            assert dt == DurationType.SHORT
            dt = DurationType.from_duration(25)
            assert dt == DurationType.MEDIUM
            tests.append(("DurationType.from_duration()", "OK"))
        except Exception as e:
            tests.append(("DurationType.from_duration()", f"{e}"))

        # FrameAnalysis
        try:
            fa = FrameAnalysis(
                timestamp=1.0,
                motion_level=0.5,
                composition_score=0.7,
                lighting="good",
                aesthetic_score=0.8,
                emotional_tone="determined",
                description="Test frame"
            )
            tests.append(("FrameAnalysis 생성", "OK"))
        except Exception as e:
            tests.append(("FrameAnalysis 생성", f"{e}"))

        # EditSegment
        try:
            es = EditSegment(
                start_time=0,
                end_time=2,
                source_start=0,
                source_end=3,
                speed=0.5,
                purpose="hook"
            )
            tests.append(("EditSegment 생성", "OK"))
        except Exception as e:
            tests.append(("EditSegment 생성", f"{e}"))

        table = Table(title="데이터 모델")
        table.add_column("테스트")
        table.add_column("결과")

        for test, result in tests:
            style = "green" if result == "OK" else "red"
            table.add_row(test, f"[{style}]{result}[/{style}]")

        console.print(table)
        return all(r == "OK" for _, r in tests)

    except Exception as e:
        console.print(f"[red]모델 import 실패: {e}[/red]")
        return False


def check_pipeline_init():
    """Pipeline 초기화 검증 (Mock 모드)"""
    console.print("\n[bold]5. Pipeline 초기화 검증 (Mock)[/bold]")

    try:
        from src.pipeline import VideoPipeline

        pipeline = VideoPipeline(use_mock=True)

        checks = [
            ("config", hasattr(pipeline, 'config')),
            ("video_analyzer", hasattr(pipeline, 'video_analyzer')),
            ("script_generator", hasattr(pipeline, 'script_generator')),
            ("renderer", hasattr(pipeline, 'renderer')),
            ("frame_selector", hasattr(pipeline, 'frame_selector')),
            ("photo_enhancer", hasattr(pipeline, 'photo_enhancer')),
        ]

        table = Table(title="Pipeline 컴포넌트")
        table.add_column("컴포넌트")
        table.add_column("상태")

        for comp, exists in checks:
            style = "green" if exists else "red"
            status = "OK" if exists else "Missing"
            table.add_row(comp, f"[{style}]{status}[/{style}]")

        console.print(table)
        return all(exists for _, exists in checks)

    except Exception as e:
        console.print(f"[red]Pipeline 초기화 실패: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


def main():
    console.print(Panel("[bold]AI Video Editor - 시스템 검증[/bold]", style="cyan"))

    results = {
        "모듈 Import": check_imports(),
        "설정 파일": check_configs(),
        "ConfigLoader": check_config_loading(),
        "데이터 모델": check_models(),
        "Pipeline 초기화": check_pipeline_init(),
    }

    # 최종 결과
    console.print("\n" + "=" * 50)
    console.print("[bold]최종 검증 결과[/bold]")
    console.print("=" * 50)

    all_passed = True
    for test, passed in results.items():
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        console.print(f"  {test}: {status}")
        if not passed:
            all_passed = False

    console.print("=" * 50)

    if all_passed:
        console.print("\n[bold green]모든 검증 통과! 시스템이 정상입니다.[/bold green]")
        console.print("\n[dim]테스트 실행: python main.py test.mp4 -d 10 --mock[/dim]")
        return 0
    else:
        console.print("\n[bold red]일부 검증 실패. 위 오류를 확인하세요.[/bold red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
