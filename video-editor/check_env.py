#!/usr/bin/env python3
"""
환경 체크 스크립트
로컬 AI 실행에 필요한 모든 의존성을 확인합니다.

사용법:
    python check_env.py
"""
import subprocess
import sys
import shutil
from pathlib import Path

# 색상 출력
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(text):
    print(f"\n{BOLD}{'=' * 50}{RESET}")
    print(f"{BOLD}{text}{RESET}")
    print(f"{BOLD}{'=' * 50}{RESET}")


def print_ok(text):
    print(f"{GREEN}✅ {text}{RESET}")


def print_fail(text):
    print(f"{RED}❌ {text}{RESET}")


def print_warn(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")


def print_hint(text):
    print(f"   → {text}")


def check_python_version():
    """Python 버전 체크"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print_ok(f"Python 버전: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_fail(f"Python 버전: {version.major}.{version.minor} (3.9+ 필요)")
        print_hint("Python 3.9 이상 설치 필요")
        return False


def check_ollama_installed():
    """Ollama 설치 체크"""
    if shutil.which("ollama"):
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        version = result.stdout.strip() or result.stderr.strip()
        print_ok(f"Ollama 설치됨: {version}")
        return True
    else:
        print_fail("Ollama 설치 안 됨")
        print_hint("brew install ollama  # macOS")
        print_hint("curl -fsSL https://ollama.ai/install.sh | sh  # Linux")
        return False


def check_ollama_server():
    """Ollama 서버 실행 체크"""
    try:
        import requests
        r = requests.get("http://localhost:11434/api/version", timeout=5)
        if r.status_code == 200:
            version = r.json().get("version", "unknown")
            print_ok(f"Ollama 서버 실행 중: v{version}")
            return True
    except:
        pass

    print_fail("Ollama 서버 실행 안 됨")
    print_hint("ollama serve  # 서버 시작")
    return False


def check_qwen_model():
    """Qwen 모델 설치 체크"""
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)

    if "qwen2.5vl:7b" in result.stdout:
        print_ok("Qwen 모델 설치됨: qwen2.5vl:7b")
        return True
    elif "qwen2.5vl" in result.stdout:
        print_warn("Qwen 모델 있지만 버전 다름")
        print_hint("권장: ollama pull qwen2.5vl:7b")
        return True
    else:
        print_fail("Qwen 모델 없음")
        print_hint("ollama pull qwen2.5vl:7b  # 약 6GB, 10-30분 소요")
        return False


def check_claude_cli():
    """Claude Code CLI 체크"""
    if shutil.which("claude"):
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print_ok(f"Claude CLI 설치됨: {version}")
            return True

    print_fail("Claude Code CLI 없음")
    print_hint("npm install -g @anthropic-ai/claude-code")
    print_hint("설치 후: claude login")
    return False


def check_ffmpeg():
    """ffmpeg 설치 체크"""
    if shutil.which("ffmpeg"):
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        # 첫 줄만 추출
        version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
        print_ok(f"ffmpeg 설치됨")
        return True
    else:
        print_fail("ffmpeg 없음")
        print_hint("brew install ffmpeg  # macOS")
        print_hint("apt install ffmpeg  # Ubuntu")
        return False


def check_python_packages():
    """Python 패키지 체크"""
    # (패키지명, import명) 튜플
    required = [
        ("moviepy", "moviepy"),
        ("opencv-python", "cv2"),
        ("pydantic", "pydantic"),
        ("rich", "rich"),
        ("pyyaml", "yaml"),
        ("aiohttp", "aiohttp"),
        ("pillow", "PIL"),
        ("gtts", "gtts")
    ]

    missing = []
    for pkg_name, import_name in required:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)

    if not missing:
        print_ok(f"Python 패키지: {len(required)}개 모두 설치됨")
        return True
    else:
        print_fail(f"Python 패키지 누락: {', '.join(missing)}")
        print_hint(f"pip install {' '.join(missing)}")
        print_hint("또는: pip install -r requirements.txt")
        return False


def check_project_structure():
    """프로젝트 구조 체크"""
    required_files = [
        "main.py",
        "src/api.py",
        "src/pipeline.py",
        "src/coaching/coaching_composer.py",
        "configs/script_prompts.yaml"
    ]

    base = Path(__file__).parent
    missing = []

    for f in required_files:
        if not (base / f).exists():
            missing.append(f)

    if not missing:
        print_ok("프로젝트 구조: 정상")
        return True
    else:
        print_fail(f"파일 누락: {', '.join(missing)}")
        return False


def check_gpu():
    """GPU 체크 (선택)"""
    # NVIDIA GPU
    if shutil.which("nvidia-smi"):
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            gpu_name = result.stdout.strip()
            print_ok(f"NVIDIA GPU: {gpu_name}")
            return True

    # Apple Silicon
    import platform
    if platform.processor() == "arm" and platform.system() == "Darwin":
        print_ok("Apple Silicon: Metal 가속 사용 가능")
        return True

    print_warn("GPU 없음 (CPU로 실행, 느릴 수 있음)")
    return True  # GPU는 선택 사항


def main():
    print_header("로컬 AI 환경 체크")

    results = {}

    # 필수 체크
    print("\n📦 시스템 의존성")
    results["python"] = check_python_version()
    results["ffmpeg"] = check_ffmpeg()

    print("\n🤖 Ollama (영상 분석용)")
    results["ollama_install"] = check_ollama_installed()
    if results["ollama_install"]:
        results["ollama_server"] = check_ollama_server()
        if results["ollama_server"]:
            results["qwen_model"] = check_qwen_model()
        else:
            results["qwen_model"] = False
    else:
        results["ollama_server"] = False
        results["qwen_model"] = False

    print("\n🧠 Claude CLI (대본 생성용)")
    results["claude_cli"] = check_claude_cli()

    print("\n📚 Python 패키지")
    results["packages"] = check_python_packages()

    print("\n📁 프로젝트 구조")
    results["structure"] = check_project_structure()

    print("\n⚡ GPU (선택)")
    check_gpu()

    # 결과 요약
    print_header("결과 요약")

    essential = ["python", "ffmpeg", "ollama_install", "ollama_server",
                 "qwen_model", "claude_cli", "packages", "structure"]

    passed = sum(1 for k in essential if results.get(k, False))
    total = len(essential)

    if passed == total:
        print(f"\n{GREEN}{BOLD}🎉 모든 환경 준비 완료! ({passed}/{total}){RESET}")
        print(f"\n테스트 실행:")
        print(f"  python main.py test-move.MOV -d 10 -s action --local")
        return 0
    else:
        print(f"\n{YELLOW}{BOLD}⚠️  일부 설정 필요 ({passed}/{total}){RESET}")
        print(f"\n위의 힌트를 따라 누락된 항목을 설치하세요.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n중단됨")
        sys.exit(1)
