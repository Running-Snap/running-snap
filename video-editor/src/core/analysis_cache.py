"""
분석 결과 캐시 시스템
영상 분석 결과와 LLM 대본을 저장/로드하여 재사용
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from rich.console import Console

from .models import VideoAnalysis, FrameAnalysis, EditScript, EditSegment, DurationType


class AnalysisCache:
    """분석 결과 캐시 관리자"""

    def __init__(
        self,
        cache_dir: str = "outputs/cache",
        console: Optional[Console] = None
    ):
        """
        Args:
            cache_dir: 캐시 저장 디렉토리
            console: Rich 콘솔
        """
        self.cache_dir = Path(cache_dir)
        self.analysis_dir = self.cache_dir / "analysis"
        self.scripts_dir = self.cache_dir / "scripts"
        self.console = console or Console()

        # 디렉토리 생성
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

    def _get_video_hash(self, video_path: str) -> str:
        """영상 파일의 해시값 생성 (파일명 + 크기 + 수정시간 기반)"""
        path = Path(video_path)
        if not path.exists():
            return ""

        stat = path.stat()
        hash_input = f"{path.name}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    def _get_analysis_path(self, video_path: str) -> Path:
        """분석 결과 저장 경로"""
        video_name = Path(video_path).stem
        video_hash = self._get_video_hash(video_path)
        return self.analysis_dir / f"{video_name}_{video_hash}_analysis.json"

    def _get_script_path(self, video_path: str, style: str, target_duration: float) -> Path:
        """대본 저장 경로"""
        video_name = Path(video_path).stem
        video_hash = self._get_video_hash(video_path)
        return self.scripts_dir / f"{video_name}_{video_hash}_{style}_{int(target_duration)}s_script.json"

    # ==================== 분석 결과 캐시 ====================

    def save_analysis(self, video_path: str, analysis: VideoAnalysis) -> str:
        """
        분석 결과 저장

        Args:
            video_path: 원본 영상 경로
            analysis: 분석 결과

        Returns:
            저장된 파일 경로
        """
        save_path = self._get_analysis_path(video_path)

        # VideoAnalysis를 JSON으로 변환
        data = {
            "meta": {
                "video_path": str(video_path),
                "video_name": Path(video_path).name,
                "video_hash": self._get_video_hash(video_path),
                "analyzed_at": datetime.now().isoformat(),
                "analyzer": "qwen2.5vl:7b"
            },
            "analysis": {
                "source_path": analysis.source_path,
                "duration": analysis.duration,
                "fps": analysis.fps,
                "resolution": list(analysis.resolution),
                "duration_type": analysis.duration_type.value,
                "highlights": analysis.highlights,
                "overall_motion": analysis.overall_motion,
                "dominant_lighting": analysis.dominant_lighting,
                "summary": analysis.summary,
                "frames": [
                    {
                        "timestamp": f.timestamp,
                        "faces_detected": f.faces_detected,
                        "face_expressions": f.face_expressions,
                        "motion_level": f.motion_level,
                        "composition_score": f.composition_score,
                        "lighting": f.lighting,
                        "background_type": f.background_type,
                        "is_action_peak": f.is_action_peak,
                        "aesthetic_score": f.aesthetic_score,
                        "emotional_tone": f.emotional_tone,
                        "description": f.description
                    }
                    for f in analysis.frames
                ]
            }
        }

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.console.print(f"[dim]분석 결과 저장됨: {save_path}[/dim]")
        return str(save_path)

    def load_analysis(self, video_path: str) -> Optional[VideoAnalysis]:
        """
        캐시된 분석 결과 로드

        Args:
            video_path: 원본 영상 경로

        Returns:
            VideoAnalysis 또는 None (캐시 없음)
        """
        cache_path = self._get_analysis_path(video_path)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 해시 검증 (영상이 변경되었는지 확인)
            current_hash = self._get_video_hash(video_path)
            cached_hash = data.get("meta", {}).get("video_hash", "")

            if current_hash != cached_hash:
                self.console.print("[yellow]영상이 변경되어 캐시를 무효화합니다[/yellow]")
                return None

            # JSON을 VideoAnalysis로 변환
            analysis_data = data["analysis"]

            frames = [
                FrameAnalysis(
                    timestamp=f["timestamp"],
                    faces_detected=f["faces_detected"],
                    face_expressions=f.get("face_expressions", []),
                    motion_level=f["motion_level"],
                    composition_score=f["composition_score"],
                    lighting=f["lighting"],
                    background_type=f.get("background_type", ""),
                    is_action_peak=f["is_action_peak"],
                    aesthetic_score=f["aesthetic_score"],
                    emotional_tone=f.get("emotional_tone", ""),
                    description=f.get("description", "")
                )
                for f in analysis_data["frames"]
            ]

            analysis = VideoAnalysis(
                source_path=analysis_data["source_path"],
                duration=analysis_data["duration"],
                fps=analysis_data["fps"],
                resolution=tuple(analysis_data["resolution"]),
                duration_type=DurationType(analysis_data["duration_type"]),
                frames=frames,
                highlights=analysis_data.get("highlights", []),
                overall_motion=analysis_data.get("overall_motion", ""),
                dominant_lighting=analysis_data.get("dominant_lighting", ""),
                summary=analysis_data.get("summary", "")
            )

            analyzed_at = data.get("meta", {}).get("analyzed_at", "unknown")
            self.console.print(f"[green]✓ 캐시된 분석 결과 로드 (분석 시간: {analyzed_at})[/green]")
            return analysis

        except Exception as e:
            self.console.print(f"[yellow]캐시 로드 실패: {e}[/yellow]")
            return None

    def has_analysis(self, video_path: str) -> bool:
        """분석 결과 캐시 존재 여부"""
        cache_path = self._get_analysis_path(video_path)
        return cache_path.exists()

    # ==================== 대본 캐시 ====================

    def save_script(
        self,
        video_path: str,
        style: str,
        target_duration: float,
        script: EditScript,
        prompt_used: str = ""
    ) -> str:
        """
        LLM 대본 저장

        Args:
            video_path: 원본 영상 경로
            style: 편집 스타일
            target_duration: 목표 길이
            script: 편집 대본
            prompt_used: 사용된 프롬프트 (디버깅용)

        Returns:
            저장된 파일 경로
        """
        save_path = self._get_script_path(video_path, style, target_duration)

        data = {
            "meta": {
                "video_path": str(video_path),
                "video_name": Path(video_path).name,
                "style": style,
                "target_duration": target_duration,
                "generated_at": datetime.now().isoformat(),
                "generator": "claude-cli"
            },
            "script": {
                "total_duration": script.total_duration,
                "style_applied": script.style_applied,
                "color_grade": script.color_grade,
                "audio_config": script.audio_config,
                "segments": [
                    {
                        "start_time": seg.start_time,
                        "end_time": seg.end_time,
                        "source_start": seg.source_start,
                        "source_end": seg.source_end,
                        "speed": seg.speed,
                        "effects": seg.effects,
                        "transition_in": seg.transition_in,
                        "transition_out": seg.transition_out,
                        "purpose": seg.purpose
                    }
                    for seg in script.segments
                ]
            },
            "prompt_used": prompt_used  # 디버깅용 프롬프트 저장
        }

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.console.print(f"[dim]대본 저장됨: {save_path}[/dim]")
        return str(save_path)

    def load_script(
        self,
        video_path: str,
        style: str,
        target_duration: float
    ) -> Optional[EditScript]:
        """
        캐시된 대본 로드

        Args:
            video_path: 원본 영상 경로
            style: 편집 스타일
            target_duration: 목표 길이

        Returns:
            EditScript 또는 None
        """
        cache_path = self._get_script_path(video_path, style, target_duration)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            script_data = data["script"]

            segments = [
                EditSegment(
                    start_time=seg["start_time"],
                    end_time=seg["end_time"],
                    source_start=seg["source_start"],
                    source_end=seg["source_end"],
                    speed=seg["speed"],
                    effects=seg.get("effects", []),
                    transition_in=seg.get("transition_in"),
                    transition_out=seg.get("transition_out"),
                    purpose=seg.get("purpose", "unknown")
                )
                for seg in script_data["segments"]
            ]

            script = EditScript(
                segments=segments,
                total_duration=script_data["total_duration"],
                style_applied=script_data["style_applied"],
                color_grade=script_data.get("color_grade", "default"),
                audio_config=script_data.get("audio_config", {})
            )

            generated_at = data.get("meta", {}).get("generated_at", "unknown")
            self.console.print(f"[green]✓ 캐시된 대본 로드 (생성 시간: {generated_at})[/green]")
            return script

        except Exception as e:
            self.console.print(f"[yellow]대본 캐시 로드 실패: {e}[/yellow]")
            return None

    def has_script(self, video_path: str, style: str, target_duration: float) -> bool:
        """대본 캐시 존재 여부"""
        cache_path = self._get_script_path(video_path, style, target_duration)
        return cache_path.exists()

    # ==================== 유틸리티 ====================

    def list_cached_analyses(self) -> List[Dict[str, Any]]:
        """캐시된 분석 결과 목록"""
        results = []
        for path in self.analysis_dir.glob("*_analysis.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                results.append({
                    "file": path.name,
                    "video": data.get("meta", {}).get("video_name", "unknown"),
                    "analyzed_at": data.get("meta", {}).get("analyzed_at", "unknown"),
                    "duration": data.get("analysis", {}).get("duration", 0),
                    "frames": len(data.get("analysis", {}).get("frames", []))
                })
            except Exception:
                pass
        return results

    def list_cached_scripts(self) -> List[Dict[str, Any]]:
        """캐시된 대본 목록"""
        results = []
        for path in self.scripts_dir.glob("*_script.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                results.append({
                    "file": path.name,
                    "video": data.get("meta", {}).get("video_name", "unknown"),
                    "style": data.get("meta", {}).get("style", "unknown"),
                    "target_duration": data.get("meta", {}).get("target_duration", 0),
                    "generated_at": data.get("meta", {}).get("generated_at", "unknown"),
                    "segments": len(data.get("script", {}).get("segments", []))
                })
            except Exception:
                pass
        return results

    def clear_cache(self, video_path: Optional[str] = None):
        """
        캐시 삭제

        Args:
            video_path: 특정 영상만 삭제 (None이면 전체 삭제)
        """
        if video_path:
            video_name = Path(video_path).stem
            video_hash = self._get_video_hash(video_path)
            pattern = f"{video_name}_{video_hash}_*"

            for path in self.analysis_dir.glob(pattern):
                path.unlink()
            for path in self.scripts_dir.glob(pattern):
                path.unlink()

            self.console.print(f"[yellow]캐시 삭제됨: {video_name}[/yellow]")
        else:
            for path in self.analysis_dir.glob("*.json"):
                path.unlink()
            for path in self.scripts_dir.glob("*.json"):
                path.unlink()

            self.console.print("[yellow]전체 캐시 삭제됨[/yellow]")

    def get_analysis_path(self, video_path: str) -> str:
        """분석 결과 파일 경로 반환 (사용자 확인용)"""
        return str(self._get_analysis_path(video_path))

    def get_script_path(self, video_path: str, style: str, target_duration: float) -> str:
        """대본 파일 경로 반환 (사용자 확인용)"""
        return str(self._get_script_path(video_path, style, target_duration))
