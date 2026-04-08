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
        """
        분석 결과를 FrameAnalysis 스키마에 맞게 정규화.
        새 포스터 선별 필드(poster_score 등) + 구 필드 모두 지원.
        """
        # ── 포스터 선별 신규 필드 ───────────────────────────────
        runner_detected = bool(data.get("runner_detected", False))
        runner_cx       = float(data.get("runner_center_x", 0.5))
        runner_cy       = float(data.get("runner_center_y", 0.5))
        runner_size     = float(data.get("runner_size", 0.0))
        limb_spread     = float(data.get("limb_spread", 0.0))
        face_expr       = str(data.get("face_expression", "neutral"))
        poster_score    = float(data.get("poster_score", 0.0))

        # 탈락 조건 자동 적용 (Qwen이 놓친 경우 방어)
        if runner_detected:
            if runner_size < 0.15:
                poster_score = 0.0
            elif runner_cx < 0.10 or runner_cx > 0.90:
                poster_score = 0.0
        else:
            poster_score = 0.0

        # ── 구 필드 (하위 호환) ─────────────────────────────────
        # 새 응답에서는 없을 수 있으므로 poster_score 기반으로 파생
        aesthetic  = float(data.get("aesthetic_score",  poster_score))
        comp_score = float(data.get("composition_score", poster_score))
        motion     = float(data.get("motion_level",      limb_spread))
        is_peak    = bool(data.get("is_action_peak",     poster_score > 0.6))

        return {
            # 신규
            "runner_detected":       runner_detected,
            "runner_center_x":       round(runner_cx, 3),
            "runner_center_y":       round(runner_cy, 3),
            "runner_size":           round(runner_size, 3),
            "limb_spread":           round(limb_spread, 3),
            "face_expression_quality": face_expr,
            "poster_score":          round(poster_score, 3),
            # 구 (호환)
            "faces_detected":        int(data.get("faces_detected", 1 if bool(data.get("face_visible")) else 0)),
            "face_expressions":      data.get("face_expressions", [face_expr] if face_expr != "neutral" else []),
            "motion_level":          round(motion, 3),
            "composition_score":     round(comp_score, 3),
            "lighting":              str(data.get("lighting", "moderate")),
            "background_type":       str(data.get("background_type", "outdoor")),
            "is_action_peak":        is_peak,
            "aesthetic_score":       round(aesthetic, 3),
            "emotional_tone":        str(data.get("emotional_tone", face_expr)),
            "description":           str(data.get("description", "")),
        }

    def _default_analysis(self) -> dict:
        """파싱 실패 시 기본값"""
        return {
            "runner_detected": False,
            "runner_center_x": 0.5, "runner_center_y": 0.5,
            "runner_size": 0.0, "limb_spread": 0.0,
            "face_expression_quality": "neutral",
            "poster_score": 0.0,
            "faces_detected": 0,
            "face_expressions": [],
            "motion_level": 0.5,
            "composition_score": 0.5,
            "lighting": "moderate",
            "background_type": "unknown",
            "is_action_peak": False,
            "aesthetic_score": 0.5,
            "emotional_tone": "neutral",
            "description": "분석 실패",
        }

    async def close(self):
        """호환성을 위한 빈 메서드"""
        pass


class FrameAnalyzer:
    """Qwen API를 사용한 프레임 분석기.

    핵심 최적화:
      - analyze_frames_batch(): N개 프레임을 이미지 여러 장으로 한 번에 전송
        → 기존 N번 API 호출 대비 ~5x 속도 향상
      - 기본 모델: qwen-vl-plus (max 대비 2x 빠름, 프레임 선별엔 충분)
    """

    API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    # 배치 분석용 짧은 프롬프트 (응답 토큰 최소화 → 속도 향상)
    BATCH_PROMPT = """러닝 영상 프레임 {n}장을 포스터 적합도 기준으로 평가한다.
각 이미지(Image 1, Image 2, ...)에 대해 아래 JSON 배열을 반환해라.
탈락 조건(poster_score=0): 러너 없음 / 크기<15% / x 위치<10% 또는 >90%.

[
  {{"frame": 1, "runner_detected": true/false, "runner_center_x": 0.0~1.0, "runner_center_y": 0.0~1.0, "runner_size": 0.0~1.0, "limb_spread": 0.0~1.0, "face_expression": "positive"|"neutral"|"negative", "poster_score": 0.0~1.0}},
  ...
]
JSON 배열만 반환, 설명 없이."""

    def __init__(self, api_key: str, model: str = "qwen-vl-plus"):
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
        # OllamaFrameAnalyzer._normalize_analysis와 동일 로직 공유
        return OllamaFrameAnalyzer._normalize_analysis(None, data)  # type: ignore

    def _default_analysis(self) -> dict:
        return OllamaFrameAnalyzer._default_analysis(None)  # type: ignore

    async def analyze_frames_batch(
        self,
        frames_data: list,   # List[Tuple[float, np.ndarray]]
        max_retries: int = 3,
    ) -> list:               # List[FrameAnalysis]
        """
        N개 프레임을 단일 API 호출로 한 번에 분석 (배치 최적화).

        기존 N번 순차/병렬 호출 → 1번 호출로 단축.
        Qwen VL API는 한 메시지에 최대 20장 이미지 지원.

        Args:
            frames_data: [(timestamp, frame_numpy), ...]
            max_retries: 최대 재시도 횟수
        Returns:
            FrameAnalysis 리스트 (입력 순서와 동일)
        """
        if not frames_data:
            return []

        # 프레임들을 base64로 인코딩
        content = []
        for ts, frame in frames_data:
            b64 = self._encode_frame(frame)
            content.append({"image": f"data:image/jpeg;base64,{b64}"})

        # 배치 프롬프트 (이미지 수 주입)
        prompt_text = self.BATCH_PROMPT.format(n=len(frames_data))
        content.append({"text": prompt_text})

        payload = {
            "model": self.model,
            "input": {
                "messages": [{"role": "user", "content": content}]
            },
            "parameters": {"result_format": "message"}
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                async with session.post(
                    self.API_URL, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        raise APIError("Qwen", f"HTTP {resp.status}: {await resp.text()}")
                    result  = await resp.json()
                    message = result.get("output", {}).get("choices", [{}])[0] \
                                    .get("message", {}).get("content", "")
                    if not message:
                        raise AnalysisError("빈 응답")

                    # JSON 배열 파싱
                    return self._parse_batch_response(message, frames_data)

            except (aiohttp.ClientError, AnalysisError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        # 실패 시 개별 프레임 분석으로 fallback
        print(f"  [배치 실패] 개별 분석으로 전환: {last_error}")
        results = []
        for ts, frame in frames_data:
            fa = await self.analyze_frame(frame, ts, "")
            results.append(fa)
        return results

    def _parse_batch_response(self, text: str, frames_data: list) -> list:
        """배치 응답 JSON 배열 → FrameAnalysis 리스트"""
        import re
        text = text.strip()
        # 코드블록 제거
        text = re.sub(r"```json|```", "", text).strip()

        try:
            items = json.loads(text)
            if not isinstance(items, list):
                items = [items]
        except json.JSONDecodeError:
            arr_match = re.search(r"\[.*\]", text, re.DOTALL)
            if arr_match:
                try:
                    items = json.loads(arr_match.group())
                except Exception:
                    items = []
            else:
                items = []

        results = []
        for idx, (ts, _) in enumerate(frames_data):
            raw = items[idx] if idx < len(items) else {}
            normalized = self._normalize_analysis(raw)
            normalized["timestamp"] = ts
            results.append(FrameAnalysis(**normalized))
        return results


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
