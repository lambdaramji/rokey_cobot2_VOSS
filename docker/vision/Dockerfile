# syntax=docker/dockerfile:1
# 비전 컨테이너 (T22 #31, 남현지) — box_tracker(OpenCV 분할, ADR-0011 — GPU 불필요) + label_reader(PaddleOCR).
# 빌드 context 는 레포 루트(compose.yml 이 정한다). 실행은 사람이 한다(docker/README.md).
#   CPU (개인 PC):  docker compose -f docker/vision/compose.yml build
#   GPU (공용 PC):  docker compose -f docker/vision/compose.yml -f docker/vision/compose.gpu.yml build
#   시험 이미지:     docker build -f docker/vision/Dockerfile --target test -t voss-vision:test .
# OCR 모델 가중치는 이미지에 넣지 않는다 — 첫 실행 때 받아 paddlex-cache 볼륨에 둔다(CLAUDE.md 규칙 8).

ARG ROS_IMAGE=ros:jazzy-ros-base-noble
FROM ${ROS_IMAGE} AS runtime

# cpu | gpu. gpu 는 CUDA 12.6 빌드 휠(CUDA 런타임·cuDNN 을 pip 의존성으로 함께 받는다) — 호스트 드라이버만 있으면 된다
ARG OCR_DEVICE=cpu
# 공용 PC 호스트 venv(~/.venvs/voss_ocr, G0·G1)와 같은 버전
ARG PADDLE_VERSION=3.3.1
ARG PADDLEOCR_VERSION=3.7.0
ARG PADDLE_GPU_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cu126/

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# box_tracker 는 시스템 python(apt numpy·opencv). rosbag2 mcap 플러그인은 playback 용
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-rosbag2-storage-mcap \
        python3-numpy python3-opencv python3-yaml \
        python3-venv python3-pip python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

# label_reader 만 PaddleOCR venv 로 띄운다(호스트와 같은 방식, --system-site-packages 로 rclpy 를 같이 쓴다)
RUN python3 -m venv --system-site-packages /opt/voss_ocr \
    && if [ "${OCR_DEVICE}" = "gpu" ]; then \
         /opt/voss_ocr/bin/pip install --no-cache-dir "paddlepaddle-gpu==${PADDLE_VERSION}" -i "${PADDLE_GPU_INDEX}"; \
       else \
         /opt/voss_ocr/bin/pip install --no-cache-dir "paddlepaddle==${PADDLE_VERSION}"; \
       fi \
    && /opt/voss_ocr/bin/pip install --no-cache-dir "paddleocr==${PADDLEOCR_VERSION}"

WORKDIR /opt/voss_ws
COPY src/voss_msgs src/voss_msgs
COPY src/voss_vision src/voss_vision
RUN source /opt/ros/jazzy/setup.bash \
    && colcon build --packages-select voss_msgs voss_vision --event-handlers console_direct- \
    && rm -rf build log

# 빌드 때 바로 확인: 두 노드가 쓰는 모듈이 각자의 python 에서 import 된다
RUN source /opt/ros/jazzy/setup.bash && source install/setup.bash \
    && python3 -c "import voss_vision.box_tracker, voss_vision.box_detect; from voss_msgs.msg import BoxTrack; print('box_tracker import OK')" \
    && /opt/voss_ocr/bin/python -c "import paddle, paddleocr, voss_vision.label_reader; print('label_reader import OK, paddle', paddle.__version__, 'cuda', paddle.device.is_compiled_with_cuda())"

COPY docker/vision/entrypoint.sh /entrypoint.sh
# config/ 는 읽기 전용 마운트(compose), OCR 은 venv python 으로(label_reader.launch.py 의 python 인자 기본값)
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    VOSS_CONFIG_DIR=/opt/voss/config \
    VOSS_OCR_PYTHON=/opt/voss_ocr/bin/python
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]

# 시험 이미지: 컨테이너 안에서 voss_vision pytest (OCR 시험이 paddle 을 쓰므로 venv python 으로)
FROM runtime AS test
RUN /opt/voss_ocr/bin/pip install --no-cache-dir pytest \
    && source /opt/ros/jazzy/setup.bash && source install/setup.bash \
    && /opt/voss_ocr/bin/python -m pytest -q -p no:cacheprovider src/voss_vision/test
