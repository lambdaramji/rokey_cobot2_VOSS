# VOSS AI 서비스 (FastAPI + faster-whisper + OpenAI). ADR-0006.
# GPU: faster-whisper(CTranslate2) 가 쓰는 CUDA 12 / cuDNN 9 런타임 이미지.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY app ./app
# 127.0.0.1 에만 바인드 — 음성 ROS 노드(호스트)만 부른다. Nginx 로 노출하지 않는다.
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
