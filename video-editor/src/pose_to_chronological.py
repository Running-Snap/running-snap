"""
pose_to_chronological.py  (v2 — lead-in slowmo + freeze)
=========================================================
파싱된 자세 분석 JSON → 프레임 순서대로 모든 finding을 영상에 담는 EditInstruction 생성기.

영상 흐름:
    [normal]  일반속도로 달리다가
    [slowmo]  finding 직전 0.5초 — 0.3× 슬로우 (브레이킹 효과, 느낌 살리기)
    [freeze]  finding 프레임에서 완전 정지 — 자막 읽을 동안 홀드
    [normal]  다음 finding까지 다시 정상속도
    ...
    [outro]   마지막 finding 이후 → 소스 영상 끝까지 정상속도

finding이 MERGE_GAP(0.15초) 이내로 붙어있으면 한 freeze 그룹으로 묶는다.
freeze 지속 시간은 자막 텍스트 글자 수 기반으로 동적 계산된다.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple


class PoseToChronological:
    # ── lead-in 슬로우 ──────────────────────────────────────────────
    SLOWMO_SPEED = 0.30   # 슬로우 배율 (찰나의 브레이킹 느낌)
    LEAD_IN      = 0.50   # finding 직전 슬로우 소스 구간 (초)

    # ── freeze 파라미터 ─────────────────────────────────────────────
    MIN_HALF     = 2.0    # issue / correction 각각의 최소 표시 시간 (초)
    READING_CPS  = 12.0   # 한국어 자막 읽기 속도 (자/초) — freeze 길이 기반
    # freeze 총 시간 = issue_dur + correction_dur (각 half 독립 계산)

    # ── 그룹핑 ─────────────────────────────────────────────────────
    MERGE_GAP    = 0.15   # 이 이내 findings → 동일 freeze 그룹

    # ── 비주얼 ─────────────────────────────────────────────────────
    CORRECTION_PREFIX = "▶ "   # 💡 대신 BMP 기호 (렌더링 안전)
    CROP_ZOOM         = 1.3
    LABEL_COLOR       = "#80C8FF"
    ISSUE_COLOR       = "#FFFFFF"
    CORRECTION_COLOR  = "#AAFFAA"

    # ────────────────────────────────────────────────────────────────

    def convert(
        self,
        analysis: Dict[str, Any],
        source_duration: float,
    ) -> Tuple[Dict, List[Dict]]:
        """
        Args:
            analysis:        PoseAnalysisParser.parse() 반환값
            source_duration: 원본 영상 길이 (초)
        Returns:
            (EditInstruction dict, tts_script list)
        """
        # ── 1. 전체 findings 수집 → timestamp 오름차순 ─────────────
        all_findings: List[Dict] = []
        for sec in analysis["sections"]:
            for f in sec["findings"]:
                all_findings.append({
                    "timestamp_sec": f["timestamp_sec"],
                    "frame":         f["frame"],
                    "issue":         f["issue"],
                    "correction":    f["correction"],
                    "rank":          sec["rank"],
                    "title":         sec["title"],
                })
        all_findings.sort(key=lambda x: x["timestamp_sec"])

        # ── 2. 가까운 findings 그룹핑 ─────────────────────────────
        groups: List[Dict] = []
        for fd in all_findings:
            if groups and (fd["timestamp_sec"] - groups[-1]["t"]) <= self.MERGE_GAP:
                groups[-1]["findings"].append(fd)
            else:
                groups.append({"t": fd["timestamp_sec"], "findings": [fd]})

        # ── 3. finding별 자막 텍스트 + freeze 시간 미리 계산 ───────
        for grp in groups:
            findings = grp["findings"]
            primary  = min(findings, key=lambda f: f["rank"])

            seen: List[str] = []
            for fd in findings:
                if fd["issue"] not in seen:
                    seen.append(fd["issue"])
            issue_text = "\n".join(seen[:2])
            correction_text = self.CORRECTION_PREFIX + primary["correction"]

            titles = list(dict.fromkeys(fd["title"] for fd in findings))

            # issue / correction 각각의 읽기 시간 → 합산이 freeze 총 길이
            issue_dur      = max(len(issue_text)      / self.READING_CPS, self.MIN_HALF)
            correction_dur = max(len(correction_text) / self.READING_CPS, self.MIN_HALF)
            freeze_dur     = issue_dur + correction_dur

            grp["issue_text"]      = issue_text
            grp["correction_text"] = correction_text
            grp["titles"]          = titles
            grp["freeze_dur"]      = round(freeze_dur, 3)
            grp["issue_dur"]       = round(issue_dur, 3)
            grp["correction_dur"]  = round(correction_dur, 3)

        # ── 4. 세그먼트 목록 구성 ─────────────────────────────────
        #   3단계: normal → slowmo(lead-in) → freeze
        seg_list: List[Dict] = []
        prev_end = 0.0   # 이전 finding 이후 소스 위치

        for grp in groups:
            t       = grp["t"]
            src_t   = min(t, source_duration - 0.001)   # freeze 추출 지점

            # slowmo 구간: t - LEAD_IN → t (LEAD_IN 초 분량)
            slow_src_s = max(prev_end, t - self.LEAD_IN)
            slow_src_e = min(t, source_duration)

            # normal 구간: prev_end → slow_src_s
            if slow_src_s > prev_end:
                seg_list.append({
                    "type":  "normal",
                    "src_s": prev_end,
                    "src_e": slow_src_s,
                    "speed": 1.0,
                })

            # slowmo lead-in
            if slow_src_e > slow_src_s:
                seg_list.append({
                    "type":  "slowmo",
                    "src_s": slow_src_s,
                    "src_e": slow_src_e,
                    "speed": self.SLOWMO_SPEED,
                })

            # freeze: 소스는 소비하지 않고 한 프레임만 고정
            seg_list.append({
                "type":      "freeze",
                "src_t":     src_t,           # 정지할 소스 타임스탬프
                "freeze_dur": grp["freeze_dur"],
                "group":     grp,
            })

            prev_end = min(t, source_duration)

        # outro: 마지막 finding 이후 → 소스 끝
        if prev_end < source_duration:
            seg_list.append({
                "type":  "outro",
                "src_s": prev_end,
                "src_e": source_duration,
                "speed": 1.0,
            })

        # ── 5. 총 출력 시간 계산 ─────────────────────────────────
        def _out_dur(s: Dict) -> float:
            if s["type"] == "freeze":
                return s["freeze_dur"]
            return (s["src_e"] - s["src_s"]) / s["speed"]

        total_out = max(sum(_out_dur(s) for s in seg_list), 1.0)

        # ── 6. segments / overlays / tts_script 빌드 ─────────────
        segments:   List[Dict] = []
        overlays:   List[Dict] = []
        tts_script: List[Dict] = []
        cum = 0.0

        for i, s in enumerate(seg_list):
            out_dur = _out_dur(s)
            sr = round(cum / total_out, 5)
            er = round((cum + out_dur) / total_out, 5)

            if s["type"] == "freeze":
                # freeze 세그먼트 — TemplateExecutor가 ImageClip으로 처리
                segments.append({
                    "id":               f"seg_{i:02d}_freeze",
                    "type":             "freeze",
                    "start_ratio":      sr,
                    "end_ratio":        er,
                    "source_start_sec": round(s["src_t"], 3),
                    "source_end_sec":   round(s["src_t"], 3),   # 동일 = 단일 프레임
                    "speed":            1.0,
                    "freeze_duration":  round(out_dur, 3),
                })

                grp   = s["group"]
                # mid_r: issue가 끝나는 지점 (절반이 아닌 실제 issue 비율)
                mid_r = round(sr + (er - sr) * grp["issue_dur"] / grp["freeze_dur"], 5)

                # 섹션 태그 (상단, freeze 전체)
                overlays.append({
                    "id":           f"tag_{i:02d}",
                    "type":         "text",
                    "content":      "  /  ".join(grp["titles"]),
                    "position_pct": {"x": 50, "y": 8},
                    "start_ratio":  sr,
                    "end_ratio":    er,
                    "style": {
                        "font_weight":     700,
                        "font_size_ratio": 0.032,
                        "color":           self.LABEL_COLOR,
                        "opacity":         0.9,
                    },
                })

                # issue 자막 (하단, 전반)
                overlays.append({
                    "id":           f"issue_{i:02d}",
                    "type":         "text",
                    "content":      grp["issue_text"],
                    "position_pct": {"x": 50, "y": 82},
                    "start_ratio":  sr,
                    "end_ratio":    mid_r,
                    "style": {
                        "font_weight":     600,
                        "font_size_ratio": 0.040,
                        "color":           self.ISSUE_COLOR,
                        "opacity":         0.95,
                    },
                })

                # correction 자막 (하단, 후반)
                overlays.append({
                    "id":           f"corr_{i:02d}",
                    "type":         "text",
                    "content":      grp["correction_text"],
                    "position_pct": {"x": 50, "y": 82},
                    "start_ratio":  mid_r,
                    "end_ratio":    er,
                    "style": {
                        "font_weight":     400,
                        "font_size_ratio": 0.038,
                        "color":           self.CORRECTION_COLOR,
                        "opacity":         0.95,
                    },
                })

                tts_script.append({
                    "start_sec": round(sr * total_out, 2),
                    "text":      grp["findings"][0]["issue"],
                    "lang":      "ko",
                })

            else:
                # normal / slowmo / outro
                exec_type = "peak" if s["type"] == "slowmo" else s["type"]
                segments.append({
                    "id":               f"seg_{i:02d}_{s['type']}",
                    "type":             exec_type,
                    "start_ratio":      sr,
                    "end_ratio":        er,
                    "source_start_sec": round(s["src_s"], 3),
                    "source_end_sec":   round(s["src_e"], 3),
                    "speed":            s["speed"],
                })

            cum += out_dur

        instruction = {
            "version":     "1.0",
            "template_id": "pose_chronological_all",
            "type":        "pose_analysis",
            "meta": {
                "aspect_ratio":            "9:16",
                "target_duration_seconds": round(total_out, 2),
                "color_grade":             "dark",
                "vibe_tags":               ["pose_analysis", "coaching", "freeze", "chronological"],
                "crop_zoom":               self.CROP_ZOOM,
            },
            "timeline": {
                "total_duration_seconds": round(total_out, 2),
                "segments":               segments,
            },
            "speed_changes": [],
            "effects":       [],
            "overlays":      overlays,
            "color_grade": {
                "overall_tone":   "dark",
                "has_filter":     True,
                "filter_style":   "film",
                "adjustment_params": {
                    "brightness": -8,
                    "contrast":   18,
                    "saturation": -15,
                },
            },
        }

        return instruction, tts_script
