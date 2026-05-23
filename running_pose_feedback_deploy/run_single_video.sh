#!/usr/bin/env bash
# 단일 영상: MediaPipe 전처리 → Qwen+LoRA 코칭
#
#   ./run_single_video.sh path/to/video.mp4 [GPU_ID]
#
# 출력: work/output/<stem>/  (pose, profiles, feedback.md/json)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VIDEO="${1:?Usage: $0 video.mp4 [gpu_id]}"
GPU="${2:-0}"

if [[ ! -f "$VIDEO" ]]; then
  echo "Video not found: $VIDEO" >&2
  exit 1
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "먼저: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

PYTHON="$ROOT/.venv/bin/python"
WORK="$ROOT/work"
POSE="$WORK/pose"
PROF="$WORK/profiles"
OUT="$WORK/output"

mkdir -p "$POSE" "$PROF" "$OUT"

echo "=== [1/2] MediaPipe 포즈 + phase 프로파일 ==="
"$PYTHON" "$ROOT/analysis/run_pose_and_feedback.py" preprocess \
  --video "$VIDEO" \
  --pose-dir "$POSE" \
  --profiles-dir "$PROF"

echo "=== [2/2] Qwen2.5-VL + LoRA 코칭 ==="
"$PYTHON" "$ROOT/analysis/generate_commentary_with_qwen.py" \
  --gpu-id "$GPU" \
  --qlora \
  --lora-dir "$ROOT/finetune_data/checkpoints/qwen_commentary_lora" \
  --video "$VIDEO" \
  --pose-dir "$POSE" \
  --profiles-dir "$PROF" \
  --reference-dir "$ROOT/analysis/reference_marathon_postprocess" \
  --output-dir "$OUT"

echo ""
echo "완료. 결과: $OUT/per_video/"
