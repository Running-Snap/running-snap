"""Gait feature extraction from detected events."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from .gait_events import GaitEvent


def extract_gait_features(events: list[GaitEvent], fps: float) -> dict[str, float | int | list[dict]]:
    """
    Compute step frequency, ground contact time, swing time per side.

    Returns summary dict suitable for JSON export.
    """
    by_side: dict[str, list[GaitEvent]] = {"left": [], "right": []}
    for event in events:
        by_side.setdefault(event.side, []).append(event)

    summary: dict[str, float | int | list[dict]] = {
        "fps": fps,
        "events": [asdict(e) for e in events],
        "per_side": {},
    }

    for side, side_events in by_side.items():
        strikes = [e for e in side_events if e.event_type == "foot_strike"]
        if len(strikes) < 2:
            summary["per_side"][side] = {
                "step_frequency_hz": 0.0,
                "cadence_spm": 0.0,
                "ground_contact_time_sec": 0.0,
                "swing_time_sec": 0.0,
                "n_strikes": len(strikes),
            }
            continue

        strike_times = np.array([e.time_sec for e in strikes])
        intervals = np.diff(strike_times)
        step_period = float(np.median(intervals))
        step_freq = 1.0 / step_period if step_period > 0 else 0.0

        contact_times: list[float] = []
        swing_times: list[float] = []
        toe_offs = {e.frame: e for e in side_events if e.event_type == "toe_off"}

        for i, strike in enumerate(strikes[:-1]):
            next_strike = strikes[i + 1]
            cycle_toe = [
                e for e in side_events
                if e.event_type == "toe_off" and strike.frame < e.frame < next_strike.frame
            ]
            if cycle_toe:
                toe = cycle_toe[0]
                contact = (toe.time_sec - strike.time_sec)
                swing = (next_strike.time_sec - toe.time_sec)
                if contact > 0:
                    contact_times.append(contact)
                if swing > 0:
                    swing_times.append(swing)

        summary["per_side"][side] = {
            "step_frequency_hz": round(step_freq, 3),
            "cadence_spm": round(step_freq * 60.0, 2),
            "ground_contact_time_sec": round(float(np.median(contact_times)) if contact_times else 0.0, 4),
            "swing_time_sec": round(float(np.median(swing_times)) if swing_times else 0.0, 4),
            "n_strikes": len(strikes),
            "step_period_sec": round(step_period, 4),
        }

    # Combined cadence from dominant side
    left_spm = summary["per_side"].get("left", {}).get("cadence_spm", 0)
    right_spm = summary["per_side"].get("right", {}).get("cadence_spm", 0)
    spms = [v for v in (left_spm, right_spm) if v and v > 0]
    summary["cadence_spm"] = round(float(np.mean(spms)) if spms else 0.0, 2)
    return summary
