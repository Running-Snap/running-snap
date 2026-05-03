"""
PoseAnalysisParser
==================
자세 분석 모델이 생성한 텍스트를 구조화된 JSON으로 파싱.

입력 포맷:
    ### N. 섹션 제목
    요약 문단 ...
    - 프레임 N, 약 X.Xs | 자세 분석: ... | 개선 방법: ...
    (근거 프레임: N, M, ...)

출력 JSON 포맷:
    {
      "version": "1.0",
      "type": "pose_analysis",
      "source_fps": 30.0,
      "sections": [
        {
          "rank": 1,
          "title": "팔꿈치-케이던스 협응",
          "summary": "...",
          "evidence_frames": [61, 51, 52],
          "findings": [
            {
              "frame": 61,
              "timestamp_sec": 2.03,
              "issue": "팔꿈치가 많이 펴져...",
              "correction": "팔꿈치를 80~100도..."
            }
          ]
        }
      ]
    }

규칙:
- sections는 rank 오름차순 (= 중요도 순)으로 정렬되어 반환
- 값 손실 없이 원문 그대로 보존
"""

import re
import json
from typing import List, Dict, Any


class PoseAnalysisParser:
    """자세 분석 텍스트 → 구조화 JSON 파서"""

    # finding 한 줄 패턴:
    # - 프레임 N, 약 X.Xs | 자세 분석: ... | 개선 방법: ...
    _FINDING_RE = re.compile(
        r"-\s*프레임\s*(\d+)[,，]\s*약\s*([\d.]+)\s*초"
        r"\s*[|｜]\s*자세\s*분석\s*:\s*(.+?)"
        r"\s*[|｜]\s*개선\s*방법\s*:\s*(.+?)(?=\n\s*-\s*프레임|\n\s*\(근거|\Z)",
        re.DOTALL,
    )

    # 근거 프레임 줄: (근거 프레임: N, M, ...)
    _EVIDENCE_RE = re.compile(r"\(근거\s*프레임\s*:\s*([\d,\s]+)\)")

    # 섹션 헤더: ### N. 제목
    _SECTION_HEADER_RE = re.compile(r"^###\s+(\d+)\.\s+(.+)", re.MULTILINE)

    def parse(self, text: str, source_fps: float = 30.0) -> Dict[str, Any]:
        """
        분석 텍스트를 파싱하여 JSON 호환 dict 반환.

        Args:
            text: 자세 분석 원문
            source_fps: 분석에 사용된 영상 fps (기본 30.0)

        Returns:
            pose_analysis JSON dict
        """
        sections = []

        # ### N. 헤더를 기준으로 블록 분리
        # 각 블록의 시작 위치와 내용을 찾기
        header_matches = list(self._SECTION_HEADER_RE.finditer(text))
        if not header_matches:
            raise ValueError("자세 분석 텍스트에서 섹션(### N.)을 찾을 수 없습니다.")

        for idx, hm in enumerate(header_matches):
            rank  = int(hm.group(1))
            title = hm.group(2).strip()

            # 이 섹션의 본문: 헤더 끝 ~ 다음 헤더 시작 (또는 텍스트 끝)
            block_start = hm.end()
            block_end   = header_matches[idx + 1].start() if idx + 1 < len(header_matches) else len(text)
            block       = text[block_start:block_end]

            # ── 개별 finding 파싱 ────────────────────────────────────
            findings = []
            for fm in self._FINDING_RE.finditer(block):
                frame         = int(fm.group(1))
                timestamp_sec = float(fm.group(2))
                issue         = fm.group(3).strip().rstrip(".")
                correction    = fm.group(4).strip().rstrip(".")

                # 개행 제거 (멀티라인 매칭 아티팩트)
                issue      = " ".join(issue.split())
                correction = " ".join(correction.split())

                findings.append({
                    "frame":         frame,
                    "timestamp_sec": timestamp_sec,
                    "issue":         issue,
                    "correction":    correction,
                })

            # ── 근거 프레임 목록 ─────────────────────────────────────
            evidence_frames: List[int] = []
            em = self._EVIDENCE_RE.search(block)
            if em:
                evidence_frames = [
                    int(x.strip()) for x in em.group(1).split(",") if x.strip().isdigit()
                ]

            # ── 요약 문단 ────────────────────────────────────────────
            # finding 줄 이전까지의 텍스트 = 요약
            summary_end = block.find("\n-")
            summary_raw = block[:summary_end] if summary_end != -1 else block
            # evidence 줄 제거
            summary_raw = self._EVIDENCE_RE.sub("", summary_raw)
            summary = " ".join(summary_raw.split())

            sections.append({
                "rank":            rank,
                "title":           title,
                "summary":         summary,
                "evidence_frames": evidence_frames,
                "findings":        findings,
            })

        # rank 오름차순 정렬 (중요도 순)
        sections.sort(key=lambda s: s["rank"])

        return {
            "version":    "1.0",
            "type":       "pose_analysis",
            "source_fps": source_fps,
            "sections":   sections,
        }

    def parse_file(self, path: str, source_fps: float = 30.0) -> Dict[str, Any]:
        """파일에서 읽어 파싱"""
        with open(path, encoding="utf-8") as f:
            return self.parse(f.read(), source_fps)

    def to_json(self, result: Dict[str, Any], indent: int = 2) -> str:
        return json.dumps(result, ensure_ascii=False, indent=indent)


# ── CLI 직접 실행 ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python pose_analysis_parser.py <analysis.txt>")
        sys.exit(1)

    parser = PoseAnalysisParser()
    result = parser.parse_file(sys.argv[1])
    print(parser.to_json(result))
    print(f"\n--- 파싱 요약 ---", file=sys.stderr)
    for s in result["sections"]:
        print(f"  Rank {s['rank']}: {s['title']}  ({len(s['findings'])}건)", file=sys.stderr)
