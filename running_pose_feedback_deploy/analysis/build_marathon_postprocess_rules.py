"""
Marathon_good_pose → pose_pipeline post-processing → phase reference → calibrated rules.

Outputs:
  analysis/results_marathon_postprocess_pose/{video}/person_1_elbow_angles.csv
  analysis/results_marathon_postprocess_profiles/
  analysis/reference_marathon_postprocess/
    normal_phase_reference.csv, cadence_reference.json, pose_rules.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_normal_reference import (  # noqa: E402
    build_cadence_reference,
    build_phase_reference,
    write_phase_reference_csv,
)
from normal_pose_reference import (  # noqa: E402
    load_phase_profiles,
    load_phase_reference,
    parse_float,
    score_phase_profile,
    write_json,
)
from plot_normal_phase_profiles import process_video_dir  # noqa: E402
from pose_pipeline.pose_estimation import extract_keypoints  # noqa: E402
from pose_pipeline.postprocess import PosePostProcessor  # noqa: E402
from pose_pipeline.track_export import keypoints_to_track_rows, write_track_csv  # noqa: E402
from pose_pipeline.video import load_video  # noqa: E402
from four_axis_metrics import (  # noqa: E402
    FOUR_AXES,
    load_track_and_metrics,
)
from legacy_phase_rules import calibrate_legacy_rules, classify_legacy_phase, save_legacy_rules  # noqa: E402
from pose_rules import classify_four_axis, save_pose_rules  # noqa: E402
from segment_running_cycles import (  # noqa: E402
    METRIC_FIELDS,
    choose_cycle_signal,
    detect_cycles,
    read_track_csv,
)


def find_marathon_videos(root: Path) -> list[Path]:
    videos: list[Path] = []
    for ext in ("*.mp4", "*.mov", "*.MP4", "*.MOV"):
        videos.extend(root.rglob(ext))
    return sorted(set(videos))


def video_output_name(video_path: Path) -> str:
    return f"{video_path.parent.name}_{video_path.stem}"


def export_postprocess_track(
    video_path: Path,
    out_dir: Path,
    *,
    frame_stride: int,
    target_width: int,
) -> dict | None:
    """BlazePose → post-process → person_1_elbow_angles.csv."""
    video = load_video(video_path, target_width=target_width)
    frames = video.frames[::frame_stride]
    if len(frames) < 10:
        return None

    raw = extract_keypoints(frames)
    processed = PosePostProcessor(video.fps).process(raw)
    rows = keypoints_to_track_rows(
        processed,
        video.fps,
        frame_stride=frame_stride,
        person_id="1",
    )
    pose_dir = out_dir / video_output_name(video_path)
    pose_dir.mkdir(parents=True, exist_ok=True)
    csv_path = pose_dir / "person_1_elbow_angles.csv"
    write_track_csv(csv_path, rows)

    detected = sum(1 for r in rows if r.get("pose_detected") == "yes")
    return {
        "video": str(video_path),
        "video_dir": pose_dir.name,
        "frames": len(rows),
        "pose_detected_frames": detected,
        "csv": str(csv_path),
    }


def segment_video_cycles(
    pose_dir: Path,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
) -> dict | None:
    csv_path = pose_dir / "person_1_elbow_angles.csv"
    if not csv_path.exists():
        return None
    rows = read_track_csv(csv_path)
    if len(rows) < 8:
        return None
    times, signal, source = choose_cycle_signal(rows)
    cycles, _ = detect_cycles(
        times,
        signal,
        min_cycle_sec=min_cycle_sec,
        max_cycle_sec=max_cycle_sec,
    )
    if len(cycles) < 1:
        return None

    durations = [c.end_time_sec - c.start_time_sec for c in cycles]
    median_dur = float(np.median(durations))
    cadence = 60.0 / median_dur if median_dur > 0 else math.nan
    return {
        "video_dir": pose_dir.name,
        "person_id": "1",
        "cycles": len(cycles),
        "median_duration_sec": round(median_dur, 4),
        "median_cadence_spm": round(cadence, 2) if not math.isnan(cadence) else "",
        "signal_source": source,
    }


def symmetry_medians(pose_dir: Path) -> tuple[float | None, float | None]:
    csv_path = pose_dir / "person_1_elbow_angles.csv"
    rows = read_track_csv(csv_path)
    elbow, knee = [], []
    for row in rows:
        if row.get("pose_detected") != "yes":
            continue
        e = parse_float(row.get("elbow_symmetry_diff_deg", ""))
        k = parse_float(row.get("knee_symmetry_diff_deg", ""))
        if not math.isnan(e):
            elbow.append(e)
        if not math.isnan(k):
            knee.append(k)
    return (
        float(np.median(elbow)) if elbow else None,
        float(np.median(knee)) if knee else None,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build post-processed Marathon reference + pose rules")
    parser.add_argument("--input", type=Path, default=Path("Marathon_good_pose"))
    parser.add_argument(
        "--pose-dir",
        type=Path,
        default=Path("analysis/results_marathon_postprocess_pose"),
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("analysis/results_marathon_postprocess_profiles"),
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("analysis/reference_marathon_postprocess"),
    )
    parser.add_argument("--frame-stride", type=int, default=3)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--min-cycles", type=int, default=2)
    parser.add_argument("--min-cycle-sec", type=float, default=0.45)
    parser.add_argument("--max-cycle-sec", type=float, default=1.8)
    parser.add_argument("--calibration-percentile", type=float, default=95.0)
    parser.add_argument("--skip-pose", action="store_true", help="Reuse existing pose CSVs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.pose_dir.mkdir(parents=True, exist_ok=True)
    args.profiles_dir.mkdir(parents=True, exist_ok=True)
    args.reference_dir.mkdir(parents=True, exist_ok=True)

    videos = find_marathon_videos(args.input)
    if not videos:
        raise RuntimeError(f"No videos under {args.input}")

    # --- 1) Pose + post-process export ---
    export_rows: list[dict] = []
    if not args.skip_pose:
        for index, video_path in enumerate(videos, 1):
            print(f"[pose {index}/{len(videos)}] {video_path.name}")
            summary = export_postprocess_track(
                video_path,
                args.pose_dir,
                frame_stride=args.frame_stride,
                target_width=args.width,
            )
            if summary:
                export_rows.append(summary)
        with (args.pose_dir / "export_summary.csv").open("w", newline="", encoding="utf-8") as f:
            if export_rows:
                writer = csv.DictWriter(f, fieldnames=list(export_rows[0].keys()))
                writer.writeheader()
                writer.writerows(export_rows)
    else:
        print("Skipping pose export (--skip-pose)")

    pose_dirs = sorted(p for p in args.pose_dir.iterdir() if p.is_dir() and (p / "person_1_elbow_angles.csv").exists())

    # --- 2) Cycle summary ---
    cycle_rows: list[dict] = []
    for pose_dir in pose_dirs:
        row = segment_video_cycles(
            pose_dir,
            min_cycle_sec=args.min_cycle_sec,
            max_cycle_sec=args.max_cycle_sec,
        )
        if row:
            cycle_rows.append(row)
    cycles_csv = args.pose_dir / "cycle_segmentation_summary.csv"
    if cycle_rows:
        with cycles_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(cycle_rows[0].keys()))
            writer.writeheader()
            writer.writerows(cycle_rows)

    # --- 3) Phase profiles ---
    profile_summaries: list[dict] = []
    skipped: list[str] = []
    for pose_dir in pose_dirs:
        summary = process_video_dir(
            pose_dir,
            args.profiles_dir,
            min_cycle_sec=args.min_cycle_sec,
            max_cycle_sec=args.max_cycle_sec,
            min_cycles=args.min_cycles,
            show_individual_cycles=False,
        )
        if summary is None:
            skipped.append(pose_dir.name)
            continue
        profile_summaries.append(summary)
        print(f"  profile OK: {pose_dir.name} ({summary['cycles']} cycles)")

    if not profile_summaries:
        raise RuntimeError("No phase profiles built; check min_cycles or pose export")

    # --- 4) Global reference ---
    profile_rows = load_phase_profiles(args.profiles_dir)
    reference = build_phase_reference(profile_rows)
    write_phase_reference_csv(args.reference_dir / "normal_phase_reference.csv", reference)

    cadence_ref = build_cadence_reference(cycles_csv) if cycles_csv.exists() else {}
    if cadence_ref:
        write_json(args.reference_dir / "cadence_reference.json", cadence_ref)

    ref_lookup = load_phase_reference(args.reference_dir / "normal_phase_reference.csv")

    # --- 5) 4-axis metrics + calibrate rules ---
    from four_axis_metrics import calibrate_four_axis_rules

    calibration: list[dict] = []
    axis_samples: list[dict] = []
    legacy_scores: list[float] = []

    for pose_dir in pose_dirs:
        profile_csv = args.profiles_dir / pose_dir.name / f"{pose_dir.name}_normal_phase_profile.csv"
        if not profile_csv.exists():
            continue
        prof_rows = list(csv.DictReader(profile_csv.open(encoding="utf-8")))
        profile = [
            {"metric": r["metric"], "phase_pct": parse_float(r["phase_pct"]), "mean": parse_float(r["mean"])}
            for r in prof_rows
        ]
        report = score_phase_profile(
            profile,
            ref_lookup,
            video_name=pose_dir.name,
            person_id="1",
            severity_threshold=0.5,
        )
        cadence_spm = None
        for crow in cycle_rows:
            if crow["video_dir"] == pose_dir.name:
                cadence_spm = parse_float(str(crow.get("median_cadence_spm", "")))
                break

        four_axis = load_track_and_metrics(pose_dir, report, cadence_spm)
        axis_samples.append(four_axis)
        legacy_scores.append(float(report["overall_deviation_score"]))

        calibration.append(
            {
                "video_dir": pose_dir.name,
                "cadence_spm": cadence_spm if cadence_spm is not None and not math.isnan(cadence_spm) else "",
                "arm_swing_severity": four_axis["arm_swing"]["severity"],
                "stride_severity": four_axis["stride"]["severity"],
                "foot_strike_severity": four_axis["foot_strike"]["severity"],
                "overstride_forward_max": four_axis["stride"].get("overstride_forward_max", ""),
            }
        )

    rules = calibrate_four_axis_rules(
        axis_samples,
        cadence_ref=cadence_ref,
        percentile=args.calibration_percentile,
        method="pose_pipeline postprocess + 4-axis (cadence|arm_swing|stride|foot_strike)",
    )
    save_pose_rules(args.reference_dir / "pose_rules.json", rules)

    legacy_rules = calibrate_legacy_rules(
        legacy_scores,
        percentile=args.calibration_percentile,
        method="postprocess phase — 4 joint metrics (L/R elbow, L/R knee) p10-p90",
        n_videos=len(legacy_scores),
    )
    save_legacy_rules(args.reference_dir / "pose_rules_legacy.json", legacy_rules)

    for row in calibration:
        pose_dir = args.pose_dir / row["video_dir"]
        profile_csv = args.profiles_dir / row["video_dir"] / f"{row['video_dir']}_normal_phase_profile.csv"
        prof_rows = list(csv.DictReader(profile_csv.open(encoding="utf-8")))
        profile = [
            {"metric": r["metric"], "phase_pct": parse_float(r["phase_pct"]), "mean": parse_float(r["mean"])}
            for r in prof_rows
        ]
        report = score_phase_profile(profile, ref_lookup, video_name=row["video_dir"], person_id="1")
        c = classify_four_axis(
            report,
            rules,
            pose_dir=pose_dir,
            cadence_spm=parse_float(str(row["cadence_spm"])) if row["cadence_spm"] != "" else None,
        )
        row["predicted_calibrated"] = c["predicted"]
        row["abnormal_axes"] = c["abnormal_axis_count"]
        row["triggers"] = ";".join(c["triggers"])
        row["primary_axis"] = c.get("primary_axis_ko", "")
        leg = classify_legacy_phase(report, legacy_rules)
        row["predicted_legacy"] = leg["predicted"]

    cal_csv = args.reference_dir / "marathon_calibration_scores.csv"
    with cal_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(calibration[0].keys()))
        writer.writeheader()
        writer.writerows(calibration)

    n_flagged = sum(1 for r in calibration if r["predicted_calibrated"] == "나쁜 자세")
    metadata = {
        "dataset": "Marathon_good_pose",
        "method": rules.method,
        "n_videos_total": len(videos),
        "n_pose_exported": len(pose_dirs),
        "n_phase_profiles": len(profile_summaries),
        "n_skipped_profiles": len(skipped),
        "skipped": skipped,
        "frame_stride": args.frame_stride,
        "pose_rules": rules.to_dict(),
        "pose_rules_legacy": legacy_rules.to_dict(),
        "cadence_reference": cadence_ref,
    }
    write_json(args.reference_dir / "reference_metadata.json", metadata)

    print("\n=== Marathon post-process rules ===")
    print(f"Reference: {args.reference_dir}")
    print(f"  phase cells: {len(reference)}")
    print(f"  profiles: {len(profile_summaries)} / {len(pose_dirs)} pose dirs")
    print(f"  4-axis rules v{rules.version}  min_axes_abnormal={rules.min_axes_abnormal}")
    for ax in FOUR_AXES:
        print(f"    {ax}: {rules.axes.get(ax, {})}")
    print(f"  Marathon flagged as bad (sanity): {n_flagged}/{len(calibration)}")
    print(f"  Legacy threshold (4-metric): {legacy_rules.bad_score_threshold}")
    print(f"  Rules: {args.reference_dir / 'pose_rules.json'}")
    print(f"  Legacy: {args.reference_dir / 'pose_rules_legacy.json'}")
    print(f"  Calibration CSV: {cal_csv}")


if __name__ == "__main__":
    main()
