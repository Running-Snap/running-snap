"""
run_pose_analysis.py
====================
자세 분석 텍스트 → 영상 자동 편집 파이프라인 (front_side_view 기반).

사용법:
    # 기본 (TTS 없음, 자막 읽기 시간 기반 영상 길이 자동 조정)
    python run_pose_analysis.py --video test-road.mp4 --analysis data/sample_pose_analysis.txt

    # TTS 음성 포함 (선택)
    python run_pose_analysis.py --video test-road.mp4 --analysis data/sample_pose_analysis.txt --tts

    # 출력 경로 지정
    python run_pose_analysis.py --video test-road.mp4 --analysis data/sample_pose_analysis.txt --output result.mp4

흐름:
    1. 분석 텍스트 파싱  →  구조화 JSON
    2. JSON → EditInstruction (자막 읽기 시간 기반 peak/replay 길이 동적 계산)
    3. TemplateExecutor → 영상 렌더링
    4. (--tts 옵션 시) gTTS → 세그먼트별 mp3 → CompositeAudioClip 합성
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── 의존성 확인 ──────────────────────────────────────────────────
try:
    from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
    HAS_MOVIEPY = True
except ImportError:
    HAS_MOVIEPY = False

try:
    from gtts import gTTS
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

# ── 프로젝트 내부 모듈 ───────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from src.pose_analysis_parser   import PoseAnalysisParser
from src.pose_to_template       import PoseToTemplate
from src.pose_to_chronological  import PoseToChronological
from src.template_executor      import TemplateExecutor


# ──────────────────────────────────────────────────────────────────
# TTS 생성
# ──────────────────────────────────────────────────────────────────

def _save_srt(instruction: dict, srt_path: str) -> None:
    """EditInstruction의 overlays에서 issue/correction 자막을 SRT 파일로 저장.

    호환성:
    - utf-8-sig (BOM 포함): VLC / QuickTime / Windows Media Player / 자막 편집기 전부 인식
    - CRLF 줄 끝: SRT 표준 + Windows 호환
    - prefix 필터: top3 모드(issue_/correction_) + chrono 모드(corr_) 모두 포함
    """
    total = instruction["meta"]["target_duration_seconds"]

    # top3: issue_N / correction_N   |   chrono: issue_NN / corr_NN
    subtitle_ovs = [
        ov for ov in instruction["overlays"]
        if ov["id"].startswith(("issue_", "correction_", "corr_"))
    ]
    subtitle_ovs.sort(key=lambda o: o["start_ratio"])

    def to_srt_time(sec: float) -> str:
        total_ms = int(round(sec * 1000))
        ms = total_ms % 1000
        s  = (total_ms // 1000) % 60
        m  = (total_ms // 60000) % 60
        h  = total_ms // 3600000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, ov in enumerate(subtitle_ovs, 1):
        start = ov["start_ratio"] * total
        end   = ov["end_ratio"]   * total
        text  = ov["content"]
        lines.append(str(i))
        lines.append(f"{to_srt_time(start)} --> {to_srt_time(end)}")
        lines.append(text)
        lines.append("")          # 블록 구분 빈 줄

    # utf-8-sig = BOM 포함 UTF-8, newline="\r\n" = CRLF (SRT 표준)
    with open(srt_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("\n".join(lines))


def _make_tts_audio(tts_script: list, tmpdir: str) -> list:
    """tts_script 항목마다 mp3 생성 → [{path, start_sec}, ...] 반환"""
    if not HAS_TTS:
        print("  [TTS] gtts 없음 — TTS 건너뜀")
        return []

    audio_files = []
    for i, seg in enumerate(tts_script):
        mp3_path = os.path.join(tmpdir, f"tts_{i:02d}.mp3")
        try:
            tts = gTTS(text=seg["text"], lang=seg.get("lang", "ko"), slow=False)
            tts.save(mp3_path)
            audio_files.append({"path": mp3_path, "start_sec": seg["start_sec"]})
            print(f"  [TTS] {i+1}/{len(tts_script)}: {seg['text'][:30]}...")
        except Exception as e:
            print(f"  [TTS] {i+1} 실패: {e}")
    return audio_files


# ──────────────────────────────────────────────────────────────────
# 오디오 합성
# ──────────────────────────────────────────────────────────────────

def _composite_audio(video_path: str, audio_files: list, output_path: str):
    """TTS mp3 파일들을 영상에 합성"""
    if not audio_files:
        shutil.copy(video_path, output_path)
        return

    video = VideoFileClip(video_path)
    clips = []
    for af in audio_files:
        start = af["start_sec"]
        if start >= video.duration:
            continue
        ac = AudioFileClip(af["path"]).with_start(start)
        # 영상 길이 초과 방지
        max_dur = video.duration - start
        if ac.duration > max_dur:
            ac = ac.subclipped(0, max_dur)
        clips.append(ac)

    if clips:
        composite = CompositeAudioClip(clips)
        video = video.with_audio(composite)

    video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset="medium",
        threads=4,
        logger=None,
    )
    video.close()


# ──────────────────────────────────────────────────────────────────
# 메인 파이프라인
# ──────────────────────────────────────────────────────────────────

def run(
    video: str,
    analysis_path: str,
    output: str | None,
    no_tts: bool,
    max_sections: int,
    mode: str = "chrono",   # "chrono" | "top3"
    use_skeleton: bool = True,
):

    # ── 출력 경로 결정 ──────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(video).stem
    out_dir = Path("outputs/videos")
    out_dir.mkdir(parents=True, exist_ok=True)
    final_output = output or str(out_dir / f"{stem}_pose_{ts}.mp4")

    print("=" * 60)
    print("  자세 분석 영상 자동 편집")
    print("=" * 60)
    print(f"  원본 영상 : {video}")
    print(f"  분석 파일 : {analysis_path}")
    print(f"  모드      : {mode}  ({'전체 finding 순차' if mode == 'chrono' else 'Top-3 섹션'})")
    print(f"  TTS       : {'비활성화' if no_tts else ('사용' if HAS_TTS else '없음(gtts 미설치)')}")
    print(f"  출력      : {final_output}")
    print()

    # ── Step 1: 분석 텍스트 파싱 ────────────────────────────────
    print("[1/5] 분석 텍스트 파싱...")
    parser = PoseAnalysisParser()
    analysis = parser.parse_file(analysis_path)

    for s in analysis["sections"]:
        print(f"      Rank {s['rank']}: {s['title']}  ({len(s['findings'])}건)")

    # 파싱 결과 JSON 저장 (디버깅용)
    parsed_path = str(out_dir / f"{stem}_pose_parsed_{ts}.json")
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"      → 파싱 JSON: {parsed_path}")

    # ── Step 2: EditInstruction + TTS 스크립트 생성 ─────────────
    print("[2/5] EditInstruction 생성...")
    if mode == "chrono":
        converter = PoseToChronological()
    else:
        converter = PoseToTemplate()
        converter.MAX_SECTIONS = max_sections

    # 소스 영상 길이 가져오기
    try:
        from moviepy import VideoFileClip as _VFC
        _v = _VFC(video)
        src_dur = _v.duration
        _v.close()
    except Exception:
        src_dur = 999.0

    instruction, tts_script = converter.convert(analysis, source_duration=src_dur)

    instr_path = str(out_dir / f"{stem}_pose_instruction_{ts}.json")
    with open(instr_path, "w", encoding="utf-8") as f:
        json.dump(instruction, f, ensure_ascii=False, indent=2)
    srt_path = str(out_dir / f"{stem}_pose_{ts}.srt")
    _save_srt(instruction, srt_path)

    print(f"      목표 길이: {instruction['meta']['target_duration_seconds']}s")
    print(f"      세그먼트: {len(instruction['timeline']['segments'])}개")
    print(f"      오버레이: {len(instruction['overlays'])}개")
    print(f"      TTS 항목: {len(tts_script)}개")
    print(f"      → 지시서 JSON: {instr_path}")
    print(f"      → 자막 SRT  : {srt_path}")

    # ── Step 3 & 4: 렌더링 + TTS ────────────────────────────────
    use_tts = (not no_tts) and HAS_TTS and tts_script

    if use_tts:
        with tempfile.TemporaryDirectory() as tmpdir:
            silent_path = os.path.join(tmpdir, "silent.mp4")

            print("[3/5] 영상 렌더링 (무음)...")
            executor = TemplateExecutor(verbose=True)
            executor.execute(instruction, video, silent_path)

            print("[4/5] TTS 음성 생성...")
            audio_files = _make_tts_audio(tts_script, tmpdir)

            print("[5/5] 오디오 합성...")
            _composite_audio(silent_path, audio_files, final_output)
    else:
        print("[3/5] 영상 렌더링...")
        executor = TemplateExecutor(verbose=True)
        executor.execute(instruction, video, final_output)
        print("[4/5] TTS 건너뜀")
        print("[5/5] 완료")

    # ── Step 6 (선택): MediaPipe 골격 오버레이 ──────────────────
    if use_skeleton:
        model_path = Path(__file__).parent / "models" / "pose_landmarker_full.task"
        if not model_path.exists():
            print(f"\n[Skeleton] 모델 파일 없음: {model_path}")
            print("  다운로드: curl -L -o models/pose_landmarker_full.task \\")
            print("    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task")
        else:
            from src.pose_skeleton_renderer import apply_skeleton_overlay
            skel_output = final_output.replace(".mp4", "_skeleton.mp4")
            print(f"\n[6] MediaPipe 골격 오버레이...")
            apply_skeleton_overlay(
                input_video=final_output,
                output_video=skel_output,
                instruction=instruction,
                parsed_json=analysis,
                model_path=str(model_path),
            )
            final_output = skel_output

    # ── 결과 출력 ────────────────────────────────────────────────
    size_mb = Path(final_output).stat().st_size / 1024 / 1024
    print()
    print("=" * 60)
    print(f"  완료!  {size_mb:.1f} MB")
    print(f"  → {final_output}")
    print("=" * 60)


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="자세 분석 영상 자동 편집")
    ap.add_argument("--video",    required=True,  help="원본 영상 경로")
    ap.add_argument("--analysis", required=True,  help="자세 분석 텍스트 파일 경로")
    ap.add_argument("--output",   default=None,   help="출력 경로 (기본: outputs/videos/자동 생성)")
    ap.add_argument("--tts",      action="store_true", help="TTS 음성 생성 활성화 (기본: 비활성)")
    ap.add_argument("--sections", type=int, default=3, help="사용할 상위 섹션 수 (기본 3, top3 모드만 적용)")
    ap.add_argument(
        "--mode",
        choices=["chrono", "top3"],
        default="chrono",
        help="편집 모드: chrono=전체 finding 순차(기본), top3=상위 3개 섹션",
    )
    ap.add_argument("--skeleton", action="store_true",
                    help="MediaPipe 골격 오버레이 추가 (모델 필요)")
    ap.add_argument("--no-skeleton", action="store_true",
                    help="골격 오버레이 비활성화")
    args = ap.parse_args()

    run(
        video=args.video,
        analysis_path=args.analysis,
        output=args.output,
        no_tts=not args.tts,
        max_sections=args.sections,
        mode=args.mode,
        use_skeleton=args.skeleton and not args.no_skeleton,
    )


if __name__ == "__main__":
    main()
