# Person Appearance Pipeline Bundle

업로드/배포용 복사본입니다. 이 폴더만 GitHub에 올려도 실행 가능합니다.

## 기능
- 멀티 사람 검출 + 트래킹 + OCR 후보 누적
- 트랙별 최종 라벨 결정(`confidence` 또는 `frequency`)
- `track_events.json` 저장
- `unknown_*` 라벨 제외한 풀프레임 클립 저장
- 2가지 모드 지원:
  - `file`: 업로드 영상 처리 후 종료
  - `live`: 카메라/RTSP 실시간 처리(수동 중지 전까지 계속)

## 설치
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## YOLO 모델 준비
기본 경로는 `yolov8n.pt` 입니다.

### 방법 1) 자동 다운로드 스크립트(권장)
```bash
python download_yolov8n.py
```

### 방법 2) 직접 배치
`yolov8n.pt` 파일을 프로젝트 루트(이 README와 같은 폴더)에 직접 넣어도 됩니다.

## 실행 (파일 모드)
```bash
python run_person_appearance_pipeline.py \
  --mode file \
  --video /path/to/video.mp4 \
  --out appearance_report_output \
  --ocr-backend easyocr \
  --ocr-interval 5 \
  --label-policy confidence \
  --progress-log-interval 60
```

## 실행 (라이브 모드 - 웹캠)
```bash
python run_person_appearance_pipeline.py \
  --mode live \
  --source 0 \
  --out appearance_live_output \
  --ocr-backend easyocr \
  --ocr-interval 5 \
  --label-policy confidence \
  --progress-log-interval 60
```

## 실행 (라이브 모드 - RTSP)
```bash
python run_person_appearance_pipeline.py \
  --mode live \
  --source "rtsp://user:pass@ip:554/stream1" \
  --out appearance_live_output \
  --ocr-backend easyocr \
  --ocr-interval 5 \
  --label-policy confidence \
  --progress-log-interval 60
```

## GPU 사용
- 기본: GPU 사용 시도 (CUDA 없으면 자동 CPU fallback)
- YOLO CPU 강제: `--no-gpu-yolo`
- OCR CPU 강제: `--no-gpu-ocr`

## 출력
- `<out>/track_events.json`
- `<out>/fullframe_label_clips/*.mp4`

라이브 모드는 자동 종료되지 않습니다. 종료는 `Ctrl + C`를 사용하세요.

