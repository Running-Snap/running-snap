"""
단일 프레임 분석기
Ollama 로컬 모델 또는 Qwen API를 사용해 개별 프레임을 분석
"""
import base64
import json
import asyncio
import aiohttp
import subprocess
from typing import Optional
import numpy as np
import cv2

from ..core.models import FrameAnalysis
from ..core.exceptions import APIError, AnalysisError


class OllamaFrameAnalyzer:
    """Ollama 로컬 비전 모델을 사용한 프레임 분석기"""

    def __init__(self, model: str = "qwen2.5vl:7b"):
        """
        Args:
            model: Ollama 비전 모델 이름
        """
        self.model = model

    def _encode_frame(self, frame: np.ndarray) -> str:
        """프레임을 base64로 인코딩"""
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise AnalysisError("프레임 인코딩 실패")

        return base64.b64encode(buffer).decode('utf-8')

    async def analyze_frame(
        self,
        frame: np.ndarray,
        timestamp: float,
        analysis_prompt: str,
        max_retries: int = 3
    ) -> FrameAnalysis:
        """
        Ollama로 단일 프레임 분석

        Args:
            frame: 분석할 프레임 (numpy array)
            timestamp: 프레임의 타임스탬프 (초)
            analysis_prompt: 분석 지시 프롬프트
            max_retries: 최대 재시도 횟수

        Returns:
            FrameAnalysis 객체
        """
        image_base64 = self._encode_frame(frame)

        # Ollama API 요청 형식
        payload = {
            "model": self.model,
            "prompt": analysis_prompt,
            "images": [image_base64],
            "stream": False
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://localhost:11434/api/generate",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=300)  # 5분 타임아웃
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise APIError("Ollama", f"API 에러 ({response.status}): {error_text}")

                        result = await response.json()
                        message = result.get("response", "")

                        if not message:
                            raise AnalysisError("빈 응답")

                        analysis_data = self._parse_response(message)
                        analysis_data["timestamp"] = timestamp

                        return FrameAnalysis(**analysis_data)

            except aiohttp.ClientError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
            except json.JSONDecodeError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                continue

        raise AnalysisError(f"프레임 분석 실패 (timestamp={timestamp}): {last_error}")

    def _parse_response(self, response_text: str) -> dict:
        """응답에서 JSON 추출 및 파싱"""
        text = response_text.strip()

        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = self._default_analysis()

        return self._normalize_analysis(data)

    def _normalize_analysis(self, data: dict) -> dict:
        """분석 결과를 FrameAnalysis 스키마에 맞게 정규화"""
        return {
            "faces_detected": int(data.get("faces_detected", 0)),
            "face_expressions": data.get("face_expressions", []),
            "motion_level": float(data.get("motion_level", 0.5)),
            "composition_score": float(data.get("composition_score", 0.5)),
            "lighting": str(data.get("lighting", "moderate")),
            "background_type": str(data.get("background_type", "unknown")),
            "is_action_peak": bool(data.get("is_action_peak", False)),
            "aesthetic_score": float(data.get("aesthetic_score", 0.5)),
            "emotional_tone": str(data.get("emotional_tone", "neutral")),
            "description": str(data.get("description", ""))
        }

    def _default_analysis(self) -> dict:
        """파싱 실패 시 기본값"""
        return {
            "faces_detected": 0,
            "face_expressions": [],
            "motion_level": 0.5,
            "composition_score": 0.5,
            "lighting": "moderate",
            "background_type": "unknown",
            "is_action_peak": False,
            "aesthetic_score": 0.5,
            "emotional_tone": "neutral",
            "description": "분석 실패"
        }

    async def close(self):
        """호환성을 위한 빈 메서드"""
        pass


class FrameAnalyzer:
    """Qwen API를 사용한 프레임 분석기 (기존 호환성 유지)"""

    API_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    def __init__(self, api_key: str, model: str = "qwen-vl-max"):
        self.api_key = api_key
        self.model = model
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _encode_frame(self, frame: np.ndarray) -> str:
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise AnalysisError("프레임 인코딩 실패")

        return base64.b64encode(buffer).decode('utf-8')

    async def analyze_frame(
        self,
        frame: np.ndarray,
        timestamp: float,
        analysis_prompt: str,
        max_retries: int = 3
    ) -> FrameAnalysis:
        image_base64 = self._encode_frame(frame)

        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": f"data:image/jpeg;base64,{image_base64}"},
                            {"text": analysis_prompt}
                        ]
                    }
                ]
            },
            "parameters": {"result_format": "message"}
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                async with session.post(
                    self.API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise APIError("Qwen", f"API 에러 ({response.status}): {error_text}")

                    result = await response.json()
                    content = result.get("output", {}).get("choices", [{}])[0]
                    message = content.get("message", {}).get("content", "")

                    if not message:
                        raise AnalysisError("빈 응답")

                    analysis_data = self._parse_response(message)
                    analysis_data["timestamp"] = timestamp

                    return FrameAnalysis(**analysis_data)

            except aiohttp.ClientError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
            except json.JSONDecodeError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                continue

        raise AnalysisError(f"프레임 분석 실패 (timestamp={timestamp}): {last_error}")

    def _parse_response(self, response_text: str) -> dict:
        text = response_text.strip()

        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = self._default_analysis()

        return self._normalize_analysis(data)

    def _normalize_analysis(self, data: dict) -> dict:
        return {
            "faces_detected": int(data.get("faces_detected", 0)),
            "face_expressions": data.get("face_expressions", []),
            "motion_level": float(data.get("motion_level", 0.5)),
            "composition_score": float(data.get("composition_score", 0.5)),
            "lighting": str(data.get("lighting", "moderate")),
            "background_type": str(data.get("background_type", "unknown")),
            "is_action_peak": bool(data.get("is_action_peak", False)),
            "aesthetic_score": float(data.get("aesthetic_score", 0.5)),
            "emotional_tone": str(data.get("emotional_tone", "neutral")),
            "description": str(data.get("description", ""))
        }

    def _default_analysis(self) -> dict:
        return {
            "faces_detected": 0,
            "face_expressions": [],
            "motion_level": 0.5,
            "composition_score": 0.5,
            "lighting": "moderate",
            "background_type": "unknown",
            "is_action_peak": False,
            "aesthetic_score": 0.5,
            "emotional_tone": "neutral",
            "description": "분석 실패"
        }


class MockFrameAnalyzer:
    """테스트용 Mock Analyzer"""

    def __init__(self):
        self.model = "mock"

    async def analyze_frame(
        self,
        frame: np.ndarray,
        timestamp: float,
        analysis_prompt: str,
        max_retries: int = 3
    ) -> FrameAnalysis:
        import random

        base_motion = 0.3 + (timestamp % 5) * 0.1
        is_peak = random.random() > 0.7

        return FrameAnalysis(
            timestamp=timestamp,
            faces_detected=random.randint(0, 2),
            face_expressions=random.choice([["focused"], ["determined"], ["joyful"], []]),
            motion_level=min(1.0, base_motion + random.uniform(-0.1, 0.2)),
            composition_score=random.uniform(0.5, 0.9),
            lighting=random.choice(["good", "moderate", "good"]),
            background_type=random.choice(["outdoor_nature", "urban", "track"]),
            is_action_peak=is_peak,
            aesthetic_score=random.uniform(0.4, 0.95),
            emotional_tone=random.choice(["determined", "focused", "joyful", "struggling"]),
            description=f"Frame at {timestamp:.1f}s - {'action peak' if is_peak else 'normal moment'}"
        )

    async def close(self):
        pass
