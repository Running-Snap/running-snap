"""
Qwen2.5-VL 코칭 파이프라인 (기본: MP JSON + 영상 → user_feedback, 1회 호출).

  .venv/bin/python analysis/generate_commentary_with_qwen.py --gpu-id 1 \\
    --video trim_1026_20260424_232310_649525.mp4 \\
    --pose-dir analysis/results_trim_1026_pose \\
    --profiles-dir analysis/results_trim_1026_profiles

  # LoRA 코칭 (QLoRA 학습 체크포인트)
  .venv/bin/python analysis/generate_commentary_with_qwen.py --gpu-id 1 --qlora \\
    --lora-dir finetune_data/checkpoints/qwen_commentary_lora \\
    --video trim_1026_20260424_232310_649525.mp4 \\
    --pose-dir analysis/results_trim_1026_pose \\
    --profiles-dir analysis/results_trim_1026_profiles

  # (선택) 1단계 Qwen 4축 good/bad 분류 후 코칭
  .venv/bin/python analysis/generate_commentary_with_qwen.py --four-axis-classify --gpu-id 1
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


def log_progress(msg: str) -> None:
    """터미널/tee에 즉시 출력 (영상별 진행 확인용)."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from qwen_commentary_prompt import (  # noqa: E402
    build_commentary_prompt,
    format_commentary_markdown,
    parse_commentary_json,
)
from sft_compact_schema import (  # noqa: E402
    STYLE_HWANG,
    axis_payload_to_compact_input,
    build_compact_user_text,
)
from user_feedback_schema import (  # noqa: E402
    build_user_feedback,
    finalize_user_feedback,
    format_pose_feedback_markdown,
    mp_bad_axis_keys,
    parse_user_feedback_json,
    qwen_attention_axis_keys,
    qwen_signals_bad,
    reconcile_summary_level,
)
from qwen_four_axis_context import (  # noqa: E402
    build_minimal_prompt_with_axis_context,
    build_prompt_with_axis_context,
    build_user_feedback_prompt_with_full_axis,
    compact_axis_payload,
    compute_axis_evaluation,
    load_axis_evaluation_for_video,
    parse_qwen_axis_json,
)
from validate_with_qwen import (  # noqa: E402
    DEFAULT_MODEL,
    LocalQwen25,
    build_hub_client,
    collect_videos,
    frame_to_data_url,
    parse_label_category,
)
from video_frame_utils import attach_frame_context, sample_frame_paths, sample_frames_with_meta  # noqa: E402
from validate_validation_dataset import find_pose_dir, video_output_name  # noqa: E402


class LocalQwen25Commentary(LocalQwen25):
    def _generate(self, frame_paths: list[Path], prompt: str, *, max_new_tokens: int) -> str:
        from qwen_vl_utils import process_vision_info

        content: list[dict] = [{"type": "image", "image": str(p)} for p in frame_paths]
        content.append({"type": "text", "text": prompt})
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

        generated = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated)]
        return self.processor.batch_decode(trimmed, skip_special_tokens=True)[0]

    def infer_classify(self, frame_paths: list[Path], prompt: str) -> tuple[str, str, list[str], str]:
        raw = self._generate(frame_paths, prompt, max_new_tokens=320)
        pred, reason, axes_bad = parse_qwen_axis_json(raw)
        return pred, reason, axes_bad, raw

    def infer_commentary(self, frame_paths: list[Path], prompt: str, *, max_new_tokens: int = 640) -> str:
        return self._generate(frame_paths, prompt, max_new_tokens=max_new_tokens)


def infer_hub_classify(
    client,
    model: str,
    frame_paths: list[Path],
    prompt: str,
) -> tuple[str, str, list[str], str]:
    content: list[dict] = []
    for path in frame_paths:
        content.append({"type": "image_url", "image_url": {"url": frame_to_data_url(path)}})
    content.append({"type": "text", "text": prompt})
    kwargs = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 320,
        "temperature": 0.1,
    }
    try:
        response = client.chat.completions.create(model=model, **kwargs)
    except TypeError:
        response = client.chat.completions.create(**kwargs)
    raw = response.choices[0].message.content or ""
    pred, reason, axes_bad = parse_qwen_axis_json(raw)
    return pred, reason, axes_bad, raw


def infer_hub_commentary(
    client,
    model: str,
    frame_paths: list[Path],
    prompt: str,
    *,
    max_tokens: int = 640,
) -> str:
    content: list[dict] = []
    for path in frame_paths:
        content.append({"type": "image_url", "image_url": {"url": frame_to_data_url(path)}})
    content.append({"type": "text", "text": prompt})
    kwargs = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    try:
        response = client.chat.completions.create(model=model, **kwargs)
    except TypeError:
        response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def load_qwen_prior(csv_path: Path) -> dict[str, dict[str, str]]:
    if not csv_path.exists():
        return {}
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        out[row["video"]] = {
            "qwen_label": row.get("qwen_label", ""),
            "qwen_axes_bad": row.get("qwen_axes_bad", ""),
            "reason": row.get("reason", ""),
        }
    return out


def resolve_axis_context(
    video_path: Path,
    *,
    axis_csv: Path,
    pose_root: Path,
    profiles_dir: Path,
    reference_dir: Path,
    output_name: str | None,
) -> tuple[dict, dict, str] | None:
    loaded = load_axis_evaluation_for_video(
        video_path.name,
        axis_csv=axis_csv,
        pose_dir=pose_root,
        profiles_dir=profiles_dir,
        reference_dir=reference_dir,
    )
    if loaded is not None:
        metrics, evaluation = loaded
        row = next(
            (r for r in csv.DictReader(axis_csv.open(encoding="utf-8")) if r["video"] == video_path.name),
            None,
        )
        out_name = row["output_name"] if row else output_name or video_output_name(video_path)
        return metrics, evaluation, out_name

    out_name = output_name or video_output_name(video_path)
    pose_dir = find_pose_dir(pose_root, video_path) or pose_root / out_name
    if not pose_dir.is_dir():
        return None
    if pose_dir.name != out_name:
        out_name = pose_dir.name
    metrics, evaluation = compute_axis_evaluation(
        out_name,
        pose_dir=pose_root,
        profiles_dir=profiles_dir,
        reference_dir=reference_dir,
    )
    return metrics, evaluation, out_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Base Qwen2.5-VL running commentary (해설) test")
    parser.add_argument("--input", type=Path, default=Path("validation_Data"))
    parser.add_argument("--video", type=Path, default=None, help="단일 영상 (프로젝트 루트 또는 절대 경로)")
    parser.add_argument("--output-name", type=str, default=None, help="pose/profile 서브디렉터리 이름")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/results_qwen_pose_feedback"),
    )
    parser.add_argument(
        "--output-format",
        choices=("user_feedback", "legacy_json"),
        default="user_feedback",
        help="user_feedback=사용자용 summary/checkpoints JSON (기본)",
    )
    parser.add_argument(
        "--axis-csv",
        type=Path,
        default=Path("analysis/results_validation_rules_compare/validation_summary_four_axis.csv"),
    )
    parser.add_argument("--pose-dir", type=Path, default=Path("analysis/results_validation_postprocess_pose"))
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("analysis/results_validation_postprocess_profiles"),
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("analysis/reference_marathon_postprocess"),
    )
    parser.add_argument(
        "--four-axis-classify",
        action="store_true",
        help="(선택) 1단계 Qwen 4축 good/bad 분류 후 2단계 코칭. 기본은 코칭만 1회",
    )
    parser.add_argument(
        "--minimal-classify-prompt",
        action="store_true",
        help="--four-axis-classify 시 분류 프롬프트 최소화",
    )
    parser.add_argument(
        "--qwen-csv",
        type=Path,
        default=None,
        help="(미사용 기본) 예전 1단계 분류 CSV — --four-axis-classify 없으면 무시",
    )
    parser.add_argument(
        "--minimal-prompt",
        action="store_true",
        help="해설 프롬프트 최소화 (JSON + 출력 스키마만, 코칭 규칙·MP 판정 힌트 없음)",
    )
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument(
        "--lora-dir",
        type=Path,
        default=None,
        help="LoRA 체크포인트 (예: finetune_data/checkpoints/qwen_commentary_lora)",
    )
    parser.add_argument(
        "--qlora",
        action="store_true",
        help="4bit 베이스 + LoRA (학습이 QLoRA였을 때 VRAM 절약)",
    )
    parser.add_argument("--mode", choices=("local", "hub"), default="local")
    parser.add_argument("--max-videos", type=int, default=0)
    parser.add_argument(
        "--frames",
        type=int,
        default=8,
        help="균등 샘플 8장 + MP 이상 구간 주변(--neighbor-frames)",
    )
    parser.add_argument("--neighbor-frames", type=int, default=2)
    parser.add_argument("--max-abnormal-centers", type=int, default=6)
    parser.add_argument("--no-hybrid-sampling", action="store_true")
    parser.add_argument("--gpu-id", type=int, default=1)
    parser.add_argument("--provider", type=str, default="hf-inference")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument(
        "--init-labels-for-sft",
        action="store_true",
        help="MP 지표→user_feedback 초안을 finetune_data/labels/ 에 저장 (추론 없음)",
    )
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=Path("finetune_data/labels/drafts"),
        help="--init-labels-for-sft 초안 저장 (승인 후 finetune_data/labels/)",
    )
    return parser.parse_args()


def write_sft_label_draft(
    labels_dir: Path,
    stem: str,
    *,
    video: str,
    label: str,
    category: str,
    axis_payload: dict,
    user_fb: dict,
) -> Path:
    labels_dir.mkdir(parents=True, exist_ok=True)
    path = labels_dir / f"{stem}.json"
    if path.exists():
        return path
    body = {
        "_approved": False,
        "_note": "검토 후 _approved: true. EXAMPLE_user_feedback.json 참고",
        "video": video,
        "label": label,
        "category": category,
        "input": axis_payload_to_compact_input(axis_payload),
        "style": STYLE_HWANG,
        "user_feedback": user_fb,
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_four_axis_classify(
    frame_paths: list[Path],
    payload: dict,
    *,
    runner: LocalQwen25Commentary | None,
    hub_client,
    model: str,
    minimal: bool,
) -> dict:
    prompt = (
        build_minimal_prompt_with_axis_context(payload)
        if minimal
        else build_prompt_with_axis_context(payload)
    )
    if runner is not None:
        pred, reason, axes_bad, raw = runner.infer_classify(frame_paths, prompt)
    else:
        pred, reason, axes_bad, raw = infer_hub_classify(hub_client, model, frame_paths, prompt)
    return {
        "qwen_label": pred,
        "axes_bad": axes_bad,
        "reason": reason,
        "raw_response": raw,
    }


def prior_from_classification(fc: dict) -> dict[str, str]:
    return {
        "qwen_label": fc.get("qwen_label", ""),
        "qwen_axes_bad": ";".join(fc.get("axes_bad") or []),
        "reason": fc.get("reason", ""),
    }


def build_commentary_prompt_for_run(
    args: argparse.Namespace,
    payload: dict,
    evaluation: dict,
    prior: dict,
) -> str:
    if args.output_format == "user_feedback":
        axes = [a.strip() for a in prior.get("qwen_axes_bad", "").split(";") if a.strip()]
        coaching_only = not args.four_axis_classify
        return build_user_feedback_prompt_with_full_axis(
            payload,
            qwen_label=prior.get("qwen_label", ""),
            qwen_axes_bad=axes or None,
            qwen_reason=prior.get("reason", ""),
            style=STYLE_HWANG,
            coaching_only=coaching_only,
        )
    compact = axis_payload_to_compact_input(payload)
    if args.minimal_prompt:
        from qwen_commentary_prompt import build_minimal_commentary_prompt

        return build_minimal_commentary_prompt(payload)
    mp_hint = str(evaluation.get("predicted", ""))
    qwen_axes = [a.strip() for a in prior.get("qwen_axes_bad", "").split(";") if a.strip()]
    return build_commentary_prompt(
        payload,
        mp_predicted=mp_hint,
        qwen_label=prior.get("qwen_label", ""),
        qwen_axes_bad=qwen_axes or None,
    )


def collect_targets(args: argparse.Namespace) -> list[Path]:
    if args.video is not None:
        path = args.video if args.video.is_absolute() else ROOT / args.video
        if not path.exists():
            raise FileNotFoundError(path)
        return [path]
    videos = collect_videos(args.input)
    if args.max_videos > 0:
        videos = videos[: args.max_videos]
    return videos


def main() -> None:
    args = parse_args()
    videos = collect_targets(args)
    if not videos:
        raise RuntimeError("No videos to process")

    from pose_rules import load_pose_rules

    pose_rules = load_pose_rules(args.reference_dir / "pose_rules.json")
    qwen_prior_csv = load_qwen_prior(args.qwen_csv) if args.qwen_csv else {}
    classify_inline = args.four_axis_classify
    log_progress(
        f"시작 | 출력={args.output_format} | "
        f"모드={'분류+코칭(2회)' if classify_inline else '코칭만(MP JSON+영상, 1회)'} | "
        f"샘플={'uniform' if args.no_hybrid_sampling else f'hybrid uniform={args.frames}+MP이상±{args.neighbor_frames}'}"
    )

    if args.init_labels_for_sft:
        runner = None
        hub_client = None
    elif args.mode == "local":
        if args.gpu_id is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
        try:
            import torch  # noqa: F401
        except ImportError as exc:
            raise SystemExit(f"pip install torch transformers qwen-vl-utils\n({exc})") from exc
        import torch

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        lora_msg = f"  lora={args.lora_dir}" if args.lora_dir else ""
        log_progress(f"모델 로드 중 | device={device} model={args.model}{lora_msg} qlora={args.qlora}")
        runner: LocalQwen25Commentary | None = LocalQwen25Commentary(
            args.model,
            args.model_dir,
            device,
            lora_dir=args.lora_dir,
            qlora=args.qlora,
        )
        hub_client = None
    else:
        from huggingface_hub import InferenceClient  # noqa: F401

        runner = None
        hub_client = build_hub_client(args.provider, args.model)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    per_video_dir = args.output_dir / "per_video"
    per_video_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, str]] = []

    log_progress(f"영상 {len(videos)}건 처리 시작 → {per_video_dir}")
    for index, video_path in enumerate(videos, start=1):
        t0 = time.perf_counter()
        label, category = "", ""
        if args.video is None:
            label, category = parse_label_category(video_path, args.input)

        log_progress(f"[{index}/{len(videos)}] {video_path.name}  (폴더: {label or '-'}/{category or '-'})")

        resolved = resolve_axis_context(
            video_path,
            axis_csv=args.axis_csv,
            pose_root=args.pose_dir,
            profiles_dir=args.profiles_dir,
            reference_dir=args.reference_dir,
            output_name=args.output_name,
        )
        if resolved is None:
            log_progress(f"  skip: no pose/profile context  ({time.perf_counter() - t0:.1f}s)")
            summary_rows.append(
                {
                    "video": video_path.name,
                    "status": "skip_no_context",
                    "label": label,
                    "category": category,
                }
            )
            continue

        metrics, evaluation, out_name = resolved
        payload = compact_axis_payload(metrics, evaluation)
        pdir = args.pose_dir / out_name
        prior = qwen_prior_csv.get(video_path.name, {}) if classify_inline else {}
        four_axis_fc: dict | None = None
        stem = video_path.stem.replace(" ", "_")

        if args.init_labels_for_sft:
            draft_fb = build_user_feedback(payload)
            write_sft_label_draft(
                args.labels_dir,
                stem,
                video=video_path.name,
                label=label,
                category=category,
                axis_payload=payload,
                user_fb=draft_fb,
            )
            log_progress(f"  label draft saved  ({time.perf_counter() - t0:.1f}s)")
            summary_rows.append(
                {
                    "video": video_path.name,
                    "status": "label_draft",
                    "labels_path": str((args.labels_dir / f"{stem}.json").resolve().relative_to(ROOT.resolve())),
                }
            )
            continue

        try:
            log_progress(f"  프레임 샘플링(hybrid) …")
            frame_paths, frame_meta = sample_frames_with_meta(
                video_path,
                args.frames,
                pose_dir=pdir if pdir.is_dir() else None,
                evaluation=evaluation,
                rules_axes=pose_rules.axes,
                neighbors_per_abnormal=args.neighbor_frames,
                max_abnormal_centers=args.max_abnormal_centers,
                use_hybrid=not args.no_hybrid_sampling,
            )
            payload = attach_frame_context(payload, frame_meta)
            if not frame_paths:
                raise RuntimeError("no frames")
            strategy = (frame_meta or {}).get("qwen_sample_strategy", "?")
            log_progress(f"  프레임 {len(frame_paths)}장 ({strategy})")

            if classify_inline:
                four_axis_fc = run_four_axis_classify(
                    frame_paths,
                    payload,
                    runner=runner,
                    hub_client=hub_client,
                    model=args.model,
                    minimal=args.minimal_classify_prompt,
                )
                prior = prior_from_classification(four_axis_fc)
                log_progress(
                    f"  classify: {prior.get('qwen_label')}  "
                    f"axes={prior.get('qwen_axes_bad', '') or 'none'}"
                )

            prompt = build_commentary_prompt_for_run(args, payload, evaluation, prior)
            log_progress("  Qwen 코칭 생성 중 …")
            if runner is not None:
                raw = runner.infer_commentary(frame_paths, prompt, max_new_tokens=args.max_new_tokens)
            else:
                raw = infer_hub_commentary(
                    hub_client,
                    args.model,
                    frame_paths,
                    prompt,
                    max_tokens=args.max_new_tokens,
                )
        except Exception as exc:
            log_progress(f"  ERROR: {exc}  ({time.perf_counter() - t0:.1f}s)")
            summary_rows.append(
                {
                    "video": video_path.name,
                    "label": label,
                    "category": category,
                    "output_name": out_name,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        user_fb = parse_user_feedback_json(raw)
        qwen_parsed = user_fb
        parse_ok = user_fb is not None
        mp_qwen_agreement = None
        if user_fb is None and args.output_format == "user_feedback":
            user_fb = build_user_feedback(payload)
            parse_ok = False
        elif user_fb is not None and args.output_format == "user_feedback":
            qwen_label = prior.get("qwen_label", "")
            axes_bad = [a.strip() for a in prior.get("qwen_axes_bad", "").split(";") if a.strip()]
            user_fb = finalize_user_feedback(
                user_fb,
                payload,
                qwen_label=qwen_label,
                qwen_axes_bad=axes_bad or None,
            )
            mp_bad = bool(mp_bad_axis_keys(payload))
            qwen_attn = set(qwen_attention_axis_keys(qwen_parsed or {}))
            if axes_bad:
                qwen_attn |= set(axes_bad)
            qwen_bad = qwen_signals_bad(qwen_parsed or {}) or bool(qwen_attn)
            if qwen_label == "good":
                qwen_bad = False
            elif qwen_label == "bad":
                qwen_bad = True
            mp_qwen_agreement = {
                "mp_bad": mp_bad,
                "qwen_bad": qwen_bad,
                "level": reconcile_summary_level(mp_bad=mp_bad, qwen_bad=qwen_bad),
                "mp_bad_axes": sorted(mp_bad_axis_keys(payload)),
                "qwen_attention_axes": sorted(qwen_attn),
            }

        parsed = parse_commentary_json(raw) if args.output_format == "legacy_json" else {}
        stem = video_path.stem.replace(" ", "_")
        json_path = per_video_dir / f"{stem}_feedback.json"
        md_path = per_video_dir / f"{stem}_feedback.md"
        record = {
            "video": video_path.name,
            "label": label,
            "category": category,
            "output_name": out_name,
            "mp_predicted": evaluation.get("predicted", ""),
            "mp_triggers": evaluation.get("triggers", []),
            "axis_context": payload,
            "compact_input": axis_payload_to_compact_input(payload),
            "four_axis_classification": four_axis_fc,
            "qwen_prior": prior or None,
            "user_feedback": user_fb,
            "mp_qwen_agreement": mp_qwen_agreement,
            "commentary_legacy": parsed if args.output_format == "legacy_json" else None,
            "raw_response": raw,
            "model": args.model,
            "mode": args.mode,
            "output_format": args.output_format,
            "parse_ok": parse_ok,
            "classify_inline": classify_inline,
        }
        json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        if user_fb:
            md_fb = {**user_fb, "frame_context": payload.get("frame_context") or user_fb.get("frame_context")}
            md_path.write_text(
                format_pose_feedback_markdown(
                    video_path.name,
                    md_fb,
                    four_axis=four_axis_fc,
                    mp_predicted=str(evaluation.get("predicted", "")),
                ),
                encoding="utf-8",
            )
        elif parsed:
            md_path.write_text(
                format_commentary_markdown(video_path.name, parsed, axis_payload=payload),
                encoding="utf-8",
            )

        level = (user_fb or {}).get("summary", {}).get("level", parsed.get("overall", ""))
        title = (user_fb or {}).get("summary", {}).get("title", parsed.get("headline", ""))
        summary_rows.append(
            {
                "video": video_path.name,
                "label": label,
                "category": category,
                "output_name": out_name,
                "mp_predicted": str(evaluation.get("predicted", "")),
                "qwen_label": prior.get("qwen_label", ""),
                "qwen_axes_bad": prior.get("qwen_axes_bad", ""),
                "level": level,
                "title": (title or "")[:80],
                "parse_ok": "yes" if parse_ok else "fallback",
                "status": "ok",
                "json_path": str(json_path.resolve().relative_to(ROOT.resolve())),
                "md_path": str(md_path.resolve().relative_to(ROOT.resolve())),
            }
        )
        log_progress(f"  ok level={level}  {str(title)[:50]}  ({time.perf_counter() - t0:.1f}s)")

    summary_csv = args.output_dir / "commentary_base_summary.csv"
    if summary_rows:
        fieldnames = sorted({k for r in summary_rows for k in r})
        with summary_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(summary_rows)
        log_progress(f"완료 | summary: {summary_csv}")
        log_progress(f"Per-video: {per_video_dir}/")


if __name__ == "__main__":
    main()
