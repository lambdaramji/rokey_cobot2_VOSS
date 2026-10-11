#!/bin/bash
# 비전 컨테이너 진입점: ROS·워크스페이스 환경을 올리고, 호스트 CycloneDDS 설정이 마운트돼 있으면 그것을 쓴다.
set -e
source /opt/ros/jazzy/setup.bash
source /opt/voss_ws/install/setup.bash
if [ -f /etc/voss/cyclonedds.xml ] && [ -s /etc/voss/cyclonedds.xml ]; then
  export CYCLONEDDS_URI=file:///etc/voss/cyclonedds.xml
fi
echo "[voss-vision] ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0} RMW=${RMW_IMPLEMENTATION} CYCLONEDDS_URI=${CYCLONEDDS_URI:-(기본)} config=${VOSS_CONFIG_DIR}"
exec "$@"
