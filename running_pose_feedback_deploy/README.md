# Running Snap — 자세 코칭 모델 배포 패키지

**최종 모델:** MediaPipe 4축 rule + Qwen2.5-VL-7B-Instruct + QLoRA (`qwen_commentary_lora`)

러닝 **mp4 1개** → MediaPipe 분석 → **한국어 코칭 리포트(`feedback.md`)** 까지 돌리는 패키지입니다.

---

## 빠른 시작 (요약)

```bash
# 1) 압축 해제 후 폴더로 이동
cd running_pose_feedback_deploy

# 2) 가상환경 + 패키지 (최초 1회)
python3 -m venv .venv
source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

# 3) 실행 (GPU 0번 사용 예시)
./run_single_video.sh /path/to/your_run.mp4 0
```

결과: `work/output/per_video/<영상이름>_feedback.md`

---

## 사전 요구사항

| 항목 | 권장 |
|------|------|
| OS | Linux (Ubuntu 22.04+) |
| GPU | NVIDIA, VRAM **24GB+** |
| CUDA | 12.x |
| Python | 3.10 ~ 3.12 |
| 디스크 | **20GB+** 여유 (베이스 Qwen HF 다운로드) |
| 네트워크 | **첫 실행 시** Hugging Face 접속 필요 |

> 베이스 모델 `Qwen/Qwen2.5-VL-7B-Instruct`는 패키지에 없고, **첫 추론 때 자동 다운로드** (~15GB) 됩니다.  
> LoRA 가중치(`adapter_model.safetensors`, ~91MB)는 **이미 포함**되어 있습니다.

---

## 설치 (최초 1회)

```bash
cd running_pose_feedback_deploy

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# GPU(CUDA 12)용 PyTorch — CPU만이면 cu124 대신 기본 pip torch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

**(선택) Hugging Face 토큰** — 다운로드 rate limit 완화:

```bash
export HF_TOKEN=hf_xxxxxxxx
```

---

## 실행 방법

### 방법 A — 쉘 스크립트 (권장)

```bash
source .venv/bin/activate
chmod +x run_single_video.sh   # 최초 1회
./run_single_video.sh /path/to/video.mp4 0
```

| 인자 | 설명 |
|------|------|
| 1번째 | 분석할 **mp4/mov** 경로 (절대·상대 경로 모두 가능) |
| 2번째 | **GPU 번호** (0, 1, …) → 내부에서 `CUDA_VISIBLE_DEVICES` 설정 |

**내부 동작 (2단계):**

1. **MediaPipe** — 포즈 추출, 보행 주기, 4축 feature, `pose_rules.json` 판정  
2. **Qwen + LoRA** — hybrid 프레임 + 4축 JSON 프롬프트 → `user_feedback` → `feedback.md`

**출력 위치:**

```
work/
├── pose/          # MediaPipe CSV (person_1_elbow_angles.csv)
├── profiles/      # phase 프로파일
└── output/
    └── per_video/
        ├── Video_Project_3_feedback.md   ← 사용자용 리포트
        └── Video_Project_3_feedback.json ← 전체 JSON
```

예시 확인: `examples/sample_feedback.md`

---

### 방법 B — Python 단계별 실행

전처리와 추론을 나눠 돌릴 때:

```bash
source .venv/bin/activate
VIDEO="/path/to/run.mp4"

# Step 1: MediaPipe + phase 프로파일
python analysis/run_pose_and_feedback.py preprocess \
  --video "$VIDEO" \
  --pose-dir work/pose \
  --profiles-dir work/profiles

# Step 2: Qwen2.5-VL + QLoRA 코칭
python analysis/generate_commentary_with_qwen.py \
  --gpu-id 0 \
  --qlora \
  --lora-dir finetune_data/checkpoints/qwen_commentary_lora \
  --video "$VIDEO" \
  --pose-dir work/pose \
  --profiles-dir work/profiles \
  --reference-dir analysis/reference_marathon_postprocess \
  --output-dir work/output
```

---

## 포함 파일

| 경로 | 설명 |
|------|------|
| `analysis/` | 추론·MP 전처리 Python |
| `analysis/reference_marathon_postprocess/` | **MP 4축 rule** (`pose_rules.json`, 정상 분포) |
| `finetune_data/checkpoints/qwen_commentary_lora/` | **LoRA** `adapter_model.safetensors` |
| `run_single_video.sh` | 원클릭 실행 |
| `requirements.txt` | pip 의존성 |

---

## 자주 묻는 점

**Q. MP 4축도 가중치 파일이 있나요?**  
A. 아닙니다. `pose_rules.json` + MediaPipe 코드로 동작하는 **규칙 엔진**이며, reference 폴더에 포함되어 있습니다.

**Q. OCR / 클립 분할은?**  
A. 이 패키지에는 없습니다. **이미 잘린 mp4**를 넣으면 됩니다.

**Q. 어떤 영상이 잘 되나요?**  
A. **측면**에서 찍은 **전신 러닝** 클립 (6초 이상, 러너가 프레임 안에 유지).

**Q. 재학습하려면?**  
A. 원본 개발 repo + `train.jsonl` + `requirements-finetune.txt` 필요 (이 패키지만으로는 불가).

---

## 문제 해결

| 증상 | 확인 |
|------|------|
| `CUDA out of memory` | GPU VRAM 부족 → 더 큰 GPU 또는 `--gpu-id` 변경 |
| HF 다운로드 실패 | `HF_TOKEN` 설정, 프록시/방화벽 확인 |
| `Pose export failed` | 영상 너무 짧음·러너 미검출 → 측면·길이 확인 |
| `skip: no pose/profile context` | Step 1 전처리 실패 → `work/pose/` CSV 존재 여부 확인 |

---

## 버전 정보

- 베이스 VLM: `Qwen/Qwen2.5-VL-7B-Instruct`
- LoRA: `finetune_data/checkpoints/qwen_commentary_lora/`
- 학습 메타: `finetune_data/checkpoints/qwen_commentary_lora/train_meta.json` (SFT 53건, 3 epochs)
