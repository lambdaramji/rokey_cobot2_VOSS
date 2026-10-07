#!/usr/bin/env bash
# 10/06 실측 #2(컨트롤러·드라이버 버전) + #5 보조(PC 사양) — 읽기 전용 환경 보고서.
# 로봇·그리퍼를 움직이지 않는다. 핑과 TCP 포트 연결 확인만 한다.
#
#   bash env_report.sh            # 화면 출력 + ~/voss_ws/measure_1006_data/env_<호스트>.md 저장
#
# DRCF 버전은 브링업 로그의 "DRCF version = ..." 줄에서 읽는다. 실기 브링업을 한 번 띄운 뒤 실행한다.
set -u
OUT_DIR="${VOSS_MEASURE_DIR:-$HOME/voss_ws/measure_1006_data}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/env_$(hostname).md"
ROBOT_IP="${ROBOT_IP:-192.168.1.100}"
GRIPPER_IP="${GRIPPER_IP:-192.168.1.1}"

port_open() { timeout 2 bash -c "</dev/tcp/$1/$2" 2>/dev/null && echo "열림" || echo "닫힘/응답 없음"; }
git_rev() { git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "(git 아님)"; return; }
  git -C "$1" log -1 --format='%h %ad %s' --date=short; git -C "$1" remote get-url origin 2>/dev/null; }
find_src() { find "$HOME" -maxdepth 4 -type d -name "$1" -path '*/src/*' 2>/dev/null | head -3; }

{
echo "# 환경 보고서 — $(hostname) — $(date '+%F %T')"
echo
echo "## OS · ROS"
echo '```'
grep PRETTY_NAME /etc/os-release | cut -d= -f2
echo "kernel $(uname -r)"
echo "ROS_DISTRO=${ROS_DISTRO:-미설정}  RMW=${RMW_IMPLEMENTATION:-미설정}  ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-미설정}"
echo "CYCLONEDDS_URI=${CYCLONEDDS_URI:-미설정}"
if [ -n "${CYCLONEDDS_URI:-}" ]; then
  f="${CYCLONEDDS_URI#file://}"
  [ -f "$f" ] && echo "  사용 인터페이스: $(grep -o 'NetworkInterface name="[^"]*"' "$f" | cut -d'"' -f2 | tr '\n' ' ')"
  ifs=$( [ -f "$f" ] && grep -o 'NetworkInterface name="[^"]*"' "$f" | cut -d'"' -f2 | sort -u | tr '\n' ' ')
  [ "$ifs" = "lo " ] && \
    echo "  ⚠ lo 만 쓴다: 다른 PC(공용 PC·팀원)와 ROS 토픽이 안 보인다. 한 PC 안에서만 돌릴 때만 괜찮다"
fi
echo '```'
echo
echo "## 두산 컨트롤러 (브링업 로그)"
echo '```'
# real 모드 로그 중 가장 최근 것을 우선 (없으면 아무 브링업 로그)
F=$(grep -rl "DRCF version" "$HOME/.ros/log" 2>/dev/null | xargs -r grep -l "mode : real" 2>/dev/null | xargs -r ls -t 2>/dev/null | head -1)
[ -z "$F" ] && F=$(grep -rl "DRCF version" "$HOME/.ros/log" 2>/dev/null | xargs -r ls -t 2>/dev/null | head -1) && echo "(real 로그 없음 — 아래는 virtual 일 수 있다)"
if [ -n "$F" ]; then echo "로그: $F  (날짜·로봇이 오늘 것인지 확인)"; grep -h -o -E "(DRCF|DRFL) version = .*" "$F" | tail -2
else echo "로그에 없음 → 실기 브링업 후 다시 실행. 또는 브링업 터미널에서 'DRCF version' 줄을 직접 옮긴다"; fi
echo '```'
echo
echo "## 드라이버 소스 커밋"
echo '```'
for p in doosan-robot2 m0609_rg2_bringup onrobot-ros2 rokey_cobot2_VOSS; do
  for d in $(find_src "$p"); do echo "[$p] $d"; git_rev "$d" | sed 's/^/  /'; done
done
dpkg -l 2>/dev/null | awk '/ros-jazzy-realsense2-camera |ros-jazzy-librealsense2 /{print $2, $3}'
python3 -c "import pymodbus;print('pymodbus', pymodbus.__version__)" 2>/dev/null || echo "pymodbus 없음"
python3 -c "import serial;print('pyserial', serial.__version__)" 2>/dev/null || echo "pyserial 없음"
echo '```'
echo
echo "## PC 사양"
echo '```'
grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //'
echo "코어 $(nproc), RAM $(free -h | awk '/Mem:/{print $2}')"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
  echo "nvidia-smi 없음 (GPU 없음 또는 드라이버 미설치)"; lspci 2>/dev/null | grep -i -E 'vga|3d' | sed 's/^/  /'
fi
docker --version 2>/dev/null || echo "docker 없음"
command -v nvidia-ctk >/dev/null && echo "nvidia-container-toolkit 있음" || echo "nvidia-container-toolkit 없음"
df -h "$HOME" | awk 'NR==2{print "디스크(홈) 남은 공간 " $4}'
echo '```'
echo
echo "## USB (5000M 이상 = USB 3.x 루트 허브)"
echo '```'
lsusb -t 2>/dev/null | grep -E 'root_hub|Video|ACM|ttyUSB|Class=Communications|Vendor Specific'
lsusb 2>/dev/null | grep -i -E 'intel.*realsense|8086:0b3a|arduino|2341:|1a86:|ch340|ftdi|0403:'
echo '```'
echo
echo "## 네트워크"
echo '```'
ip -br addr | grep -v -E '^(lo|docker|veth|br-)'
echo "로봇 $ROBOT_IP 로 가는 경로: $(ip route get "$ROBOT_IP" 2>/dev/null | head -1)"
echo "핑 로봇 $ROBOT_IP: $(ping -c 2 -W 1 "$ROBOT_IP" >/dev/null 2>&1 && echo OK || echo 실패)   포트 12345: $(port_open "$ROBOT_IP" 12345)"
echo "핑 그리퍼 $GRIPPER_IP: $(ping -c 2 -W 1 "$GRIPPER_IP" >/dev/null 2>&1 && echo OK || echo 실패)   포트 502: $(port_open "$GRIPPER_IP" 502)"
echo '```'
echo
echo "## 시리얼 (아두이노)"
echo '```'
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "시리얼 장치 없음 (아두이노 USB 연결 확인)"
id -nG | tr ' ' '\n' | grep -qx dialout && echo "dialout 그룹: 있음" || \
  echo "⚠ dialout 그룹 없음 → sudo usermod -aG dialout \$USER 후 로그아웃/로그인 (또는 재부팅)"
echo '```'
} | tee "$OUT"
echo
echo "저장: $OUT"
