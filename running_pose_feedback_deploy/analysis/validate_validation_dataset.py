from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from initial_box_track_elbow_metrics import analyze_video  # noqa: E402
from plot_normal_phase_profiles import process_video_dir  # noqa: E402
from normal_pose_reference import (  # noqa: E402
    build_marginal_reference,
    load_phase_reference,
    load_user_phase_profile_csv,
    score_marginal_track,
    score_phase_profile,
    write_json,
)
from score_pose_deviation import score_cadence  # noqa: E402

TRACK_CYCLE = "cycle"
TRACK_NOCYCLE = "nocycle"


def collect_videos(root: Path) -> list[Path]:
    suffixes = {".mp4", ".mov", ".MP4", ".MOV"}
    return sorted(p for p in root.rglob("*") if p.suffix in suffixes)


def parse_label_category(video_path: Path, validation_root: Path) -> tuple[str, str]:
    rel = video_path.relative_to(validation_root)
    parts = rel.parts
    label = parts[0] if parts else "unknown"
    category = parts[1] if len(parts) > 2 else ""
    return label, category


def video_output_name(video_path: Path) -> str:
    return f"{video_path.parent.name}_{video_path.stem}"


def find_pose_dir(pose_output: Path, video_path: Path) -> Path | None:
    expected = video_output_name(video_path)
    direct = pose_output / expected
    if direct.is_dir():
        return direct
    stem = video_path.stem
    for path in pose_output.iterdir():
        if not path.is_dir():
            continue
        if path.name == expected or path.name.endswith(f"_{stem}") or stem in path.name:
            return path
    return None


def find_profile_csv(profile_output: Path, out_name: str) -> Path | None:
    direct = profile_output / out_name / f"{out_name}_normal_phase_profile.csv"
    if direct.exists():
        return direct
    matches = list(profile_output.glob(f"**/{out_name}_normal_phase_profile.csv"))
    return matches[0] if matches else None


def base_row(video_path: Path, label: str, category: str, out_name: str) -> dict[str, str]:
    return {
        "video": video_path.name,
        "label": label,
        "category": category,
        "output_name": out_name,
        "track": "",
        "status": "",
        "scoring_mode": "",
        "person_id": "",
        "cycles": "",
        "overall_score": "",
        "outside_band": "",
        "n_issues": "",
        "top_issue": "",
    }


def report_to_row(row: dict[str, str], report: dict, profile_summary: dict[str, str] | None = None) -> dict[str, str]:
    row["status"] = report.get("status", "ok")
    row["scoring_mode"] = report.get("scoring_mode", row.get("scoring_mode", ""))
    row["person_id"] = str(report.get("person_id", ""))
    row["overall_score"] = str(report.get("overall_deviation_score", ""))
    row["outside_band"] = str(report.get("outside_band_count", ""))
    issues = report.get("detected_issues", [])
    row["n_issues"] = str(len(issues))
    row["top_issue"] = issues[0]["label_ko"] if issues else ""
    if profile_summary:
        row["cycles"] = str(profile_summary.get("cycles", ""))
    return row


def write_summary_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    fieldnames = sorted({k for r in rows for k in r})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def print_track_stats(rows: list[dict[str, str]], track_name: str) -> None:
    ok_rows = [r for r in rows if r.get("status") == "ok" and r.get("overall_score")]
    if not ok_rows:
        print(f"  [{track_name}] no scored rows")
        return
    for group_label in ("좋은 자세", "나쁜 자세"):
        group = [r for r in ok_rows if r.get("label") == group_label]
        if not group:
            continue
        scores = [float(r["overall_score"]) for r in group]
        print(
            f"  [{track_name}] {group_label}: n={len(group)}  "
            f"mean={sum(scores) / len(scores):.3f}  "
            f"min={min(scores):.3f}  max={max(scores):.3f}"
        )


def plot_confusion_matrices(score_output: Path, nocycle_csv: Path) -> None:
    """Binary confusion matrix — nocycle track only (no gait cycle)."""
    plot_script = SCRIPT_DIR / "plot_validation_results.py"
    if not plot_script.exists() or not nocycle_csv.exists():
        return
    subprocess.run(
        [
            sys.executable,
            str(plot_script),
            "--summary",
            str(nocycle_csv),
            "--track",
            "nocycle",
            "--output",
            str(score_output / "validation_confusion_matrix_binary.png"),
            "--metrics-csv",
            str(score_output / "validation_confusion_metrics_binary.csv"),
        ],
        check=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate validation_Data: cycle track (phase) + nocycle track (marginal)."
    )
    parser.add_argument("--input", type=Path, default=Path("validation_Data"))
    parser.add_argument(
        "--pose-output",
        type=Path,
        default=Path("analysis/results_validation_pose_stride3"),
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        default=Path("analysis/results_validation_phase_profiles"),
    )
    parser.add_argument(
        "--score-output",
        type=Path,
        default=Path("analysis/results_validation_scoring"),
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("analysis/reference_marathon_good_pose"),
    )
    parser.add_argument("--frame-stride", type=int, default=3)
    parser.add_argument("--min-cycles", type=int, default=1)
    parser.add_argument("--severity-threshold", type=float, default=0.5)
    parser.add_argument("--skip-pose", action="store_true")
    parser.add_argument("--skip-profile", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    videos = collect_videos(args.input)
    if not videos:
        raise RuntimeError(f"No videos under {args.input}")

    ref_csv = args.reference_dir / "normal_phase_reference.csv"
    if not ref_csv.exists():
        raise RuntimeError(f"Missing reference: {ref_csv}")

    reference_lookup = load_phase_reference(ref_csv)
    marginal_ref = build_marginal_reference(reference_lookup)
    cadence_ref_path = args.reference_dir / "cadence_reference.json"
    cadence_ref = (
        json.loads(cadence_ref_path.read_text(encoding="utf-8")) if cadence_ref_path.exists() else {}
    )

    args.pose_output.mkdir(parents=True, exist_ok=True)
    args.profile_output.mkdir(parents=True, exist_ok=True)
    args.score_output.mkdir(parents=True, exist_ok=True)

    cycle_rows: list[dict[str, str]] = []
    nocycle_rows: list[dict[str, str]] = []

    for index, video_path in enumerate(videos, start=1):
        label, category = parse_label_category(video_path, args.input)
        out_name = video_output_name(video_path)
        pose_dir = find_pose_dir(args.pose_output, video_path)
        if pose_dir is None and not args.skip_pose:
            pose_dir = args.pose_output / out_name
        elif pose_dir is not None:
            out_name = pose_dir.name

        print(f"[{index}/{len(videos)}] {video_path.name} ({label}/{category})")

        if not args.skip_pose:
            try:
                analyze_video(
                    video_path,
                    args.pose_output,
                    frame_stride=args.frame_stride,
                    min_visibility=0.5,
                    process_width=960,
                    min_box_area=20000,
                    crop_padding=0.15,
                    init_scan_frames=5,
                    max_distance_ratio=1.2,
                    reuse_last_box_frames=30,
                    debug_video=False,
                )
                pose_dir = find_pose_dir(args.pose_output, video_path) or pose_dir
                if pose_dir is not None:
                    out_name = pose_dir.name
            except Exception as exc:
                fail = base_row(video_path, label, category, out_name)
                fail["status"] = "pose_failed"
                fail["top_issue"] = str(exc)
                cycle_rows.append({**fail, "track": TRACK_CYCLE})
                nocycle_rows.append({**fail, "track": TRACK_NOCYCLE})
                continue

        if pose_dir is None or not pose_dir.exists():
            fail = base_row(video_path, label, category, out_name)
            fail["status"] = "no_pose_dir"
            cycle_rows.append({**fail, "track": TRACK_CYCLE})
            nocycle_rows.append({**fail, "track": TRACK_NOCYCLE})
            continue

        score_dir = args.score_output / out_name
        score_dir.mkdir(parents=True, exist_ok=True)

        # --- Track B: nocycle (marginal median, no gait cycle required) ---
        nocycle_row = base_row(video_path, label, category, out_name)
        nocycle_row["track"] = TRACK_NOCYCLE
        nocycle_report = score_marginal_track(
            pose_dir,
            marginal_ref,
            video_name=out_name,
            person_id="",
        )
        if nocycle_report.get("status") == "ok":
            nocycle_report["scoring_mode"] = "marginal_median"
            write_json(score_dir / "deviation_report_nocycle.json", nocycle_report)
            report_to_row(nocycle_row, nocycle_report)
            print(
                f"  [nocycle] score={nocycle_report['overall_deviation_score']:.3f}  "
                f"issues={len(nocycle_report.get('detected_issues', []))}"
            )
        else:
            nocycle_row["status"] = nocycle_report.get("status", "marginal_failed")
        nocycle_rows.append(nocycle_row)

        # --- Track A: cycle (phase profile, requires gait cycles) ---
        cycle_row = base_row(video_path, label, category, out_name)
        cycle_row["track"] = TRACK_CYCLE

        if args.skip_profile:
            profile_csv = find_profile_csv(args.profile_output, out_name)
            profile_summary = {"cycles": ""} if profile_csv else None
        else:
            profile_summary = process_video_dir(
                pose_dir,
                args.profile_output,
                min_cycle_sec=0.45,
                max_cycle_sec=1.8,
                min_cycles=args.min_cycles,
                show_individual_cycles=False,
            )
            profile_csv = find_profile_csv(args.profile_output, out_name) if profile_summary else None

        if profile_summary is None or profile_csv is None:
            cycle_row["status"] = "insufficient_cycles"
            cycle_row["scoring_mode"] = "cycle_phase"
            cycle_rows.append(cycle_row)
            print("  [cycle] insufficient_cycles")
            continue

        video_name, person_id, profile_rows = load_user_phase_profile_csv(profile_csv)
        cycle_report = score_phase_profile(
            profile_rows,
            reference_lookup,
            video_name=video_name,
            person_id=person_id,
            severity_threshold=args.severity_threshold,
        )
        cycle_report["scoring_mode"] = "cycle_phase"

        cycles_summary = pose_dir / "cycle_segmentation_summary.csv"
        if not cycles_summary.exists():
            alt = list(pose_dir.glob("**/cycle_segmentation_summary.csv"))
            cycles_summary = alt[0] if alt else cycles_summary
        if cadence_ref and cycles_summary.exists():
            cadence_score = score_cadence(person_id, cycles_summary, cadence_ref, video_name)
            if cadence_score:
                cycle_report["cadence"] = cadence_score

        write_json(score_dir / "deviation_report_cycle.json", cycle_report)
        report_to_row(cycle_row, cycle_report, profile_summary)
        cycle_rows.append(cycle_row)
        print(
            f"  [cycle] score={cycle_report['overall_deviation_score']:.3f}  "
            f"cycles={profile_summary.get('cycles', '?')}  "
            f"issues={len(cycle_report.get('detected_issues', []))}"
        )

    cycle_csv = args.score_output / "validation_summary_cycle.csv"
    nocycle_csv = args.score_output / "validation_summary_nocycle.csv"
    write_summary_csv(cycle_csv, cycle_rows)
    write_summary_csv(nocycle_csv, nocycle_rows)

    # Legacy combined summary (nocycle preferred when cycle missing)
    combined: list[dict[str, str]] = []
    nocycle_by_video = {r["output_name"]: r for r in nocycle_rows}
    for cycle_row in cycle_rows:
        name = cycle_row["output_name"]
        if cycle_row.get("status") == "ok":
            combined.append(cycle_row)
        elif name in nocycle_by_video and nocycle_by_video[name].get("status") == "ok":
            combined.append(nocycle_by_video[name])
        else:
            combined.append(cycle_row)
    write_summary_csv(args.score_output / "validation_summary.csv", combined)

    print(f"\nCycle track:   {cycle_csv}")
    print(f"No-cycle track: {nocycle_csv}")
    print_track_stats(cycle_rows, TRACK_CYCLE)
    print_track_stats(nocycle_rows, TRACK_NOCYCLE)

    plot_confusion_matrices(args.score_output, nocycle_csv)


if __name__ == "__main__":
    main()
