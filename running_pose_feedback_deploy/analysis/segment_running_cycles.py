from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from scipy.signal import find_peaks

METRIC_FIELDS = [
    "left_elbow_deg",
    "right_elbow_deg",
    "left_knee_deg",
    "right_knee_deg",
    "torso_lean_deg",
    "elbow_symmetry_diff_deg",
    "knee_symmetry_diff_deg",
]

CYCLE_SUMMARY_FIELDS = [
    "cycle_id",
    "start_time_sec",
    "end_time_sec",
    "duration_sec",
    "cadence_spm",
    "samples",
    "signal_source",
    *[
        f"{field}_{stat}"
        for field in METRIC_FIELDS
        for stat in ("min", "max", "mean")
    ],
]


@dataclass
class CycleSegment:
    cycle_id: int
    start_idx: int
    end_idx: int
    start_time_sec: float
    end_time_sec: float


def configure_plot_fonts() -> None:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ("Noto Sans CJK KR", "Noto Sans CJK JP", "NanumGothic", "Malgun Gothic"):
        if font_name in available_fonts:
            plt.rcParams["font.family"] = font_name
            break
    plt.rcParams["axes.unicode_minus"] = False


def parse_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        return math.nan
    return parsed


def read_track_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def build_series(rows: list[dict[str, str]], key: str) -> tuple[np.ndarray, np.ndarray]:
    times = np.array([parse_float(row["time_sec"]) for row in rows], dtype=float)
    values = np.array([parse_float(row.get(key, "nan")) for row in rows], dtype=float)
    return times, values


def interpolate_short_gaps(times: np.ndarray, values: np.ndarray, max_gap_sec: float) -> np.ndarray:
    if len(values) == 0:
        return values

    filled = values.copy()
    valid = ~np.isnan(filled)
    if valid.sum() < 2:
        return filled

    for index in range(1, len(filled)):
        if np.isnan(filled[index]) and valid[index - 1]:
            gap_start = index
            while index < len(filled) and np.isnan(filled[index]):
                index += 1
            gap_end = index
            if gap_end < len(filled) and (times[gap_end] - times[gap_start - 1]) <= max_gap_sec:
                left_time = times[gap_start - 1]
                right_time = times[gap_end]
                left_value = filled[gap_start - 1]
                right_value = filled[gap_end]
                for fill_index in range(gap_start, gap_end):
                    ratio = (times[fill_index] - left_time) / (right_time - left_time)
                    filled[fill_index] = left_value + (right_value - left_value) * ratio
    return filled


def smooth(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(values) < window:
        return values
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def median_dt(times: np.ndarray) -> float:
    if len(times) < 2:
        return 0.1
    diffs = np.diff(times)
    diffs = diffs[diffs > 0]
    return float(np.median(diffs)) if len(diffs) else 0.1


def choose_cycle_signal(rows: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray, str]:
    times = np.array([parse_float(row["time_sec"]) for row in rows], dtype=float)
    left_knee = np.array([parse_float(row.get("left_knee_deg", "nan")) for row in rows], dtype=float)
    right_knee = np.array([parse_float(row.get("right_knee_deg", "nan")) for row in rows], dtype=float)
    left_elbow = np.array([parse_float(row.get("left_elbow_deg", "nan")) for row in rows], dtype=float)
    right_elbow = np.array([parse_float(row.get("right_elbow_deg", "nan")) for row in rows], dtype=float)

    knee_stack = np.vstack([left_knee, right_knee])
    knee_valid = np.sum(~np.isnan(knee_stack), axis=0)
    if np.any(knee_valid >= 1):
        combined = np.full(len(times), np.nan)
        for index in range(len(times)):
            values = knee_stack[:, index]
            valid_values = values[~np.isnan(values)]
            if len(valid_values):
                combined[index] = float(np.max(valid_values))
        return times, combined, "max(left_knee, right_knee)"

    elbow_stack = np.vstack([left_elbow, right_elbow])
    if np.sum(~np.isnan(elbow_stack)) >= 3:
        combined = np.full(len(times), np.nan)
        for index in range(len(times)):
            values = elbow_stack[:, index]
            valid_values = values[~np.isnan(values)]
            if len(valid_values):
                combined[index] = float(np.max(valid_values))
        return times, combined, "max(left_elbow, right_elbow)"

    return times, np.full(len(times), np.nan), "none"


def detect_cycles(
    times: np.ndarray,
    signal: np.ndarray,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
) -> tuple[list[CycleSegment], np.ndarray]:
    if len(signal) < 5 or np.all(np.isnan(signal)):
        return [], np.array([], dtype=int)

    dt = median_dt(times)
    window = max(3, int(round(0.15 / dt)))
    filled = interpolate_short_gaps(times, signal, max_gap_sec=0.5)
    smoothed = smooth(filled, window)

    valid = ~np.isnan(smoothed)
    if valid.sum() < 5:
        return [], np.array([], dtype=int)

    min_distance = max(1, int(round(min_cycle_sec / dt)))
    prominence = max(3.0, float(np.nanstd(smoothed) * 0.25))
    peak_indices, _ = find_peaks(smoothed, distance=min_distance, prominence=prominence)

    if len(peak_indices) < 2:
        trough_indices, _ = find_peaks(-smoothed, distance=min_distance, prominence=prominence)
        peak_indices = trough_indices

    if len(peak_indices) < 2:
        return [], peak_indices

    cycles: list[CycleSegment] = []
    for cycle_id, start_idx in enumerate(peak_indices[:-1]):
        end_idx = peak_indices[cycle_id + 1]
        duration = times[end_idx] - times[start_idx]
        if duration < min_cycle_sec or duration > max_cycle_sec:
            continue
        cycles.append(
            CycleSegment(
                cycle_id=len(cycles) + 1,
                start_idx=int(start_idx),
                end_idx=int(end_idx),
                start_time_sec=float(times[start_idx]),
                end_time_sec=float(times[end_idx]),
            )
        )
    return cycles, peak_indices


def metric_stats(values: np.ndarray) -> dict[str, float | str]:
    valid = values[~np.isnan(values)]
    if len(valid) == 0:
        return {"min": "", "max": "", "mean": ""}
    return {
        "min": f"{float(np.min(valid)):.2f}",
        "max": f"{float(np.max(valid)):.2f}",
        "mean": f"{float(np.mean(valid)):.2f}",
    }


def summarize_cycle(rows: list[dict[str, str]], cycle: CycleSegment, signal_source: str) -> dict[str, float | int | str]:
    segment_rows = rows[cycle.start_idx : cycle.end_idx + 1]
    duration = cycle.end_time_sec - cycle.start_time_sec
    cadence = (60.0 / duration) if duration > 0 else ""
    summary: dict[str, float | int | str] = {
        "cycle_id": cycle.cycle_id,
        "start_time_sec": f"{cycle.start_time_sec:.3f}",
        "end_time_sec": f"{cycle.end_time_sec:.3f}",
        "duration_sec": f"{duration:.3f}",
        "cadence_spm": f"{cadence:.1f}" if cadence != "" else "",
        "samples": len(segment_rows),
        "signal_source": signal_source,
    }
    for field in METRIC_FIELDS:
        values = np.array([parse_float(row.get(field, "nan")) for row in segment_rows], dtype=float)
        stats = metric_stats(values)
        summary[f"{field}_min"] = stats["min"]
        summary[f"{field}_max"] = stats["max"]
        summary[f"{field}_mean"] = stats["mean"]
    return summary


def write_cycles_csv(path: Path, cycle_rows: list[dict[str, float | int | str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CYCLE_SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(cycle_rows)


def plot_cycle_detection(
    path: Path,
    times: np.ndarray,
    signal: np.ndarray,
    peak_indices: np.ndarray,
    cycles: list[CycleSegment],
    title: str,
) -> None:
    configure_plot_fonts()
    plt.figure(figsize=(12, 5))
    plt.plot(times, signal, label="Cycle signal", linewidth=1.4)
    if len(peak_indices):
        plt.plot(times[peak_indices], signal[peak_indices], "o", label="Cycle boundaries", markersize=5)
    for cycle in cycles:
        plt.axvspan(cycle.start_time_sec, cycle.end_time_sec, alpha=0.12)
    plt.title(title)
    plt.xlabel("Time (seconds)")
    plt.ylabel("Signal value (degrees)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def plot_phase_overlay(
    path: Path,
    rows: list[dict[str, str]],
    cycles: list[CycleSegment],
    metric_key: str,
    title: str,
) -> None:
    configure_plot_fonts()
    plt.figure(figsize=(12, 5))
    plotted = False
    for cycle in cycles:
        segment_rows = rows[cycle.start_idx : cycle.end_idx + 1]
        times = np.array([parse_float(row["time_sec"]) for row in segment_rows], dtype=float)
        values = np.array([parse_float(row.get(metric_key, "nan")) for row in segment_rows], dtype=float)
        if len(times) < 2 or np.all(np.isnan(values)):
            continue
        phase = (times - times[0]) / max(times[-1] - times[0], 1e-6) * 100.0
        plt.plot(phase, values, alpha=0.45, linewidth=1.2, label=f"cycle {cycle.cycle_id}")
        plotted = True
    if not plotted:
        plt.close()
        return
    plt.title(title)
    plt.xlabel("Cycle phase (%)")
    plt.ylabel(f"{metric_key} (degrees)")
    plt.grid(True, alpha=0.3)
    if len(cycles) <= 12:
        plt.legend(fontsize=8, ncol=2)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def process_person_csv(
    csv_path: Path,
    output_dir: Path,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
) -> dict[str, float | int | str] | None:
    rows = read_track_csv(csv_path)
    if len(rows) < 8:
        return None

    times, signal, signal_source = choose_cycle_signal(rows)
    cycles, peak_indices = detect_cycles(
        times,
        signal,
        min_cycle_sec=min_cycle_sec,
        max_cycle_sec=max_cycle_sec,
    )
    person_id = csv_path.stem.replace("person_", "").replace("_elbow_angles", "")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not cycles:
        return {
            "person_id": person_id,
            "cycles": 0,
            "signal_source": signal_source,
            "median_duration_sec": "",
            "median_cadence_spm": "",
        }

    cycle_rows = [summarize_cycle(rows, cycle, signal_source) for cycle in cycles]
    write_cycles_csv(output_dir / f"person_{person_id}_cycles.csv", cycle_rows)

    filled = interpolate_short_gaps(times, signal, max_gap_sec=0.5)
    smoothed = smooth(filled, max(3, int(round(0.15 / median_dt(times)))))
    plot_cycle_detection(
        output_dir / f"person_{person_id}_cycle_detection.png",
        times,
        smoothed,
        peak_indices,
        cycles,
        f"Cycle Detection - person {person_id}",
    )
    plot_phase_overlay(
        output_dir / f"person_{person_id}_knee_phase_overlay.png",
        rows,
        cycles,
        "left_knee_deg",
        f"Left Knee Angle by Cycle Phase - person {person_id}",
    )
    plot_phase_overlay(
        output_dir / f"person_{person_id}_elbow_phase_overlay.png",
        rows,
        cycles,
        "left_elbow_deg",
        f"Left Elbow Angle by Cycle Phase - person {person_id}",
    )

    durations = [cycle.end_time_sec - cycle.start_time_sec for cycle in cycles]
    cadences = [60.0 / duration for duration in durations if duration > 0]
    return {
        "person_id": person_id,
        "cycles": len(cycles),
        "signal_source": signal_source,
        "median_duration_sec": f"{float(np.median(durations)):.3f}",
        "median_cadence_spm": f"{float(np.median(cadences)):.1f}" if cadences else "",
    }


def process_video_dir(
    video_dir: Path,
    output_root: Path,
    *,
    min_cycle_sec: float,
    max_cycle_sec: float,
) -> Path | None:
    person_csvs = sorted(video_dir.glob("person_*_elbow_angles.csv"))
    if not person_csvs:
        return None

    video_output = output_root / video_dir.name
    video_output.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, float | int | str]] = []
    for csv_path in person_csvs:
        person_output = video_output / csv_path.stem.replace("_elbow_angles", "")
        summary = process_person_csv(
            csv_path,
            person_output,
            min_cycle_sec=min_cycle_sec,
            max_cycle_sec=max_cycle_sec,
        )
        if summary:
            summaries.append(summary)

    if not summaries:
        return None

    summary_csv = video_output / "cycle_segmentation_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["person_id", "cycles", "signal_source", "median_duration_sec", "median_cadence_spm"],
        )
        writer.writeheader()
        writer.writerows(summaries)
    return summary_csv


def collect_video_dirs(input_path: Path, name_filter: str | None = None) -> list[Path]:
    if input_path.is_file():
        return []
    person_csv = list(input_path.glob("person_*_elbow_angles.csv"))
    if person_csv:
        return [input_path]
    video_dirs = sorted(path for path in input_path.iterdir() if path.is_dir())
    if name_filter:
        video_dirs = [path for path in video_dirs if name_filter in path.name]
    return video_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Segment running cycles from initial box track CSV outputs.")
    parser.add_argument(
        "input",
        type=Path,
        help="Video directory from initial_box_track output, or parent folder containing many video dirs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/results_running_cycles"),
        help="Directory for cycle CSVs and plots",
    )
    parser.add_argument(
        "--min-cycle-sec",
        type=float,
        default=0.45,
        help="Minimum duration between cycle boundaries (seconds)",
    )
    parser.add_argument(
        "--max-cycle-sec",
        type=float,
        default=1.8,
        help="Maximum allowed cycle duration (seconds)",
    )
    parser.add_argument(
        "--name-filter",
        type=str,
        default=None,
        help="Only process video directories whose name contains this substring",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_dirs = collect_video_dirs(args.input, args.name_filter)
    if not video_dirs:
        raise RuntimeError(f"No video directories with person_*_elbow_angles.csv found: {args.input}")

    all_summaries: list[dict[str, float | int | str]] = []
    for video_dir in video_dirs:
        summary_csv = process_video_dir(
            video_dir,
            args.output_dir,
            min_cycle_sec=args.min_cycle_sec,
            max_cycle_sec=args.max_cycle_sec,
        )
        if summary_csv is None:
            print(f"Skipped: {video_dir}")
            continue
        print(f"Video: {video_dir.name}")
        print(f"Summary: {summary_csv}")
        with summary_csv.open(encoding="utf-8") as file:
            for row in csv.DictReader(file):
                all_summaries.append({"video_dir": video_dir.name, **row})

    if all_summaries:
        combined = args.output_dir / "all_cycle_segmentation_summary.csv"
        with combined.open("w", newline="", encoding="utf-8") as file:
            fieldnames = ["video_dir", "person_id", "cycles", "signal_source", "median_duration_sec", "median_cadence_spm"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_summaries)
        print(f"Combined summary: {combined}")


if __name__ == "__main__":
    main()
