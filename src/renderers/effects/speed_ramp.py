"""스피드 램프 이펙트"""
import numpy as np
from moviepy import VideoFileClip, concatenate_videoclips


def apply_speed_change(clip: VideoFileClip, speed: float) -> VideoFileClip:
    """
    단순 속도 변경

    Args:
        clip: 원본 클립
        speed: 속도 배율 (0.5 = 절반 속도, 2.0 = 2배속)
    """
    if speed == 1.0:
        return clip

    return clip.with_speed_scaled(speed)


def apply_speed_ramp(
    clip: VideoFileClip,
    start_speed: float = 1.0,
    end_speed: float = 0.5,
    curve: str = "ease_in_out"
) -> VideoFileClip:
    """
    부드러운 속도 변화 (스피드 램프) 적용

    Args:
        clip: 원본 클립
        start_speed: 시작 속도
        end_speed: 끝 속도
        curve: 변화 커브 ("linear", "ease_in", "ease_out", "ease_in_out")

    Returns:
        속도 변화가 적용된 클립
    """
    duration = clip.duration

    def time_transform(t):
        """원본 시간 -> 변환된 시간 매핑 (numpy 배열 지원)"""
        # t가 배열일 수 있으므로 numpy 연산 사용
        t = np.asarray(t)

        # 정규화된 위치 (0~1)
        progress = t / duration if duration > 0 else np.zeros_like(t)

        # 커브 적용 (배열 연산)
        if curve == "ease_in":
            curved = progress ** 2
        elif curve == "ease_out":
            curved = 1 - (1 - progress) ** 2
        elif curve == "ease_in_out":
            # np.where로 조건부 배열 연산
            curved = np.where(
                progress < 0.5,
                2 * progress ** 2,
                1 - 2 * (1 - progress) ** 2
            )
        else:  # linear
            curved = progress

        # 현재 속도 계산 (보간)
        current_speed = start_speed + (end_speed - start_speed) * curved

        # 누적 시간 계산 (적분 근사)
        # 단순화를 위해 현재 속도로 시간 변환
        return t * current_speed

    # 새 duration 계산 (평균 속도 기준)
    avg_speed = (start_speed + end_speed) / 2
    new_duration = duration / avg_speed if avg_speed > 0 else duration

    return clip.time_transform(time_transform, apply_to=['video', 'audio']).with_duration(new_duration)


def create_slow_motion_peak(
    clip: VideoFileClip,
    peak_time: float,
    slow_speed: float = 0.3,
    ramp_duration: float = 0.5
) -> VideoFileClip:
    """
    특정 순간에 슬로우모션 피크 생성

    전체 흐름: 보통속도 -> 슬로우 -> 보통속도

    Args:
        clip: 원본 클립
        peak_time: 슬로우모션 피크 시간 (원본 기준)
        slow_speed: 슬로우모션 속도 (0.3 = 30% 속도)
        ramp_duration: 램프 전환 구간 길이
    """
    duration = clip.duration

    # 구간 나누기
    ramp_start = max(0, peak_time - ramp_duration)
    ramp_end = min(duration, peak_time + ramp_duration)

    clips = []

    # 1. 피크 전 구간 (보통 속도)
    if ramp_start > 0:
        before_clip = clip.subclipped(0, ramp_start)
        clips.append(before_clip)

    # 2. 램프 인 (점점 느려짐)
    if ramp_start < peak_time:
        ramp_in_clip = clip.subclipped(ramp_start, peak_time)
        ramp_in_clip = apply_speed_ramp(ramp_in_clip, 1.0, slow_speed, "ease_out")
        clips.append(ramp_in_clip)

    # 3. 램프 아웃 (점점 빨라짐)
    if peak_time < ramp_end:
        ramp_out_clip = clip.subclipped(peak_time, ramp_end)
        ramp_out_clip = apply_speed_ramp(ramp_out_clip, slow_speed, 1.0, "ease_in")
        clips.append(ramp_out_clip)

    # 4. 피크 후 구간 (보통 속도)
    if ramp_end < duration:
        after_clip = clip.subclipped(ramp_end, duration)
        clips.append(after_clip)

    if clips:
        return concatenate_videoclips(clips)
    return clip
