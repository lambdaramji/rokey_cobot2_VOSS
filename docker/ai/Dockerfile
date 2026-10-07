# VOSS AI 서비스 (FastAPI + faster-whisper + OpenAI).
# 입력/출력 계약: docs/interfaces/web_api.md
# ADR-0006에 맞춰 Python 3.12를 사용하고, PEP 668 충돌을 피하려고 venv를 사용한다.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        ca-certificates \
    && python3 -m venv /opt/venv \
    && python -m pip install --upgrade pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .

# ADR-0006의 Python 3.12와 실제 컨테이너 환경이 어긋나면 빌드 단계에서 바로 실패시킨다.
RUN python --version \
    && python -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version" \
    && python -m pip install -r requirements.txt

COPY app ./app

# FastAPI는 음성 ROS 노드만 로컬에서 호출한다.
# Nginx로 노출하지 않는다 (ADR-0006, web_api.md).
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
