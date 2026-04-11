"""YAML 설정 파일 로더"""
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from .exceptions import ConfigError
from .models import DurationType


class ConfigLoader:
    """설정 파일 관리자"""

    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}
        self._validate_config_dir()

    def _validate_config_dir(self):
        if not self.config_dir.exists():
            raise ConfigError(f"설정 디렉토리가 없습니다: {self.config_dir}")

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """YAML 파일 로드 (캐싱)"""
        if filename in self._cache:
            return self._cache[filename]

        filepath = self.config_dir / filename
        if not filepath.exists():
            raise ConfigError(f"설정 파일이 없습니다: {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                self._cache[filename] = data
                return data
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML 파싱 에러 ({filename}): {e}")

    def get_analysis_profile(self, duration_type: DurationType) -> Dict[str, Any]:
        """영상 길이에 맞는 분석 프로파일 반환"""
        config = self._load_yaml("analysis_profiles.yaml")
        profile = config.get("profiles", {}).get(duration_type.value)
        if not profile:
            raise ConfigError(f"분석 프로파일이 없습니다: {duration_type.value}")

        # 공통 분석 항목 병합
        common = config.get("common_analysis", [])
        profile["common_analysis"] = common
        return profile

    # ============================================================
    # 새로운 스타일 시스템 (v3.0)
    # ============================================================

    def get_style(self, style_name: str) -> Dict[str, Any]:
        """
        스타일 전체 설정 반환 (새 구조)

        Returns:
            {
                "name": str,
                "description": str,
                "defaults": {"color_grade": str, ...},
                "allowed": {"effects": [], "transitions": [], ...},
                "prompt": str
            }
        """
        config = self._load_yaml("script_prompts.yaml")
        style = config.get("styles", {}).get(style_name)
        if not style:
            available = self.get_available_styles()
            raise ConfigError(f"편집 스타일이 없습니다: {style_name}. 사용 가능: {available}")
        return style

    def get_style_defaults(self, style_name: str) -> Dict[str, Any]:
        """스타일 기본값 반환 (렌더러에서 사용)"""
        style = self.get_style(style_name)
        return style.get("defaults", {})

    def get_style_allowed(self, style_name: str) -> Dict[str, Any]:
        """스타일에서 허용된 옵션 반환 (검증에서 사용)"""
        style = self.get_style(style_name)
        return style.get("allowed", {})

    def get_style_prompt(self, style_name: str) -> str:
        """스타일별 프롬프트 반환"""
        style = self.get_style(style_name)
        return style.get("prompt", "")

    def get_available_styles(self) -> List[str]:
        """사용 가능한 편집 스타일 목록"""
        config = self._load_yaml("script_prompts.yaml")
        return list(config.get("styles", {}).keys())

    def get_system_prompt(self) -> str:
        """공통 시스템 프롬프트 반환"""
        config = self._load_yaml("script_prompts.yaml")
        return config.get("system_prompt", "")

    def get_validation_rules(self) -> Dict[str, Any]:
        """검증 규칙 반환"""
        config = self._load_yaml("script_prompts.yaml")
        return config.get("validation", {})

    def get_script_prompt(self, duration_type: DurationType, style_name: str) -> str:
        """
        완성된 LLM 프롬프트 반환 (새 구조)

        system_prompt + style_prompt 조합
        """
        system_prompt = self.get_system_prompt()
        style_prompt = self.get_style_prompt(style_name)
        style = self.get_style(style_name)

        # 허용된 옵션을 명시적으로 포함
        allowed = style.get("allowed", {})
        allowed_section = self._format_allowed_options(allowed)

        full_prompt = f"""{system_prompt}

{style_prompt}

---

## 이 스타일에서 허용된 옵션

{allowed_section}
"""
        return full_prompt

    def _format_allowed_options(self, allowed: Dict[str, Any]) -> str:
        """허용된 옵션을 프롬프트용 텍스트로 포맷"""
        parts = []

        effects = allowed.get("effects", [])
        if effects:
            parts.append(f"- 사용 가능한 effects: {effects}")
        else:
            parts.append("- effects: 사용하지 마라 (빈 배열로)")

        transitions = allowed.get("transitions", [])
        parts.append(f"- 사용 가능한 transitions: {transitions}")

        color_grades = allowed.get("color_grades", [])
        parts.append(f"- 사용 가능한 color_grades: {color_grades}")

        speed_range = allowed.get("speed_range", {})
        if speed_range:
            parts.append(f"- speed 범위: {speed_range.get('min', 0.3)} ~ {speed_range.get('max', 2.0)}")

        return "\n".join(parts)

    # ============================================================
    # 하위 호환성을 위한 래퍼 (deprecated)
    # ============================================================

    def get_editing_style(self, style_name: str) -> Dict[str, Any]:
        """
        [DEPRECATED] 이전 버전 호환용
        새 코드에서는 get_style() 사용 권장
        """
        style = self.get_style(style_name)
        # 이전 구조로 변환
        return {
            "name": style.get("name", style_name),
            "description": style.get("description", ""),
            "prompt_modifier": style.get("prompt", ""),
            "characteristics": {
                "color_tone": style.get("defaults", {}).get("color_grade", "default"),
                "transitions": style.get("allowed", {}).get("transitions", []),
            }
        }

    # ============================================================
    # 기타 설정 로더
    # ============================================================

    def get_photo_selection_criteria(self) -> Dict[str, Any]:
        """베스트컷 선정 기준"""
        config = self._load_yaml("photo_grading.yaml")
        return config.get("selection_criteria", {})

    def get_enhancement_pipeline(self) -> Dict[str, Any]:
        """사진 보정 파이프라인 설정"""
        config = self._load_yaml("photo_grading.yaml")
        return config.get("enhancement_pipeline", {})

    def get_photo_preset(self, preset_name: str) -> Dict[str, Any]:
        """사진 보정 프리셋"""
        config = self._load_yaml("photo_grading.yaml")
        preset = config.get("presets", {}).get(preset_name)
        if not preset:
            return config.get("presets", {}).get("sports_action", {})
        return preset

    def get_output_specs(self, platform: str = "default") -> Dict[str, Any]:
        """출력 사양"""
        config = self._load_yaml("output_specs.yaml")
        return config.get(platform, config.get("default", {}))

    def get_composition_style(self, style_name: str) -> Dict[str, Any]:
        """구도 스타일 설정"""
        config = self._load_yaml("composition_styles.yaml")
        return config.get("style_mappings", {}).get(style_name, {})

    def reload(self):
        """캐시 초기화 (설정 파일 수정 후 리로드)"""
        self._cache.clear()
