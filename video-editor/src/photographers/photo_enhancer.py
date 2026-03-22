"""
사진 후보정기
프로 사진작가 스타일의 후보정 적용
"""
from pathlib import Path
from typing import Optional, Union, Tuple, List
import colorsys
import numpy as np
import cv2
from PIL import Image, ImageEnhance
from rich.console import Console

from ..core.config_loader import ConfigLoader
from ..core.exceptions import PhotoProcessingError


class PhotoEnhancer:
    """프로 사진작가 스타일 후보정기"""

    def __init__(
        self,
        config_loader: ConfigLoader,
        console: Optional[Console] = None
    ):
        self.config = config_loader
        self.console = console or Console()

        # 설정 로드
        self.pipeline = config_loader.get_enhancement_pipeline()
        self.presets = self._load_presets()

    def _load_presets(self) -> dict:
        """프리셋 로드"""
        try:
            config = self.config._load_yaml("photo_grading.yaml")
            return config.get("presets", {})
        except Exception:
            return {}

    def enhance(
        self,
        image: Union[str, np.ndarray, Image.Image],
        preset: str = "sports_action"
    ) -> Image.Image:
        """
        사진 후보정 파이프라인

        Args:
            image: 입력 이미지 (경로, numpy array, 또는 PIL Image)
            preset: 보정 프리셋 이름

        Returns:
            보정된 PIL Image
        """
        # 이미지 로드
        img = self._load_image(image)

        # 기본 보정 파이프라인
        img = self._apply_basic_adjustments(img)

        # 색감 보정
        img = self._apply_color_grading(img)

        # 프리셋 적용
        if preset in self.presets:
            img = self._apply_preset(img, preset)

        # 샤프닝
        img = self._apply_sharpening(img)

        # 비네팅
        img = self._apply_vignette(img)

        return img

    def _load_image(
        self,
        image: Union[str, np.ndarray, Image.Image]
    ) -> Image.Image:
        """이미지를 PIL Image로 로드"""
        if isinstance(image, str):
            path = Path(image)
            if not path.exists():
                raise PhotoProcessingError(f"이미지 파일이 없습니다: {path}")
            return Image.open(path).convert("RGB")

        elif isinstance(image, np.ndarray):
            # BGR to RGB (OpenCV)
            if len(image.shape) == 3 and image.shape[2] == 3:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            return Image.fromarray(image)

        elif isinstance(image, Image.Image):
            return image.convert("RGB")

        else:
            raise PhotoProcessingError(f"지원하지 않는 이미지 타입: {type(image)}")

    def _apply_basic_adjustments(self, img: Image.Image) -> Image.Image:
        """기본 보정 (노출, 대비, 하이라이트/섀도우)"""
        basic = self.pipeline.get("basic_adjustments", {})

        # 대비
        contrast = basic.get("contrast", 1.0)
        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast)

        # 밝기 (하이라이트/섀도우 간소화 버전)
        highlights = basic.get("highlights", 0)
        shadows = basic.get("shadows", 0)

        if highlights != 0 or shadows != 0:
            img = self._adjust_highlights_shadows(img, highlights, shadows)

        return img

    def _adjust_highlights_shadows(
        self,
        img: Image.Image,
        highlights: float,
        shadows: float
    ) -> Image.Image:
        """하이라이트/섀도우 조정"""
        arr = np.array(img).astype(np.float32) / 255.0

        # 밝기 기준 마스크
        luminance = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

        # 하이라이트 영역 (밝은 부분)
        highlight_mask = np.clip((luminance - 0.5) * 2, 0, 1)
        # 섀도우 영역 (어두운 부분)
        shadow_mask = np.clip((0.5 - luminance) * 2, 0, 1)

        # 조정 적용
        for c in range(3):
            # 하이라이트 조정 (밝은 부분 더 밝게/어둡게)
            arr[:, :, c] = arr[:, :, c] + highlight_mask * highlights * 0.3
            # 섀도우 조정 (어두운 부분 더 밝게/어둡게)
            arr[:, :, c] = arr[:, :, c] + shadow_mask * shadows * 0.3

        arr = np.clip(arr, 0, 1)
        return Image.fromarray((arr * 255).astype(np.uint8))

    def _apply_color_grading(self, img: Image.Image) -> Image.Image:
        """색감 보정"""
        color = self.pipeline.get("color_grading", {})

        # 채도 (Vibrance - 피부톤 보호 버전은 복잡하므로 일반 채도로)
        vibrance = color.get("vibrance", 0)
        saturation = color.get("saturation", 0)
        total_saturation = 1.0 + vibrance + saturation

        if total_saturation != 1.0:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(total_saturation)

        # 톤 커브 (S-curve)
        tone_curve = color.get("tone_curve", "")
        if tone_curve == "s_curve_gentle" or tone_curve == "s_curve":
            img = self._apply_s_curve(img)

        # 스플릿 토닝
        split_toning = color.get("split_toning", {})
        if split_toning:
            img = self._apply_split_toning(img, split_toning)

        return img

    def _apply_s_curve(self, img: Image.Image, strength: float = 0.2) -> Image.Image:
        """S-커브 톤 적용 (대비 증가)"""
        arr = np.array(img).astype(np.float32) / 255.0

        # S-curve 함수: 중간톤 대비 증가
        # sigmoid 변형 사용
        midpoint = 0.5
        arr = midpoint + (arr - midpoint) * (1 + strength * np.abs(arr - midpoint) * 2)

        arr = np.clip(arr, 0, 1)
        return Image.fromarray((arr * 255).astype(np.uint8))

    def _apply_split_toning(
        self,
        img: Image.Image,
        settings: dict
    ) -> Image.Image:
        """스플릿 토닝 (하이라이트/섀도우에 다른 색상)"""
        arr = np.array(img).astype(np.float32) / 255.0

        # 밝기 계산
        luminance = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

        # 하이라이트 색상 (따뜻한 톤)
        h_hue = settings.get("highlights_hue", 45) / 360.0  # 0-360 -> 0-1
        h_sat = settings.get("highlights_saturation", 0.1)

        # 섀도우 색상 (차가운 톤)
        s_hue = settings.get("shadows_hue", 220) / 360.0
        s_sat = settings.get("shadows_saturation", 0.05)

        balance = settings.get("balance", 0.5)

        # 하이라이트 마스크 (밝은 영역)
        h_mask = np.clip((luminance - balance) / (1 - balance + 0.001), 0, 1)
        # 섀도우 마스크 (어두운 영역)
        s_mask = np.clip((balance - luminance) / (balance + 0.001), 0, 1)

        # 색상을 RGB로 변환 (간소화)
        h_color = self._hue_to_rgb(h_hue)
        s_color = self._hue_to_rgb(s_hue)

        # 적용
        for c in range(3):
            arr[:, :, c] = arr[:, :, c] + h_mask * h_color[c] * h_sat
            arr[:, :, c] = arr[:, :, c] + s_mask * s_color[c] * s_sat

        arr = np.clip(arr, 0, 1)
        return Image.fromarray((arr * 255).astype(np.uint8))

    def _hue_to_rgb(self, hue: float) -> Tuple[float, float, float]:
        """Hue 값을 RGB로 변환 (채도=1, 명도=1 가정)"""
        r, g, b = colorsys.hsv_to_rgb(hue, 0.5, 1.0)
        return (r - 0.5, g - 0.5, b - 0.5)  # 중심을 0으로

    def _apply_preset(self, img: Image.Image, preset_name: str) -> Image.Image:
        """프리셋 적용"""
        preset = self.presets.get(preset_name, {})
        adjustments = preset.get("adjustments", {})

        # 대비
        if "contrast" in adjustments:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(adjustments["contrast"])

        # 명료도 (Clarity) - 로컬 대비로 구현
        if "clarity" in adjustments and adjustments["clarity"] > 0:
            img = self._apply_clarity(img, adjustments["clarity"])

        # 채도
        if "vibrance" in adjustments:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.0 + adjustments["vibrance"])

        # 밝기
        if "exposure" in adjustments:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.0 + adjustments["exposure"])

        return img

    def _apply_clarity(self, img: Image.Image, strength: float) -> Image.Image:
        """명료도 (로컬 대비) 적용"""
        # 하이패스 필터로 디테일 강조
        arr = np.array(img).astype(np.float32)

        # 블러 버전
        blurred = cv2.GaussianBlur(arr, (0, 0), 10)

        # 하이패스 = 원본 - 블러
        high_pass = arr - blurred

        # 원본에 하이패스 추가
        result = arr + high_pass * strength
        result = np.clip(result, 0, 255)

        return Image.fromarray(result.astype(np.uint8))

    def _apply_sharpening(self, img: Image.Image) -> Image.Image:
        """샤프닝 적용"""
        sharpening = self.pipeline.get("sharpening", {})
        amount = sharpening.get("amount", 0.3)

        if amount <= 0:
            return img

        # Unsharp Mask
        arr = np.array(img).astype(np.float32)
        blurred = cv2.GaussianBlur(arr, (0, 0), sharpening.get("radius", 1.0))

        # 샤프닝: 원본 + (원본 - 블러) * amount
        sharpened = arr + (arr - blurred) * amount
        sharpened = np.clip(sharpened, 0, 255)

        return Image.fromarray(sharpened.astype(np.uint8))

    def _apply_vignette(self, img: Image.Image) -> Image.Image:
        """비네팅 적용"""
        vignette = self.pipeline.get("vignette", {})
        amount = abs(vignette.get("amount", 0))

        if amount <= 0:
            return img

        arr = np.array(img).astype(np.float32) / 255.0
        h, w = arr.shape[:2]

        # 중심으로부터의 거리
        y, x = np.ogrid[:h, :w]
        center_y, center_x = h / 2, w / 2

        midpoint = vignette.get("midpoint", 0.5)
        max_dist = np.sqrt(center_x**2 + center_y**2) * midpoint * 2

        distance = np.sqrt((x - center_x)**2 + (y - center_y)**2)

        # 비네팅 마스크
        vignette_mask = 1 - np.clip(distance / max_dist, 0, 1) ** 2 * amount
        vignette_mask = vignette_mask[:, :, np.newaxis]

        arr = arr * vignette_mask
        arr = np.clip(arr, 0, 1)

        return Image.fromarray((arr * 255).astype(np.uint8))

    def save(
        self,
        image: Image.Image,
        output_path: str,
        format: str = "jpeg",
        quality: int = 95
    ) -> str:
        """보정된 이미지 저장"""
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # 포맷에 따른 저장
        if format.lower() in ["jpg", "jpeg"]:
            image.save(str(output_path_obj), "JPEG", quality=quality, optimize=True)
        elif format.lower() == "png":
            image.save(str(output_path_obj), "PNG", optimize=True)
        else:
            image.save(str(output_path_obj))

        return str(output_path_obj)

    def enhance_and_save(
        self,
        input_path: str,
        output_path: str,
        preset: str = "sports_action",
        format: str = "jpeg",
        quality: int = 95
    ) -> str:
        """보정 후 저장 (한번에)"""
        img = self.enhance(input_path, preset)
        return self.save(img, output_path, format, quality)

    def batch_enhance(
        self,
        input_paths: List[str],
        output_dir: str,
        preset: str = "sports_action",
        format: str = "jpeg",
        quality: int = 95
    ) -> List[str]:
        """여러 이미지 배치 보정"""
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        saved_paths = []

        for input_path in input_paths:
            input_path_obj = Path(input_path)
            output_path = output_dir_path / f"{input_path_obj.stem}_enhanced.{format}"

            try:
                saved = self.enhance_and_save(
                    str(input_path_obj),
                    str(output_path),
                    preset,
                    format,
                    quality
                )
                saved_paths.append(saved)
                self.console.print(f"[dim]✓ {input_path_obj.name}[/dim]")
            except Exception as e:
                self.console.print(f"[red]✗ {input_path_obj.name}: {e}[/red]")

        return saved_paths
