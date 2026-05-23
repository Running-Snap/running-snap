from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from segment_running_cycles import (  # noqa: E402
    METRIC_FIELDS,
    CycleSegment,
    choose_cycle_signal,
    configure_plot_fonts,
    detect_cycles,
    parse_float,
    read_track_csv,
)

PLOT_METRICS = [
    "left_elbow_deg",
    "right_elbow_deg",
    "left_knee_deg",
    "right_knee_deg",
    "torso_lean_deg",
]

METRIC_LABELS = {
    "left_elbow_deg": "Left elbow (deg)",
    "right_elbow_deg": "Right elbow (deg)",
    "left_knee_deg": "Left knee (deg)",
    "right_knee_deg": "Right knee (deg)",
    "torso_lean_deg": "Torso lean (deg)",
    "elbow_symmetry_diff_deg": "Elbow symmetry diff (deg)",
    "knee_symmetry_diff_deg": "Knee symmetry diff (deg)",
}

PHASE_GRID = np.linspace(0.0, 100.0, 101)


def resample_cycle_to_phase(
    rows: list[dict[str, str]],
    cycle: CycleSegment,
    metric_key: str,
) -> np.ndarray | None:
    segment_rows = rows[cycle.start_idx : cycle.end_idx + 1]
    times = np.array([parse_float(row["time_sec"]) for row in segment_rows], dtype=float)
    values = np.array([parse_float(row.get(metric_key, "nan")) for row in segment_rows], dtype=float)
    valid = ~np.isnan(values)
    if valid.sum() < 2:
        return None
    times = times[valid]
    values = values[valid]
    duration = max(times[-1] - times[0], 1e-6)
    phase = (times - times[0]) / duration * 100.0
    order = np.argsort(phase)
    phase = phase[order]
    values = values[order]
    return np.interp(PHASE_GRID, phase, values)


def collect_person_cycles(
    csv_path: Path,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
    min_cycles: int,
) -> tuple[list[CycleSegment], list[dict[str, str]]] | None:
    rows = read_track_csv(csv_path)
    if len(rows) < 8:
        return None
    times, signal, _ = choose_cycle_signal(rows)
    cycles, _ = detect_cycles(
        times,
        signal,
        min_cycle_sec=min_cycle_sec,
        max_cycle_sec=max_cycle_sec,
    )
    if len(cycles) < min_cycles:
        return None
    return cycles, rows


def pick_best_person(
    pose_video_dir: Path,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
    min_cycles: int,
) -> tuple[str, list[CycleSegment], list[dict[str, str]]] | None:
    best: tuple[str, list[CycleSegment], list[dict[str, str]]] | None = None
    for csv_path in sorted(pose_video_dir.glob("person_*_elbow_angles.csv")):
        person_id = csv_path.stem.replace("person_", "").replace("_elbow_angles", "")
        result = collect_person_cycles(
            csv_path,
            min_cycle_sec=min_cycle_sec,
            max_cycle_sec=max_cycle_sec,
            min_cycles=min_cycles,
        )
        if result is None:
            continue
        cycles, rows = result
        if best is None or len(cycles) > len(best[1]):
            best = (person_id, cycles, rows)
    return best


def aggregate_phase_profiles(
    rows: list[dict[str, str]],
    cycles: list[CycleSegment],
    metric_key: str,
) -> dict[str, np.ndarray] | None:
    curves: list[np.ndarray] = []
    for cycle in cycles:
        curve = resample_cycle_to_phase(rows, cycle, metric_key)
        if curve is not None:
            curves.append(curve)
    if len(curves) < 2:
        return None
    stack = np.vstack(curves)
    return {
        "mean": np.nanmean(stack, axis=0),
        "p10": np.nanpercentile(stack, 10, axis=0),
        "p25": np.nanpercentile(stack, 25, axis=0),
        "p75": np.nanpercentile(stack, 75, axis=0),
        "p90": np.nanpercentile(stack, 90, axis=0),
        "min": np.nanmin(stack, axis=0),
        "max": np.nanmax(stack, axis=0),
        "n_cycles": len(curves),
    }


def write_phase_csv(
    path: Path,
    profiles: dict[str, dict[str, np.ndarray]],
    person_id: str,
    video_name: str,
) -> None:
    fieldnames = [
        "video_dir",
        "person_id",
        "metric",
        "phase_pct",
        "mean",
        "p10",
        "p25",
        "p75",
        "p90",
        "min",
        "max",
        "n_cycles",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for metric_key, stats in profiles.items():
            n_cycles = int(stats["n_cycles"])
            for index, phase in enumerate(PHASE_GRID):
                writer.writerow(
                    {
                        "video_dir": video_name,
                        "person_id": person_id,
                        "metric": metric_key,
                        "phase_pct": f"{phase:.1f}",
                        "mean": f"{stats['mean'][index]:.2f}",
                        "p10": f"{stats['p10'][index]:.2f}",
                        "p25": f"{stats['p25'][index]:.2f}",
                        "p75": f"{stats['p75'][index]:.2f}",
                        "p90": f"{stats['p90'][index]:.2f}",
                        "min": f"{stats['min'][index]:.2f}",
                        "max": f"{stats['max'][index]:.2f}",
                        "n_cycles": n_cycles,
                    }
                )


def plot_video_phase_profile(
    output_path: Path,
    video_name: str,
    person_id: str,
    profiles: dict[str, dict[str, np.ndarray]],
    *,
    show_individual_cycles: bool,
    rows: list[dict[str, str]],
    cycles: list[CycleSegment],
) -> None:
    configure_plot_fonts()
    n_metrics = len(PLOT_METRICS)
    fig, axes = plt.subplots(n_metrics, 1, figsize=(12, 2.6 * n_metrics), sharex=True)
    if n_metrics == 1:
        axes = [axes]

    n_cycles = next(iter(profiles.values()))["n_cycles"]
    fig.suptitle(
        f"Normal phase profile — {video_name}\n"
        f"person {person_id} · {n_cycles} cycles · shaded: p10–p90, line: mean",
        fontsize=13,
        y=0.995,
    )

    for axis, metric_key in zip(axes, PLOT_METRICS):
        stats = profiles.get(metric_key)
        if stats is None:
            axis.set_visible(False)
            continue

        if show_individual_cycles:
            for cycle in cycles:
                curve = resample_cycle_to_phase(rows, cycle, metric_key)
                if curve is not None:
                    axis.plot(PHASE_GRID, curve, color="0.7", alpha=0.25, linewidth=0.8)

        axis.fill_between(PHASE_GRID, stats["p10"], stats["p90"], alpha=0.22, color="C0", label="p10–p90")
        axis.fill_between(PHASE_GRID, stats["p25"], stats["p75"], alpha=0.35, color="C0", label="p25–p75")
        axis.plot(PHASE_GRID, stats["mean"], color="C0", linewidth=2.0, label="mean")
        axis.set_ylabel(METRIC_LABELS.get(metric_key, metric_key))
        axis.set_ylim(0, 180 if "elbow" in metric_key or "knee" in metric_key else None)
        axis.grid(True, alpha=0.3)
        axis.legend(loc="upper right", fontsize=7)

    axes[-1].set_xlabel("Gait cycle phase (%)")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def process_video_dir(
    pose_video_dir: Path,
    output_root: Path,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
    min_cycles: int,
    show_individual_cycles: bool,
) -> dict[str, str] | None:
    picked = pick_best_person(
        pose_video_dir,
        min_cycle_sec=min_cycle_sec,
        max_cycle_sec=max_cycle_sec,
        min_cycles=min_cycles,
    )
    if picked is None:
        return None

    person_id, cycles, rows = picked
    profiles: dict[str, dict[str, np.ndarray]] = {}
    for metric_key in PLOT_METRICS:
        aggregated = aggregate_phase_profiles(rows, cycles, metric_key)
        if aggregated is not None:
            profiles[metric_key] = aggregated

    if not profiles:
        return None

    video_output = output_root / pose_video_dir.name
    video_output.mkdir(parents=True, exist_ok=True)

    png_path = video_output / f"{pose_video_dir.name}_normal_phase_profile.png"
    csv_path = video_output / f"{pose_video_dir.name}_normal_phase_profile.csv"

    plot_video_phase_profile(
        png_path,
        pose_video_dir.name,
        person_id,
        profiles,
        show_individual_cycles=show_individual_cycles,
        rows=rows,
        cycles=cycles,
    )
    write_phase_csv(csv_path, profiles, person_id, pose_video_dir.name)

    return {
        "video_dir": pose_video_dir.name,
        "person_id": person_id,
        "cycles": str(len(cycles)),
        "png": str(png_path),
        "csv": str(csv_path),
    }


def collect_pose_video_dirs(pose_root: Path) -> list[Path]:
    person_in_root = list(pose_root.glob("person_*_elbow_angles.csv"))
    if person_in_root:
        return [pose_root]
    return sorted(
        path
        for path in pose_root.iterdir()
        if path.is_dir() and list(path.glob("person_*_elbow_angles.csv"))
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize per-video normal gait phase metric bands (mean + percentile envelope)."
    )
    parser.add_argument(
        "pose_root",
        type=Path,
        default=Path("analysis/results_initial_box_pose_metrics_stride3"),
        nargs="?",
        help="Root folder with per-video person_*_elbow_angles.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/results_normal_phase_profiles"),
    )
    parser.add_argument("--min-cycle-sec", type=float, default=0.45)
    parser.add_argument("--max-cycle-sec", type=float, default=1.8)
    parser.add_argument("--min-cycles", type=int, default=3, help="Minimum cycles on best track to plot")
    parser.add_argument(
        "--show-individual-cycles",
        action="store_true",
        help="Draw faint lines for each resampled cycle",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_dirs = collect_pose_video_dirs(args.pose_root)
    if not video_dirs:
        raise RuntimeError(f"No person_*_elbow_angles.csv found under {args.pose_root}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, str]] = []
    skipped: list[str] = []

    for video_dir in video_dirs:
        summary = process_video_dir(
            video_dir,
            args.output_dir,
            min_cycle_sec=args.min_cycle_sec,
            max_cycle_sec=args.max_cycle_sec,
            min_cycles=args.min_cycles,
            show_individual_cycles=args.show_individual_cycles,
        )
        if summary is None:
            skipped.append(video_dir.name)
            print(f"Skipped (insufficient cycles): {video_dir.name}")
            continue
        summaries.append(summary)
        print(f"OK: {video_dir.name} person {summary['person_id']} ({summary['cycles']} cycles)")
        print(f"  PNG: {summary['png']}")

    if summaries:
        summary_csv = args.output_dir / "all_normal_phase_profile_summary.csv"
        with summary_csv.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["video_dir", "person_id", "cycles", "png", "csv"])
            writer.writeheader()
            writer.writerows(summaries)
        print(f"Summary: {summary_csv}")

    if skipped:
        print(f"Skipped {len(skipped)} videos: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
