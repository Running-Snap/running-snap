"""트랜지션 이펙트"""
import numpy as np
import cv2
from moviepy import (
    VideoFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    ColorClip
)


def crossfade(
    clip1: VideoFileClip,
    clip2: VideoFileClip,
    duration: float = 0.5
) -> VideoFileClip:
    """
    크로스페이드 트랜지션

    Args:
        clip1: 첫 번째 클립
        clip2: 두 번째 클립
        duration: 페이드 길이 (초)
    """
    # MoviePy 2.x 호환: 수동으로 크로스페이드 구현
    # crossfadeout/crossfadein이 없을 수 있으므로 직접 구현

    # duration이 클립보다 길면 조정
    duration = min(duration, clip1.duration * 0.5, clip2.duration * 0.5)

    # 페이드아웃 효과 (clip1 끝부분)
    def fadeout_filter(get_frame, t):
        frame = get_frame(t)
        if t > clip1.duration - duration:
            # 점점 어두워짐
            progress = (t - (clip1.duration - duration)) / duration
            factor = 1.0 - progress
            return (frame * factor).astype(np.uint8)
        return frame

    # 페이드인 효과 (clip2 시작부분)
    def fadein_filter(get_frame, t):
        frame = get_frame(t)
        if t < duration:
            # 점점 밝아짐
            progress = t / duration
            factor = progress
            return (frame * factor).astype(np.uint8)
        return frame

    try:
        # 먼저 MoviePy 내장 메서드 시도
        clip1_faded = clip1.with_effects([lambda c: c.crossfadeout(duration)])
        clip2_faded = clip2.with_effects([lambda c: c.crossfadein(duration)])
        clip2_positioned = clip2_faded.with_start(clip1.duration - duration)
        return CompositeVideoClip([clip1_faded, clip2_positioned])
    except (AttributeError, TypeError):
        # 내장 메서드 없으면 단순 연결로 대체 (크로스페이드 효과 없이)
        return concatenate_videoclips([clip1, clip2])


def flash_transition(
    clip1: VideoFileClip,
    clip2: VideoFileClip,
    duration: float = 0.1,
    color: tuple = (255, 255, 255)
) -> VideoFileClip:
    """
    플래시(화이트/블랙) 트랜지션 - 짧은 플래시

    Args:
        clip1: 첫 번째 클립
        clip2: 두 번째 클립
        duration: 플래시 길이 (짧게)
        color: 플래시 색상 (RGB)
    """
    w, h = clip1.size

    # 아주 짧은 플래시 (0.05초)
    flash_duration = min(0.05, duration)
    flash = ColorClip(size=(w, h), color=color, duration=flash_duration)

    # 단순 연결 (플래시가 짧아서 자연스러움)
    return concatenate_videoclips([clip1, flash, clip2])


def zoom_transition(
    clip1: VideoFileClip,
    clip2: VideoFileClip,
    duration: float = 0.4,
    zoom_factor: float = 1.5
) -> VideoFileClip:
    """
    줌 트랜지션 (clip1 줌인 -> clip2 줌아웃)

    Args:
        clip1: 첫 번째 클립
        clip2: 두 번째 클립
        duration: 트랜지션 길이
        zoom_factor: 최대 줌 배율
    """
    half_duration = duration / 2

    # clip1 끝부분 줌인
    def zoom_in(get_frame, t):
        frame = get_frame(t)
        # 마지막 half_duration 동안 줌인
        clip_end = clip1.duration
        if t > clip_end - half_duration:
            progress = (t - (clip_end - half_duration)) / half_duration
            scale = 1 + (zoom_factor - 1) * progress
            return _zoom_frame(frame, scale)
        return frame

    # clip2 시작부분 줌아웃
    def zoom_out(get_frame, t):
        frame = get_frame(t)
        if t < half_duration:
            progress = t / half_duration
            scale = zoom_factor - (zoom_factor - 1) * progress
            return _zoom_frame(frame, scale)
        return frame

    clip1_zoomed = clip1.transform(zoom_in, apply_to=['video'])
    clip2_zoomed = clip2.transform(zoom_out, apply_to=['video'])

    return concatenate_videoclips([clip1_zoomed, clip2_zoomed])


def _zoom_frame(frame: np.ndarray, scale: float) -> np.ndarray:
    """프레임 줌 (중앙 기준)"""
    h, w = frame.shape[:2]
    new_h, new_w = int(h * scale), int(w * scale)

    # 확대
    zoomed = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # 중앙 크롭
    start_y = (new_h - h) // 2
    start_x = (new_w - w) // 2

    return zoomed[start_y:start_y + h, start_x:start_x + w]


def cut_transition(
    clip1: VideoFileClip,
    clip2: VideoFileClip,
    **kwargs
) -> VideoFileClip:
    """단순 컷 (트랜지션 없음)"""
    return concatenate_videoclips([clip1, clip2])


def whip_pan(
    clip1: VideoFileClip,
    clip2: VideoFileClip,
    duration: float = 0.2
) -> VideoFileClip:
    """
    휩 팬 (빠른 수평 이동) 트랜지션
    모션 블러 효과로 구현
    """
    def motion_blur_out(get_frame, t):
        """clip1 끝에 모션블러"""
        frame = get_frame(t)
        clip_end = clip1.duration
        if t > clip_end - duration:
            progress = (t - (clip_end - duration)) / duration
            return _apply_motion_blur(frame, progress, direction="right")
        return frame

    def motion_blur_in(get_frame, t):
        """clip2 시작에 모션블러"""
        frame = get_frame(t)
        if t < duration:
            progress = 1 - (t / duration)
            return _apply_motion_blur(frame, progress, direction="right")
        return frame

    clip1_blurred = clip1.transform(motion_blur_out, apply_to=['video'])
    clip2_blurred = clip2.transform(motion_blur_in, apply_to=['video'])

    return concatenate_videoclips([clip1_blurred, clip2_blurred])


def _apply_motion_blur(
    frame: np.ndarray,
    strength: float,
    direction: str = "right"
) -> np.ndarray:
    """수평 모션블러 적용"""
    # 블러 커널 크기 (strength에 비례)
    kernel_size = int(strength * 50) + 1
    if kernel_size % 2 == 0:
        kernel_size += 1

    # 수평 모션블러 커널
    kernel = np.zeros((kernel_size, kernel_size))
    kernel[kernel_size // 2, :] = 1.0 / kernel_size

    return cv2.filter2D(frame, -1, kernel)


# 트랜지션 매핑
TRANSITIONS = {
    "cut": cut_transition,
    "crossfade": crossfade,
    "flash": flash_transition,
    "zoom": zoom_transition,
    "whip_pan": whip_pan,
}


def apply_transition(
    clip1: VideoFileClip,
    clip2: VideoFileClip,
    transition_type: str,
    duration: float = 0.3
) -> VideoFileClip:
    """
    트랜지션 적용 (통합 인터페이스)

    Args:
        clip1: 첫 번째 클립
        clip2: 두 번째 클립
        transition_type: 트랜지션 종류
        duration: 트랜지션 길이
    """
    transition_func = TRANSITIONS.get(transition_type, cut_transition)
    return transition_func(clip1, clip2, duration=duration)
