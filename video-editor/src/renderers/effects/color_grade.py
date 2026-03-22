"""색상 그레이딩 이펙트"""
import numpy as np
from moviepy import VideoFileClip


def apply_color_adjustment(
    clip: VideoFileClip,
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    warmth: float = 0.0
) -> VideoFileClip:
    """
    기본 색상 조정

    Args:
        clip: 원본 클립
        brightness: 밝기 조정 (-1.0 ~ 1.0)
        contrast: 대비 (0.5 ~ 2.0, 1.0이 기본)
        saturation: 채도 (0.0 ~ 2.0, 1.0이 기본)
        warmth: 따뜻함 (-1.0 차가움 ~ 1.0 따뜻함)
    """
    def process_frame(frame):
        # numpy array to float
        img = frame.astype(np.float32) / 255.0

        # 밝기
        if brightness != 0:
            img = img + brightness

        # 대비
        if contrast != 1.0:
            img = (img - 0.5) * contrast + 0.5

        # 채도 (RGB to HSV 간소화 버전)
        if saturation != 1.0:
            gray = np.mean(img, axis=2, keepdims=True)
            img = gray + (img - gray) * saturation

        # 따뜻함 (R/B 채널 조정)
        if warmth != 0:
            img[:, :, 0] = img[:, :, 0] + warmth * 0.1  # R
            img[:, :, 2] = img[:, :, 2] - warmth * 0.1  # B

        # 클리핑 및 변환
        img = np.clip(img, 0, 1)
        return (img * 255).astype(np.uint8)

    return clip.image_transform(process_frame)


def apply_lut_style(clip: VideoFileClip, style: str) -> VideoFileClip:
    """
    미리 정의된 LUT 스타일 적용

    Args:
        clip: 원본 클립
        style: 스타일 이름 ("high_contrast", "filmic", "vibrant", "moody", "warm", "cool")
    """
    # 스타일별 파라미터 정의
    styles = {
        "high_contrast": {
            "brightness": 0.0,
            "contrast": 1.3,
            "saturation": 1.1,
            "warmth": 0.05
        },
        "filmic": {
            "brightness": -0.02,
            "contrast": 1.1,
            "saturation": 0.9,
            "warmth": 0.1
        },
        "vibrant": {
            "brightness": 0.05,
            "contrast": 1.15,
            "saturation": 1.3,
            "warmth": 0.0
        },
        "moody": {
            "brightness": -0.05,
            "contrast": 1.2,
            "saturation": 0.85,
            "warmth": -0.1
        },
        "warm": {
            "brightness": 0.02,
            "contrast": 1.05,
            "saturation": 1.05,
            "warmth": 0.2
        },
        "cool": {
            "brightness": 0.0,
            "contrast": 1.1,
            "saturation": 0.95,
            "warmth": -0.15
        },
        "default": {
            "brightness": 0.0,
            "contrast": 1.0,
            "saturation": 1.0,
            "warmth": 0.0
        }
    }

    params = styles.get(style, styles["default"])
    return apply_color_adjustment(clip, **params)


def apply_vignette(
    clip: VideoFileClip,
    strength: float = 0.3,
    radius: float = 1.0
) -> VideoFileClip:
    """
    비네팅 효과 적용

    Args:
        clip: 원본 클립
        strength: 비네팅 강도 (0.0 ~ 1.0)
        radius: 비네팅 반경 (작을수록 좁음)
    """
    def process_frame(frame):
        h, w = frame.shape[:2]

        # 중심으로부터의 거리 계산
        y, x = np.ogrid[:h, :w]
        center_y, center_x = h / 2, w / 2

        # 정규화된 거리
        distance = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        max_distance = np.sqrt(center_x**2 + center_y**2) * radius

        # 비네팅 마스크 (가장자리로 갈수록 어두워짐)
        vignette = 1 - (distance / max_distance) ** 2 * strength
        vignette = np.clip(vignette, 0, 1)

        # 적용
        result = frame.astype(np.float32)
        result = result * vignette[:, :, np.newaxis]

        return result.astype(np.uint8)

    return clip.image_transform(process_frame)
