# 로컬 AI 설정 가이드

> **목적**: API 키 없이 본인 컴퓨터에서 AI 기능 돌리기
> **대상**: 백엔드 개발자

---

## 왜 로컬 AI를 쓰나?

| 방식 | 장점 | 단점 |
|------|------|------|
| **API (클라우드)** | 빠름, 설치 불필요 | 유료, API 키 필요, 인터넷 필요 |
| **로컬 (Ollama)** | 무료, 오프라인 가능, 데이터 외부 전송 없음 | 느림, GPU 권장, 초기 설정 필요 |

우리 프로젝트는 **2가지 AI**를 사용:
1. **Qwen** (영상 분석) → Ollama로 대체
2. **Claude** (편집 대본 생성) → Claude Code CLI로 대체

---

## 1. Ollama 설치 (영상 분석용)

### Ollama가 뭐야?

- 로컬에서 LLM 돌리는 프로그램
- Docker처럼 모델을 pull해서 사용
- 우리는 `qwen2.5vl:7b` 모델 사용 (비전 모델 = 이미지 이해 가능)

### 1.1 설치

```bash
# macOS
brew install ollama

# 또는 공식 사이트에서 다운로드
# https://ollama.ai/download
```

**Ubuntu/Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**Windows:**
- https://ollama.ai/download 에서 설치 파일 다운로드

### 1.2 모델 다운로드

```bash
# Ollama 서버 시작 (백그라운드)
ollama serve &

# 비전 모델 다운로드 (약 6GB, 처음 한 번만)
ollama pull qwen2.5vl:7b
```

> ⚠️ **주의**: 다운로드 시간 10~30분 (인터넷 속도에 따라)

### 1.3 설치 확인

```bash
# 모델 목록 확인
ollama list

# 예상 출력:
# NAME              ID              SIZE      MODIFIED
# qwen2.5vl:7b      5ced39dfa4ba    6.0 GB    2 minutes ago
```

### 1.4 테스트

```bash
# 텍스트 테스트
ollama run qwen2.5vl:7b "안녕하세요"

# 이미지 테스트 (비전 기능)
# Python에서 테스트 (아래 참고)
```

**Python 테스트:**
```python
import requests
import base64

# 이미지를 base64로 인코딩
with open("test_image.jpg", "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode()

# Ollama API 호출
response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5vl:7b",
        "prompt": "이 이미지에서 무슨 일이 일어나고 있어?",
        "images": [image_base64],
        "stream": False
    }
)

print(response.json()["response"])
```

### 1.5 Ollama 서버 자동 시작 (선택)

**macOS (launchd):**
```bash
# 로그인 시 자동 시작
brew services start ollama
```

**Linux (systemd):**
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

---

## 2. Claude Code CLI 설치 (편집 대본 생성용)

### Claude Code CLI가 뭐야?

- Anthropic에서 만든 터미널 기반 AI 어시스턴트
- API 키 없이 Claude 사용 가능 (로그인만 하면 됨)
- 우리 프로젝트에서 편집 대본 생성에 사용

### 2.1 설치

```bash
# npm으로 설치 (Node.js 필요)
npm install -g @anthropic-ai/claude-code

# 또는 Homebrew (macOS)
brew install claude-code
```

**Node.js 없으면:**
```bash
# macOS
brew install node

# Ubuntu
sudo apt install nodejs npm
```

### 2.2 로그인

```bash
# 처음 한 번만 로그인
claude login
```

브라우저가 열리고 Anthropic 계정으로 로그인하면 됨.
(계정 없으면 무료로 만들 수 있음)

### 2.3 테스트

```bash
# 간단한 테스트
claude "안녕하세요, 테스트입니다"

# JSON 응답 테스트
claude --output-format json "1+1은?"
```

### 2.4 우리 프로젝트에서 사용하는 방식

코드 내부에서 이렇게 호출함:

```python
import subprocess
import json

def call_claude(prompt: str) -> str:
    """Claude Code CLI 호출"""
    result = subprocess.run(
        ["claude", "--output-format", "json", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode == 0:
        response = json.loads(result.stdout)
        return response.get("result", "")
    else:
        raise Exception(f"Claude 호출 실패: {result.stderr}")
```

---

## 3. 전체 환경 체크리스트

### 설치 확인 명령어

```bash
# 1. Ollama 확인
ollama --version
# 예상: ollama version 0.x.x

# 2. Ollama 서버 실행 중인지 확인
curl http://localhost:11434/api/version
# 예상: {"version":"0.x.x"}

# 3. 모델 설치 확인
ollama list | grep qwen
# 예상: qwen2.5vl:7b  ...

# 4. Claude CLI 확인
claude --version
# 예상: claude-code x.x.x

# 5. ffmpeg 확인 (영상 처리용)
ffmpeg -version
# 예상: ffmpeg version x.x.x

# 6. Python 의존성 확인
pip list | grep -E "(moviepy|opencv|pydantic)"
```

### 환경 테스트 스크립트

```python
#!/usr/bin/env python3
"""환경 테스트 스크립트"""
import subprocess
import requests
import sys

def check_ollama():
    """Ollama 서버 체크"""
    try:
        r = requests.get("http://localhost:11434/api/version", timeout=5)
        if r.status_code == 200:
            print("✅ Ollama 서버: 정상")
            return True
    except:
        pass
    print("❌ Ollama 서버: 실행 안 됨")
    print("   → 'ollama serve' 실행 필요")
    return False

def check_qwen_model():
    """Qwen 모델 체크"""
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True, text=True
    )
    if "qwen2.5vl" in result.stdout:
        print("✅ Qwen 모델: 설치됨")
        return True
    print("❌ Qwen 모델: 없음")
    print("   → 'ollama pull qwen2.5vl:7b' 실행 필요")
    return False

def check_claude_cli():
    """Claude CLI 체크"""
    result = subprocess.run(
        ["claude", "--version"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✅ Claude CLI: 설치됨")
        return True
    print("❌ Claude CLI: 없음")
    print("   → 'npm install -g @anthropic-ai/claude-code' 실행 필요")
    return False

def check_ffmpeg():
    """ffmpeg 체크"""
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✅ ffmpeg: 설치됨")
        return True
    print("❌ ffmpeg: 없음")
    print("   → 'brew install ffmpeg' 또는 'apt install ffmpeg' 실행 필요")
    return False

if __name__ == "__main__":
    print("=" * 50)
    print("로컬 AI 환경 체크")
    print("=" * 50)

    results = [
        check_ollama(),
        check_qwen_model(),
        check_claude_cli(),
        check_ffmpeg()
    ]

    print("=" * 50)
    if all(results):
        print("🎉 모든 환경 준비 완료!")
        sys.exit(0)
    else:
        print("⚠️  일부 환경 설정 필요")
        sys.exit(1)
```

이 스크립트를 `check_env.py`로 저장하고 실행:
```bash
python check_env.py
```

---

## 4. 프로젝트 실행

### 4.1 기본 실행 (로컬 AI)

```bash
cd video-editor

# --local 옵션으로 로컬 AI 사용
python main.py input.mp4 -d 10 -s action --local
```

### 4.2 코드에서 사용

```python
from src.api import VideoEditorAPI, VideoEditorConfig, ProcessingMode

# 로컬 모드 설정
config = VideoEditorConfig(
    mode=ProcessingMode.LOCAL,  # ← 이게 핵심!
    ollama_model="qwen2.5vl:7b"
)

api = VideoEditorAPI(config)
result = api.process("input.mp4", duration=10, style="action")
```

---

## 5. 문제 해결

### Q: "Ollama 연결 실패" 에러

```
원인: Ollama 서버가 안 돌아가고 있음

해결:
1. ollama serve  # 서버 시작
2. 다시 실행
```

### Q: "model 'qwen2.5vl:7b' not found" 에러

```
원인: 모델 다운로드 안 됨

해결:
1. ollama pull qwen2.5vl:7b  # 모델 다운로드 (6GB)
2. ollama list  # 확인
3. 다시 실행
```

### Q: "Claude CLI 명령어 없음" 에러

```
원인: Claude Code CLI 설치 안 됨

해결:
1. npm install -g @anthropic-ai/claude-code
2. claude --version  # 확인
3. claude login  # 로그인 (처음만)
4. 다시 실행
```

### Q: 처리가 너무 느림

```
원인: GPU 없이 CPU로 돌아가는 중

해결 (선택지):
1. GPU 있는 컴퓨터 사용 (NVIDIA 권장)
2. 클라우드 GPU 서버 사용 (AWS, GCP 등)
3. 더 작은 모델 사용: ollama pull qwen2.5vl:3b
4. API 모드로 전환 (유료지만 빠름)
```

### Q: 메모리 부족

```
원인: qwen2.5vl:7b는 약 8GB RAM 필요

해결:
1. 다른 프로그램 종료
2. 더 작은 모델 사용: qwen2.5vl:3b (3GB)
3. RAM 16GB 이상 권장
```

---

## 6. 하드웨어 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| **CPU** | 4코어 | 8코어+ |
| **RAM** | 8GB | 16GB+ |
| **GPU** | 없어도 됨 | NVIDIA 8GB VRAM |
| **저장공간** | 10GB | 20GB+ |
| **OS** | macOS 12+, Ubuntu 20.04+, Windows 10+ | - |

### GPU 사용 (선택, 훨씬 빠름)

**NVIDIA GPU가 있으면:**
```bash
# CUDA 설치 확인
nvidia-smi

# Ollama가 자동으로 GPU 사용
# 별도 설정 불필요
```

**Apple Silicon (M1/M2/M3):**
```bash
# Metal 자동 사용
# 별도 설정 불필요
```

---

## 7. 요약: 빠른 설정 (5분)

```bash
# 1. Ollama 설치
brew install ollama  # macOS
# curl -fsSL https://ollama.ai/install.sh | sh  # Linux

# 2. Ollama 서버 시작 & 모델 다운로드
ollama serve &
ollama pull qwen2.5vl:7b

# 3. Claude CLI 설치 & 로그인
npm install -g @anthropic-ai/claude-code
claude login

# 4. 테스트
cd video-editor
python main.py test-move.MOV -d 10 -s action --local
```

---

## 부록: 내부 동작 원리

### Ollama가 코드에서 어떻게 호출되는지

```
main.py
    │
    └─► pipeline.py
            │
            └─► analyzers/frame_analyzer.py
                    │
                    └─► OllamaFrameAnalyzer.analyze_frame()
                            │
                            ├─► 프레임 이미지를 base64로 인코딩
                            │
                            └─► HTTP POST http://localhost:11434/api/generate
                                    │
                                    └─► Ollama 서버가 qwen2.5vl:7b로 추론
                                            │
                                            └─► JSON 응답 반환
```

**실제 코드 (frame_analyzer.py):**
```python
class OllamaFrameAnalyzer:
    def __init__(self, model: str = "qwen2.5vl:7b"):
        self.model = model
        self.base_url = "http://localhost:11434"

    async def analyze_frame(self, frame_path: str, timestamp: float):
        # 이미지 → base64
        with open(frame_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()

        # Ollama API 호출
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": "이 러닝 영상 프레임을 분석해줘...",
                "images": [image_base64],
                "stream": False
            }
        )

        # 응답 파싱
        result = response.json()
        return self._parse_response(result["response"])
```

### Claude CLI가 코드에서 어떻게 호출되는지

```
main.py
    │
    └─► pipeline.py
            │
            └─► directors/script_generator.py
                    │
                    └─► ClaudeCodeScriptGenerator.generate()
                            │
                            ├─► 프롬프트 생성 (분석 결과 + 스타일 지시)
                            │
                            └─► subprocess.run(["claude", "-p", prompt])
                                    │
                                    └─► Claude Code CLI가 처리
                                            │
                                            └─► JSON 응답 반환
```

**실제 코드 (script_generator.py):**
```python
class ClaudeCodeScriptGenerator:
    async def generate(self, video_analysis, target_duration, style):
        # 프롬프트 생성
        prompt = self._build_prompt(video_analysis, target_duration, style)

        # Claude CLI 호출
        result = subprocess.run(
            ["claude", "--output-format", "json", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            raise Exception(f"Claude 실패: {result.stderr}")

        # 응답 파싱
        response = json.loads(result.stdout)
        return self._parse_script(response["result"])
```

---

**끝. 질문 있으면 언제든 연락!**
