# VOSS AI 서비스 (FastAPI + faster-whisper + LangChain/OpenAI). ADR-0006.
# Ubuntu 24.04 → Python 3.12 (ADR-0006 기술스택과 같은 버전).
# GPU: faster-whisper(CTranslate2 4.x) 가 쓰는 CUDA 12 / cuDNN 9 런타임 이미지.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
# Ubuntu 24.04 는 시스템 pip 설치를 막는다(PEP 668) → 가상환경에 설치한다
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
# 127.0.0.1 에만 바인드 — 음성 ROS 노드(호스트)만 부른다. Nginx 로 노출하지 않는다.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
