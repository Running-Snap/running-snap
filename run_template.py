"""
템플릿 기반 영상 편집 CLI

─── 터미널에서 바로 사용하는 법 ───────────────────────────────────────
# VSCode 터미널에서 video-editor 폴더 열고:

  # 기본 (캡컷 실험 템플릿)
  python run_template.py

  # 영상 + 템플릿 직접 지정
  python run_template.py --video test-move.MOV --template templates/capcut_run_v1.json

  # searchingmodule이 만든 실제 템플릿
  python run_template.py --video test-move.MOV --template ../searchingmodule/template_factory/data/exports/edit_instruction_088e50dd_20250302.json

  # 출력 경로까지 지정
  python run_template.py --video my_run.mp4 --template edit_instruction_XXX.json --output result.mp4

─── searchingmodule Python 연동 ────────────────────────────────────────
  from src.template_executor import apply_template
  apply_template(instruction_dict, "my_run.mp4", "output/result.mp4")
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.template_executor import TemplateExecutor


def main():
    parser = argparse.ArgumentParser(
        description="템플릿 기반 영상 자동 편집",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--video",    default="test-move.MOV",
                        help="원본 영상 경로 (기본: test-move.MOV)")
    parser.add_argument("--template", default="templates/capcut_run_v1.json",
                        help="EditInstruction JSON 경로")
    parser.add_argument("--output",   default=None,
                        help="출력 경로 (기본: outputs/videos/[영상]_[템플릿ID]_[시간].mp4)")
    args = parser.parse_args()

    # 경로 정리
    video_path = Path(args.video)
    template_path = Path(args.template)

    if not video_path.exists():
        print(f"[오류] 영상 파일 없음: {video_path}")
        sys.exit(1)
    if not template_path.exists():
        print(f"[오류] 템플릿 파일 없음: {template_path}")
        sys.exit(1)

    # 템플릿 로드
    with open(template_path, encoding="utf-8") as f:
        instruction = json.load(f)

    # 출력 경로
    if args.output:
        output_path = args.output
    else:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        tid = instruction.get("template_id", template_path.stem)
        output_path = f"outputs/videos/{video_path.stem}_{tid}_{ts}.mp4"

    print("=" * 60)
    print("  템플릿 기반 영상 자동 편집")
    print("=" * 60)
    print(f"  원본 영상 : {video_path}")
    print(f"  템플릿    : {template_path}")
    print(f"  템플릿 ID : {instruction.get('template_id', '-')}")
    print(f"  목표 길이 : {instruction['meta']['target_duration_seconds']}초")
    print(f"  스타일    : {instruction['meta'].get('color_grade', '-')}")
    print(f"  태그      : {', '.join(instruction['meta'].get('vibe_tags', []))}")
    print(f"  출력      : {output_path}")
    print("=" * 60)
    print()

    # 실행
    executor = TemplateExecutor(verbose=True)
    success = executor.execute(
        instruction=instruction,
        input_video=str(video_path),
        output_video=output_path
    )

    if success:
        import os
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print()
        print("=" * 60)
        print(f"  완료! 파일 크기: {size_mb:.1f} MB")
        print(f"  → {output_path}")
        print("=" * 60)
    else:
        print("[실패] 편집 중 오류 발생")
        sys.exit(1)


if __name__ == "__main__":
    main()
