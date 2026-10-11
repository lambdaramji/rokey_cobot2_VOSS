#!/bin/bash
# 비전 컨테이너 진입점: ROS·워크스페이스 환경을 올리고, 호스트 CycloneDDS 설정이 마운트돼 있으면 그것을 쓴다.
set -e
source /opt/ros/jazzy/setup.bash
source /opt/voss_ws/install/setup.bash
# 도메인이 안 왔으면(셸·.env 둘 다 없음) 시험값 77·LOCALHOST — 운용 노드와 안 보이는 쪽으로 실패한다.
# 도메인만 왔으면 범위도 호스트 셸처럼 비워 둔다(rmw 기본 SUBNET) — 30 에 LOCALHOST 가 섞이지 않게
if [ -z "${ROS_DOMAIN_ID:-}" ]; then
  export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE="${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}"
fi
if [ -z "${ROS_AUTOMATIC_DISCOVERY_RANGE:-}" ]; then
  unset ROS_AUTOMATIC_DISCOVERY_RANGE
fi
if [ -f /etc/voss/cyclonedds.xml ] && [ -s /etc/voss/cyclonedds.xml ]; then
  export CYCLONEDDS_URI=file:///etc/voss/cyclonedds.xml
fi
echo "[voss-vision] ROS_DOMAIN_ID=${ROS_DOMAIN_ID} RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-(기본 SUBNET)} RMW=${RMW_IMPLEMENTATION} CYCLONEDDS_URI=${CYCLONEDDS_URI:-(기본)} config=${VOSS_CONFIG_DIR}"
exec "$@"
