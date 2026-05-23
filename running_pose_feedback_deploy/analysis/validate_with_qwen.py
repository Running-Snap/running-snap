from __future__ import annotations

"""
validation_Data 이진 분류 — Qwen2.5-VL

기본: 로컬 모델 (Hub에서 한 번 받아 두고 GPU/CPU에서 직접 추론)
  pip install torch transformers accelerate qwen-vl-utils opencv-python huggingface_hub

  .venv/bin/python analysis/validate_with_qwen.py --model Qwen/Qwen2.5-VL-7B-Instruct
  .venv/bin/python analysis/validate_with_qwen.py --max-videos 3

디스크 부족 시 캐시를 다른 드라이브로:
  export HF_HOME=/path/with/space/huggingface
  # 7B(~15GB) 대신 3B(~6GB): --model Qwen/Qwen2.5-VL-3B-Instruct

Hub API (토큰·권한 필요):
  .venv/bin/python analysis/validate_with_qwen.py --mode hub --model Qwen/Qwen2.5-VL-7B-Instruct
"""

import argparse
import base64
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from plot_validation_results import (  # noqa: E402
    BAD_LABEL,
    GOOD_LABEL,
    classification_metrics,
    configure_plot_fonts,
    plot_confusion_matrix,
    write_metrics_csv,
)

DEFAULT_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

PROMPT = """이 영상은 러닝(달리기) 자세 영상입니다.
여러 프레임을 보고 전신 러닝 폼을 이진 분류하세요.

- good: 마라톤/조깅에 적합한 전반적으로 올바른 러닝 자세
- bad: 명확한 자세 문제(팔꿈치, 케이던스, 착지, 상체, 보폭 등)가 보임

반드시 아래 JSON만 출력하세요:
{"label": "good" 또는 "bad", "reason": "한 문장 한국어"}"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qwen2.5-VL binary validation (local or Hub API)")
    parser.add_argument("--input", type=Path, default=Path("validation_Data"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/results_validation_qwen"),
    )
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="로컬 모델 경로 (없으면 Hub id로 자동 다운로드)",
    )
    parser.add_argument(
        "--mode",
        choices=("local", "hub"),
        default="local",
        help="local=설치 후 직접 추론 (기본), hub=HF Inference API",
    )
    parser.add_argument("--max-videos", type=int, default=0, help="0 = all")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument(
        "--gpu-id",
        type=int,
        default=1,
        help="Physical GPU index (default: 1). Sets CUDA_VISIBLE_DEVICES before load.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="hf-inference",
        choices=("hf-inference", "router", "auto"),
        help="--mode hub 일 때만 사용",
    )
    return parser.parse_args()


def collect_videos(root: Path) -> list[Path]:
    suffixes = {".mp4", ".mov", ".MP4", ".MOV"}
    return sorted(p for p in root.rglob("*") if p.suffix in suffixes)


def parse_label_category(video_path: Path, validation_root: Path) -> tuple[str, str]:
    rel = video_path.relative_to(validation_root)
    parts = rel.parts
    return parts[0] if parts else "unknown", parts[1] if len(parts) > 2 else ""


def parse_qwen_json(text: str) -> tuple[str, str]:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            label = str(data.get("label", "")).lower()
            reason = str(data.get("reason", ""))
            if label in ("good", "bad"):
                return label, reason
        except json.JSONDecodeError:
            pass
    if "bad" in text.lower() or "나쁨" in text or "문제" in text:
        return "bad", text[:200]
    return "good", text[:200]


from video_frame_utils import sample_frame_paths, sample_frames_with_meta  # noqa: E402


def frame_to_data_url(frame_path: Path) -> str:
    data = frame_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


# --- Local inference ---------------------------------------------------------


def _resolve_lora_dir(lora_dir: Path | None) -> Path | None:
    if lora_dir is None:
        return None
    p = lora_dir.resolve()
    if (p / "adapter_config.json").is_file():
        return p
    for name in ("checkpoint-150", "checkpoint-125", "checkpoint-100"):
        cand = p / name
        if (cand / "adapter_config.json").is_file():
            return cand
    raise FileNotFoundError(f"No adapter_config.json under {lora_dir}")


def load_qwen25_vl_local(
    model_id: str,
    model_dir: Path | None,
    device: str,
    *,
    lora_dir: Path | None = None,
    qlora: bool = False,
):
    """베이스 Qwen2.5-VL (+ 선택 PEFT LoRA). 학습이 QLoRA였으면 qlora=True 권장."""
    import torch
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    adapter_path = _resolve_lora_dir(lora_dir)
    base_path = str(model_dir) if model_dir and model_dir.is_dir() else model_id
    if adapter_path is not None:
        cfg = json.loads((adapter_path / "adapter_config.json").read_text(encoding="utf-8"))
        base_path = cfg.get("base_model_name_or_path") or base_path

    use_cuda = device.startswith("cuda") and torch.cuda.is_available()
    load_kw: dict = {"trust_remote_code": True}
    if qlora and use_cuda:
        from transformers import BitsAndBytesConfig

        load_kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        dev_index = int(device.rsplit(":", 1)[-1]) if ":" in device else 0
        load_kw["device_map"] = {"": dev_index}
    else:
        dtype = torch.bfloat16 if use_cuda else torch.float32
        load_kw["torch_dtype"] = dtype
        load_kw["device_map"] = {"": device} if use_cuda else None

    print(f"Loading base on {device} from: {base_path}")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(base_path, **load_kw)
    if adapter_path is not None:
        from peft import PeftModel

        print(f"Loading LoRA adapter: {adapter_path}")
        model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
    if not use_cuda:
        model = model.to("cpu")

    proc_path = str(adapter_path) if adapter_path and (adapter_path / "processor_config.json").is_file() else base_path
    processor = AutoProcessor.from_pretrained(proc_path, trust_remote_code=True)
    model.eval()
    return model, processor


class LocalQwen25:
    def __init__(
        self,
        model_id: str,
        model_dir: Path | None,
        device: str,
        *,
        lora_dir: Path | None = None,
        qlora: bool = False,
    ) -> None:
        self.device = device
        self.model, self.processor = load_qwen25_vl_local(
            model_id,
            model_dir,
            device,
            lora_dir=lora_dir,
            qlora=qlora,
        )

    def infer(self, frame_paths: list[Path]) -> tuple[str, str, str]:
        from qwen_vl_utils import process_vision_info

        content: list[dict] = [{"type": "image", "image": str(p)} for p in frame_paths]
        content.append({"type": "text", "text": PROMPT})
        messages = [{"role": "user", "content": content}]

        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        generated = self.model.generate(**inputs, max_new_tokens=256)
        trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated)]
        raw = self.processor.batch_decode(trimmed, skip_special_tokens=True)[0]
        pred, reason = parse_qwen_json(raw)
        return pred, reason, raw


# --- Hub API inference -------------------------------------------------------

def build_hub_client(provider: str, model: str):
    from huggingface_hub import InferenceClient

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if provider in ("router", "auto"):
        return InferenceClient(provider=provider, token=token)
    return InferenceClient(model=model, token=token)


def infer_hub(client, model: str, frame_paths: list[Path]) -> tuple[str, str, str]:
    content: list[dict] = []
    for path in frame_paths:
        content.append({"type": "image_url", "image_url": {"url": frame_to_data_url(path)}})
    content.append({"type": "text", "text": PROMPT})
    kwargs = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 256,
        "temperature": 0.1,
    }
    try:
        response = client.chat.completions.create(model=model, **kwargs)
    except TypeError:
        response = client.chat.completions.create(**kwargs)
    raw = response.choices[0].message.content or ""
    pred, reason = parse_qwen_json(raw)
    return pred, reason, raw


def main() -> None:
    args = parse_args()
    videos = collect_videos(args.input)
    if args.max_videos > 0:
        videos = videos[: args.max_videos]
    if not videos:
        raise RuntimeError(f"No videos under {args.input}")

    if args.mode == "local":
        if args.gpu_id is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
        try:
            import torch  # noqa: F401
            from transformers import Qwen2_5_VLForConditionalGeneration  # noqa: F401
        except ImportError as exc:
            py = sys.executable
            raise SystemExit(
                "로컬 모드 패키지가 필요합니다:\n"
                f"  {py} -m pip install torch torchvision transformers accelerate qwen-vl-utils opencv-python\n"
                f"  ({exc})"
            ) from exc
        import torch

        if torch.cuda.is_available():
            device = "cuda:0"
            print(f"Using GPU physical_id={args.gpu_id} → {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            print("CUDA unavailable — running on CPU")
        runner: LocalQwen25 | None = LocalQwen25(args.model, args.model_dir, device)
        hub_client = None
    else:
        try:
            from huggingface_hub import InferenceClient  # noqa: F401
        except ImportError as exc:
            raise SystemExit(f"pip install huggingface_hub\n({exc})") from exc
        runner = None
        hub_client = build_hub_client(args.provider, args.model)
        if not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")):
            print("Warning: HF_TOKEN 없음 — hf auth login 또는 export HF_TOKEN=...")

    print(f"mode={args.mode}  model={args.model}" + (f"  gpu={args.gpu_id}" if args.mode == "local" else ""))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []

    for index, video_path in enumerate(videos, start=1):
        label, category = parse_label_category(video_path, args.input)
        actual = GOOD_LABEL if label == GOOD_LABEL else BAD_LABEL
        print(f"[{index}/{len(videos)}] {video_path.name} ({label}/{category})")

        try:
            frame_paths = sample_frame_paths(video_path, args.frames)
            if not frame_paths:
                raise RuntimeError("no frames read")
            if runner is not None:
                pred_label, reason, raw = runner.infer(frame_paths)
            else:
                pred_label, reason, raw = infer_hub(hub_client, args.model, frame_paths)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            rows.append(
                {
                    "video": video_path.name,
                    "label": label,
                    "category": category,
                    "actual": actual,
                    "predicted": "",
                    "qwen_label": "",
                    "reason": "",
                    "raw_response": str(exc),
                    "status": "error",
                    "mode": args.mode,
                    "correct": "no",
                }
            )
            continue

        predicted = BAD_LABEL if pred_label == "bad" else GOOD_LABEL
        correct = actual == predicted
        rows.append(
            {
                "video": video_path.name,
                "label": label,
                "category": category,
                "actual": actual,
                "predicted": predicted,
                "qwen_label": pred_label,
                "reason": reason,
                "raw_response": raw,
                "status": "ok",
                "mode": args.mode,
                "correct": "yes" if correct else "no",
            }
        )
        mark = "✓" if correct else "✗"
        print(f"  {mark} qwen={pred_label}  actual={label}  ({reason[:50]}...)")

    summary_csv = args.output_dir / "qwen25_validation_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    if not ok_rows:
        raise RuntimeError("No successful inference rows")

    matrix = np.zeros((2, 2), dtype=int)
    label_order = (GOOD_LABEL, BAD_LABEL)
    for row in ok_rows:
        matrix[label_order.index(row["actual"]), label_order.index(row["predicted"])] += 1

    metrics = classification_metrics(matrix)
    write_metrics_csv(
        args.output_dir / "qwen25_confusion_metrics.csv",
        0.0,
        metrics,
        False,
        f"qwen25_{args.mode}",
    )

    mode_label = "로컬" if args.mode == "local" else "Hub API"
    configure_plot_fonts()
    plot_confusion_matrix(
        matrix,
        metrics,
        0.0,
        int(metrics["n"]),
        len(rows) - len(ok_rows),
        False,
        args.output_dir / "qwen25_confusion_matrix_binary.png",
        f"Qwen2.5-VL 이진 분류 ({mode_label})\n{args.model}",
    )

    print(f"\nSaved: {summary_csv}")
    print(
        f"n={int(metrics['n'])}  Accuracy {metrics['accuracy']:.1%}  "
        f"Recall {metrics['recall']:.1%}  F1 {metrics['f1']:.3f}"
    )


if __name__ == "__main__":
    main()
