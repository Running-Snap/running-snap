"""Temporal post-processing for pose keypoint sequences."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, filtfilt

from .landmarks import BONE_PAIRS, LEFT_ARM, LEFT_LEG, RIGHT_ARM, RIGHT_LEG


@dataclass
class PostProcessConfig:
    median_window: int = 5
    butter_cutoff_hz: float = 6.0
    butter_order: int = 2
    max_jump_norm: float = 0.08
    max_velocity_norm: float = 0.25
    min_visibility: float = 0.5
    bone_length_blend: float = 0.3


class PosePostProcessor:
    """Stabilize raw MediaPipe keypoints across time."""

    def __init__(self, fps: float, config: PostProcessConfig | None = None) -> None:
        self.fps = max(fps, 1.0)
        self.config = config or PostProcessConfig()

    def process(self, keypoints: np.ndarray) -> np.ndarray:
        """Apply full post-processing chain."""
        out = keypoints.astype(np.float32, copy=True)
        out = self._interpolate_missing(out)
        out = self.smooth_keypoints(out)
        out = self.enforce_temporal_consistency(out)
        out = self.fix_left_right_swap(out)
        out = self.normalize_bone_length(out)
        out = self.remove_outliers(out)
        out = self.enforce_temporal_consistency(out)
        return out

    def smooth_keypoints(self, keypoints: np.ndarray) -> np.ndarray:
        """Median filter + Butterworth low-pass per coordinate."""
        out = keypoints.copy()
        window = max(3, self.config.median_window | 1)
        for j in range(3):
            for lm in range(out.shape[1]):
                series = out[:, lm, j]
                valid = ~np.isnan(series)
                if valid.sum() < window:
                    continue
                filled = self._fill_nan_1d(series)
                smoothed = median_filter(filled, size=window, mode="nearest")
                smoothed = self._lowpass_1d(smoothed)
                out[:, lm, j] = smoothed
        return out

    def enforce_temporal_consistency(self, keypoints: np.ndarray) -> np.ndarray:
        """Replace sudden jumps with previous frame."""
        out = keypoints.copy()
        max_jump = self.config.max_jump_norm
        for t in range(1, out.shape[0]):
            prev = out[t - 1]
            curr = out[t]
            if np.all(np.isnan(prev)) or np.all(np.isnan(curr)):
                continue
            dist = np.linalg.norm(curr[:, :2] - prev[:, :2], axis=1)
            bad = dist > max_jump
            curr[bad] = prev[bad]
            out[t] = curr
        return out

    def fix_left_right_swap(self, keypoints: np.ndarray) -> np.ndarray:
        """
        Detect left/right leg (and arm) swaps using hip–ankle distance consistency.
        """
        out = keypoints.copy()
        l_hip, l_knee, l_ankle = LEFT_LEG[0], LEFT_LEG[1], LEFT_LEG[2]
        r_hip, r_knee, r_ankle = RIGHT_LEG[0], RIGHT_LEG[1], RIGHT_LEG[2]

        for t in range(1, out.shape[0]):
            prev = out[t - 1]
            curr = out[t]
            if np.any(np.isnan(curr[[l_hip, r_hip, l_ankle, r_ankle], :2])):
                continue

            def leg_cost(kps: np.ndarray) -> float:
                left_d = np.linalg.norm(kps[l_ankle, :2] - kps[l_hip, :2])
                right_d = np.linalg.norm(kps[r_ankle, :2] - kps[r_hip, :2])
                prev_left = np.linalg.norm(prev[l_ankle, :2] - prev[l_hip, :2])
                prev_right = np.linalg.norm(prev[r_ankle, :2] - prev[r_hip, :2])
                swap_left = np.linalg.norm(kps[l_ankle, :2] - kps[r_hip, :2])
                swap_right = np.linalg.norm(kps[r_ankle, :2] - kps[l_hip, :2])
                normal = abs(left_d - prev_left) + abs(right_d - prev_right)
                swapped = abs(swap_left - prev_left) + abs(swap_right - prev_right)
                return normal, swapped

            n_cost, s_cost = leg_cost(curr)
            _, s_cost_prev = leg_cost(prev)
            if s_cost < n_cost and s_cost < s_cost_prev * 0.95:
                curr = self._swap_groups(curr, LEFT_LEG, RIGHT_LEG)
                curr = self._swap_groups(curr, LEFT_ARM, RIGHT_ARM)
                out[t] = curr
        return out

    def normalize_bone_length(self, keypoints: np.ndarray) -> np.ndarray:
        """Keep limb lengths close to temporal median."""
        out = keypoints.copy()
        alpha = self.config.bone_length_blend
        for a, b in BONE_PAIRS:
            vec = out[:, b, :2] - out[:, a, :2]
            lengths = np.linalg.norm(vec, axis=1)
            valid = ~np.isnan(lengths) & (lengths > 1e-6)
            if valid.sum() < 3:
                continue
            target = float(np.nanmedian(lengths[valid]))
            for t in np.where(valid)[0]:
                current = lengths[t]
                scale = target / current
                midpoint = (out[t, a, :2] + out[t, b, :2]) / 2
                half = (out[t, b, :2] - out[t, a, :2]) / 2 * scale
                out[t, a, :2] = midpoint - half
                out[t, b, :2] = midpoint + half
                out[t, a, :2] = (1 - alpha) * keypoints[t, a, :2] + alpha * out[t, a, :2]
                out[t, b, :2] = (1 - alpha) * keypoints[t, b, :2] + alpha * out[t, b, :2]
        return out

    def remove_outliers(self, keypoints: np.ndarray) -> np.ndarray:
        """Remove frames with excessive joint velocity."""
        out = keypoints.copy()
        max_vel = self.config.max_velocity_norm * self.fps
        for lm in range(out.shape[1]):
            xy = out[:, lm, :2]
            vel = np.linalg.norm(np.diff(xy, axis=0), axis=1) * self.fps
            bad_frames = np.where(vel > max_vel)[0] + 1
            for t in bad_frames:
                if t > 0 and not np.any(np.isnan(out[t - 1])):
                    out[t, lm] = out[t - 1, lm]
        return out

    def _lowpass_1d(self, series: np.ndarray) -> np.ndarray:
        nyq = 0.5 * self.fps
        cutoff = min(self.config.butter_cutoff_hz / nyq, 0.99)
        if cutoff <= 0:
            return series
        b, a = butter(self.config.butter_order, cutoff, btype="low")
        try:
            return filtfilt(b, a, series)
        except ValueError:
            return series

    def _fill_nan_1d(self, series: np.ndarray) -> np.ndarray:
        out = series.copy()
        valid = ~np.isnan(out)
        if not valid.any():
            return out
        idx = np.arange(len(out))
        out[~valid] = np.interp(idx[~valid], idx[valid], out[valid])
        return out

    def _interpolate_missing(self, keypoints: np.ndarray) -> np.ndarray:
        out = keypoints.copy()
        for lm in range(out.shape[1]):
            for j in range(3):
                out[:, lm, j] = self._fill_nan_1d(out[:, lm, j])
        return out

    @staticmethod
    def _swap_groups(kps: np.ndarray, left: tuple[int, ...], right: tuple[int, ...]) -> np.ndarray:
        out = kps.copy()
        for li, ri in zip(left, right):
            out[[li, ri]] = out[[ri, li]]
        return out
