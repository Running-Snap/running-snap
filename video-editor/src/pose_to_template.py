"""
PoseToTemplate
==============
파싱된 자세 분석 JSON → EditInstruction JSON + TTS 스크립트 생성.
front_side_view 기반 자세 분석 결과를 받아 코칭 영상으로 자동 편집.

영상 구조 (섹션당 최대 3 클립):
    [buildup]  키 프레임 직전 BUILDUP_DUR초 — 일반 속도, 섹션 라벨 표시
               → 시청자가 어떤 구간을 분석할지 예고

    [peak]     키 프레임 중심 슬로모션(SLOWMO_SPEED=0.35x) — 문제 자막 표시
               → 소스 범위: issue 텍스트 읽기 시간 기반 동적 결정
               → 출력 시간 ≥ max(len(issue) / READING_CPS, MIN_DISPLAY)
               → 소스 길이 = 출력 시간 × SLOWMO_SPEED (키 프레임 중심으로 대칭 확장)

    [replay]   동일 구간 재생(REPLAY_SPEED=0.55x) — 개선 방법 자막 표시
               → correction 텍스트 REPLAY_THRESH(15)자 이상일 때 자동 활성화
               → 출력 시간 ≥ max(len(correction) / READING_CPS, MIN_DISPLAY)
               → replay 소스 범위도 독립적으로 동적 계산

타이밍 계산 원칙:
    각 finding의 timestamp_sec(키 프레임 시간 t)을 중심으로:
      p_half = max(PEAK_HALF, issue_read_sec × SLOWMO_SPEED / 2)
      p_src_s = t - p_half,  p_src_e = t + p_half  (소스 범위)
      p_out   = (p_src_e - p_src_s) / SLOWMO_SPEED  (출력 길이)
    → 자막 글자 수가 많을수록 슬로모 구간이 자동으로 길어짐

TemplateExecutor 호환:
    - source_start_sec / source_end_sec 필드로 소스 직접 지정 (중요도순 편집)
    - 기존 ratio 필드는 오버레이 타이밍 계산에 사용
"""

from typing import Dict, List, Tuple, Any


class PoseToTemplate:
    SLOWMO_SPEED  = 0.35   # peak 슬로모션 배율
    REPLAY_SPEED  = 0.55   # replay 배율 (살짝 느림)
    BUILDUP_DUR   = 0.5    # buildup 소스 길이 (초)
    PEAK_HALF     = 0.3    # peak 최소 반경 (초) — 읽기 시간 기준으로 동적 확장됨
    MAX_SECTIONS  = 3      # 상위 N 섹션만 사용
    REPLAY_THRESH = 15     # correction 자막 길이 이 이상이면 replay 활성화
    READING_CPS   = 8.0    # 한국어 자막 읽기 속도 (자/초) — 표시 시간 계산 기준
    MIN_DISPLAY   = 2.0    # 자막 최소 표시 시간 (초)
    CROP_ZOOM     = 1.3    # 인물 확대 배율 — 중앙 1/1.3 크롭 후 원본 해상도로 업스케일
    OUTRO_DUR     = 1.5    # 아우트로 길이 (초) — 항상 소스 영상의 마지막 구간 사용

    # 오버레이 색상
    LABEL_COLOR      = "#80C8FF"   # 섹션 라벨 (파란 계열)
    ISSUE_COLOR      = "#FFFFFF"   # 문제 자막
    CORRECTION_COLOR = "#AAFFAA"   # 개선 방법 자막 (연두 계열)
    REPLAY_TAG_COLOR = "#FFD700"   # REPLAY 태그

    def convert(
        self,
        analysis: Dict[str, Any],
        source_duration: float = 999.0,
    ) -> Tuple[Dict, List[Dict]]:
        """
        Args:
            analysis:        PoseAnalysisParser.parse() 반환값
            source_duration: 원본 영상 길이 (초) — source_end_sec 클램핑용

        Returns:
            (EditInstruction dict, tts_script list)

        tts_script item:
            {"start_sec": float, "text": str, "lang": "ko"}
        """
        sections = analysis["sections"][: self.MAX_SECTIONS]

        segments: List[Dict]  = []
        overlays: List[Dict]  = []
        tts_script: List[Dict] = []

        # ── 1. 각 섹션에 필요한 시간 계산 ──────────────────────────
        plan = []            # 섹션별 (section, finding, 각 클립 정보) 목록
        chosen_times = []    # 이미 선택된 타임스탬프 — 분산 최대화용

        for sec in sections:
            if not sec["findings"]:
                continue

            # ── 스마트 finding 선택: 이미 선택된 타임스탬프와 가장 멀리 떨어진 것 ──
            # findings[0]을 항상 쓰면 rank2/3가 영상 앞부분만 반복하는 문제 발생.
            # 대신 이미 선택된 타임스탬프들과의 최소 거리가 최대인 finding을 선택해
            # 편집 구간이 소스 영상 전체에 고르게 분포되도록 함.
            if not chosen_times:
                # 첫 섹션(rank1)은 findings[0]이 가장 중요한 순간이므로 그대로 사용
                finding = sec["findings"][0]
            else:
                finding = max(
                    sec["findings"],
                    key=lambda f: min(
                        abs(f["timestamp_sec"] - ct) for ct in chosen_times
                    ),
                )
            chosen_times.append(finding["timestamp_sec"])
            t = finding["timestamp_sec"]

            # ── buildup: 키 프레임 직전 BUILDUP_DUR초 (일반속도, 섹션 예고) ──────
            b_src_s = max(0.0, t - self.BUILDUP_DUR)
            b_src_e = min(t, source_duration)
            b_out   = b_src_e - b_src_s

            # ── peak: issue 자막 읽기 시간 기반으로 슬로모 구간 동적 결정 ─────────
            # issue 텍스트를 읽는 데 필요한 시간 (최소 MIN_DISPLAY초 보장)
            issue_read_sec = max(len(finding["issue"]) / self.READING_CPS,
                                 self.MIN_DISPLAY)
            # 슬로모(SLOWMO_SPEED)로 issue_read_sec만큼 재생하려면 필요한 소스 길이
            p_src_needed   = issue_read_sec * self.SLOWMO_SPEED
            p_half         = max(self.PEAK_HALF, p_src_needed / 2)
            p_src_s        = max(0.0, t - p_half)
            p_src_e        = min(t + p_half, source_duration)
            p_src_d        = p_src_e - p_src_s
            p_out          = p_src_d / self.SLOWMO_SPEED   # ≥ issue_read_sec

            # ── replay: correction 자막 읽기 시간 기반, 조건부 활성화 ─────────────
            do_replay = len(finding["correction"]) >= self.REPLAY_THRESH
            if do_replay:
                corr_read_sec = max(len(finding["correction"]) / self.READING_CPS,
                                    self.MIN_DISPLAY)
                r_src_needed  = corr_read_sec * self.REPLAY_SPEED
                r_half        = max(self.PEAK_HALF, r_src_needed / 2)
                r_src_s       = max(0.0, t - r_half)
                r_src_e       = min(t + r_half, source_duration)
                r_src_d       = r_src_e - r_src_s
                r_out         = r_src_d / self.REPLAY_SPEED   # ≥ corr_read_sec
            else:
                r_src_s, r_src_e = p_src_s, p_src_e
                r_out             = 0.0

            plan.append({
                "section":   sec,
                "finding":   finding,
                "b": {"src_s": b_src_s, "src_e": b_src_e, "out": b_out},
                "p": {"src_s": p_src_s, "src_e": p_src_e, "out": p_out, "src_d": p_src_d},
                "r": {"src_s": r_src_s, "src_e": r_src_e, "out": r_out, "do": do_replay},
            })

        if not plan:
            raise ValueError("유효한 finding을 가진 섹션이 없습니다.")

        # ── outro: 항상 소스 영상의 마지막 OUTRO_DUR초 ────────────────────────────
        # "마지막 finding 이후" 방식은 outro가 영상 중간에 걸릴 수 있음.
        # 대신 source_duration 기준으로 고정해 영상이 끝까지 자연스럽게 마무리됨.
        outro_src_e = source_duration
        outro_src_s = max(0.0, source_duration - self.OUTRO_DUR)
        outro_out   = outro_src_e - outro_src_s

        total_out = (
            sum(p["b"]["out"] + p["p"]["out"] + p["r"]["out"] for p in plan)
            + outro_out
        )
        total_out = max(total_out, 1.0)  # 안전값

        # ── 2. 세그먼트 & 오버레이 빌드 ─────────────────────────────
        cum = 0.0   # 누적 출력 시간

        for pi, p in enumerate(plan):
            rank    = p["section"]["rank"]
            title   = p["section"]["title"]
            finding = p["finding"]

            # ── BUILDUP ──────────────────────────────────────────────
            b      = p["b"]
            b_sr   = round(cum / total_out, 5)
            b_er   = round((cum + b["out"]) / total_out, 5)

            segments.append({
                "id":               f"buildup_{rank}",
                "type":             "buildup",
                "start_ratio":      b_sr,
                "end_ratio":        b_er,
                "source_start_sec": round(b["src_s"], 3),
                "source_end_sec":   round(b["src_e"], 3),
                "speed":            1.0,
            })

            # 섹션 라벨 (buildup 전체)
            overlays.append(_ov(
                f"label_{rank}",
                f"#{rank}  {title}",
                50, 10,
                b_sr, b_er,
                weight=700, size=0.036,
                color=self.LABEL_COLOR, opacity=0.9,
            ))
            cum += b["out"]

            # ── PEAK (슬로모션) ───────────────────────────────────────
            pk     = p["p"]
            pk_sr  = round(cum / total_out, 5)
            pk_er  = round((cum + pk["out"]) / total_out, 5)

            segments.append({
                "id":               f"peak_{rank}",
                "type":             "peak",
                "start_ratio":      pk_sr,
                "end_ratio":        pk_er,
                "source_start_sec": round(pk["src_s"], 3),
                "source_end_sec":   round(pk["src_e"], 3),
                "speed":            self.SLOWMO_SPEED,
            })

            # 섹션 라벨 (peak 유지)
            overlays.append(_ov(
                f"label_{rank}_pk",
                f"#{rank}  {title}",
                50, 10,
                pk_sr, pk_er,
                weight=700, size=0.036,
                color=self.LABEL_COLOR, opacity=0.9,
            ))
            # 문제 자막
            overlays.append(_ov(
                f"issue_{rank}",
                finding["issue"],
                50, 84,
                pk_sr, pk_er,
                weight=400, size=0.043,
                color=self.ISSUE_COLOR, opacity=0.95,
            ))

            # TTS — 문제 설명
            tts_script.append({
                "start_sec": round(cum, 3),
                "text":      finding["issue"],
                "lang":      "ko",
            })
            cum += pk["out"]

            # ── REPLAY ───────────────────────────────────────────────
            r = p["r"]
            if r["do"]:
                r_sr = round(cum / total_out, 5)
                r_er = round((cum + r["out"]) / total_out, 5)

                segments.append({
                    "id":               f"replay_{rank}",
                    "type":             "buildup",
                    "start_ratio":      r_sr,
                    "end_ratio":        r_er,
                    "source_start_sec": round(r["src_s"], 3),
                    "source_end_sec":   round(r["src_e"], 3),
                    "speed":            self.REPLAY_SPEED,
                })

                # REPLAY 태그
                overlays.append(_ov(
                    f"replay_tag_{rank}",
                    "◀ REPLAY",
                    50, 10,
                    r_sr, r_er,
                    weight=700, size=0.032,
                    color=self.REPLAY_TAG_COLOR, opacity=0.85,
                ))
                # 개선 방법 자막
                overlays.append(_ov(
                    f"correction_{rank}",
                    f"▶ {finding['correction']}",
                    50, 84,
                    r_sr, r_er,
                    weight=400, size=0.042,
                    color=self.CORRECTION_COLOR, opacity=0.95,
                ))

                # TTS — 개선 방법
                tts_script.append({
                    "start_sec": round(cum, 3),
                    "text":      finding["correction"],
                    "lang":      "ko",
                })
                cum += r["out"]

        # ── OUTRO ────────────────────────────────────────────────────
        o_sr = round(cum / total_out, 5)
        segments.append({
            "id":               "outro",
            "type":             "outro",
            "start_ratio":      o_sr,
            "end_ratio":        1.0,
            "source_start_sec": round(outro_src_s, 3),
            "source_end_sec":   round(outro_src_e, 3),
            "speed":            1.0,
        })

        # ── 완성 EditInstruction ────────────────────────────────────
        instruction = {
            "version":     "1.0",
            "template_id": f"pose_analysis_top{len(plan)}",
            "type":        "pose_analysis",
            "meta": {
                "aspect_ratio":             "9:16",
                "target_duration_seconds":  round(total_out, 2),
                "color_grade":              "dark",
                "vibe_tags":                ["pose_analysis", "coaching", "slowmo"],
                "crop_zoom":                self.CROP_ZOOM,   # 인물 중앙 확대 (1.3x)
            },
            "timeline": {
                "total_duration_seconds": round(total_out, 2),
                "segments":               segments,
            },
            "speed_changes": [],   # 세그먼트별 speed 직접 지정으로 대체
            "effects": [
                # 슬로모 구간마다 줌인
                {
                    "type":        "zoom_in",
                    "start_ratio": seg["start_ratio"],
                    "end_ratio":   seg["end_ratio"],
                    "intensity":   0.07,
                }
                for seg in segments if seg["type"] == "peak"
            ],
            "overlays": overlays,
            "color_grade": {
                "overall_tone":      "dark",
                "has_filter":        True,
                "filter_style":      "film",
                "adjustment_params": {
                    "brightness": -8,
                    "contrast":   18,
                    "saturation": -15,
                },
            },
        }

        return instruction, tts_script


# ── 헬퍼 ─────────────────────────────────────────────────────────

def _ov(
    ov_id: str, content: str,
    x: int, y: int,
    start_ratio: float, end_ratio: float,
    weight: int = 400, size: float = 0.043,
    color: str = "#FFFFFF", opacity: float = 0.95,
) -> Dict:
    return {
        "id":           ov_id,
        "type":         "text",
        "content":      content,
        "position_pct": {"x": x, "y": y},
        "start_ratio":  start_ratio,
        "end_ratio":    end_ratio,
        "style": {
            "font_weight":      weight,
            "font_size_ratio":  size,
            "color":            color,
            "opacity":          opacity,
        },
    }
