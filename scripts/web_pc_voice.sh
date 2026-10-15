#!/usr/bin/env bash
# Web PC 마이크/STT/LLM intent/TTS와 웹 음성 상태 브리지.
set -eo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source "$repo_dir/install/setup.bash"
set -u
export ROS_DOMAIN_ID=30
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
nodes_pc_ip="${VOSS_NODES_PC_IP:-}"
if [ -z "$nodes_pc_ip" ]; then
  echo 'VOSS_NODES_PC_IP를 현장 Nodes PC 주소로 설정하세요.' >&2
  exit 1
fi
if [[ ! "$nodes_pc_ip" =~ ^[0-9.]+$ ]]; then
  echo 'VOSS_NODES_PC_IP는 IPv4 주소여야 합니다.' >&2
  exit 1
fi
network_interface="$(ip -o -4 route get "$nodes_pc_ip" | awk '{for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')"
if [[ ! "$network_interface" =~ ^[[:alnum:]_.-]+$ ]]; then
  echo 'Nodes PC로 연결할 Web PC 네트워크 인터페이스를 찾지 못했습니다.' >&2
  exit 1
fi
log_dir="$(mktemp -d /tmp/voss-web-voice.XXXXXX)"
cat >"$log_dir/cyclonedds.xml" <<XML
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain id="any">
    <General>
      <Interfaces><NetworkInterface name="$network_interface"/></Interfaces>
      <AllowMulticast>true</AllowMulticast>
    </General>
    <Discovery><Peers><Peer Address="$nodes_pc_ip"/></Peers></Discovery>
  </Domain>
</CycloneDDS>
XML
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$log_dir/cyclonedds.xml"
unset ROS_STATIC_PEERS
export PYTHONUNBUFFERED=1

visible_nodes="$(ros2 node list --no-daemon --spin-time 3)"
if printf '%s\n' "$visible_nodes" | grep -Eq '^/(voice_listener|intent_parser|speech_out)$'; then
  echo '음성 노드가 이미 보입니다. 중복 실행을 막기 위해 종료합니다.' >&2
  exit 1
fi
if pgrep -u "$(id -u)" -f '^/usr/bin/python3 .*/voss_hmi/hmi_bridge --ros-args -r __node:=web_voice_status_bridge' >/dev/null; then
  echo '기존 Web PC 음성 상태 브리지 프로세스가 있습니다. 종료한 뒤 다시 실행하세요.' >&2
  exit 1
fi
curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:8000/ai/health >/dev/null
curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:8080/api/sessions/current >/dev/null
touch "$log_dir/status.log"
voice_bin="$(ros2 pkg prefix voss_voice)/lib/voss_voice"
bridge_pid=''
if ! printf '%s\n' "$visible_nodes" | grep -qx '/web_voice_status_bridge'; then
  # 비밀번호는 명령 인자나 로그에 남기지 않고 브리지 프로세스에만 전달한다.
  password="$(python3 - "$repo_dir/deploy/node/.env" <<'PY'
import pathlib
import sys

for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line.startswith("VOSS_MQTT_BRIDGE_PASSWORD="):
        value = line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        print(value, end="")
        break
PY
)"
  if [ -z "$password" ]; then
    echo 'deploy/node/.env에 VOSS_MQTT_BRIDGE_PASSWORD가 없습니다.' >&2
    exit 1
  fi
  (
    export VOSS_MQTT_PREVIEW_USERNAME=bridge
    export VOSS_MQTT_PREVIEW_PASSWORD="$password"
    exec "$(ros2 pkg prefix voss_hmi)/lib/voss_hmi/hmi_bridge" --ros-args \
      -r __node:=web_voice_status_bridge -p voice_status_only:=true \
      -p local_text_enabled:=true
  ) >"$log_dir/status.log" 2>&1 &
  bridge_pid=$!
  unset password
fi
"$voice_bin/speech_out" >"$log_dir/tts.log" 2>&1 &
tts_pid=$!
"$voice_bin/intent_parser" --ros-args -p ai_base:=http://127.0.0.1:8000 \
  -p api_base:=http://127.0.0.1:8080 -p command_transport:=web_api \
  -p web_context_stream:=true \
  >"$log_dir/intent.log" 2>&1 &
parser_pid=$!
"$voice_bin/voice_listener" --ros-args -p mode:=mic -p require_wake:=true \
  -p wake_window_s:=10.0 -p end_silence_ms:=350 >"$log_dir/mic.log" 2>&1 &
mic_pid=$!
cleanup() {
  kill "$mic_pid" "$parser_pid" "$tts_pid" ${bridge_pid:+"$bridge_pid"} 2>/dev/null || true
  wait "$mic_pid" "$parser_pid" "$tts_pid" ${bridge_pid:+"$bridge_pid"} 2>/dev/null || true
}
trap cleanup EXIT
sleep 3
if ! kill -0 "$mic_pid" "$parser_pid" "$tts_pid" 2>/dev/null \
    || ! grep -q 'voice_listener: mic 모드' "$log_dir/mic.log"; then
  echo "음성 노드 또는 Web PC 마이크 시작 실패. 로그: $log_dir" >&2
  exit 1
fi
if [ -n "$bridge_pid" ]; then
  for _ in 1 2 3 4 5; do
    grep -q 'MQTT connected' "$log_dir/status.log" && break
    kill -0 "$bridge_pid" 2>/dev/null || break
    sleep 1
  done
  if ! grep -q 'MQTT connected' "$log_dir/status.log"; then
    echo "웹 음성 상태 MQTT 연결 실패. 로그: $log_dir/status.log" >&2
    exit 1
  fi
fi
echo "음성 로그: $log_dir (Ctrl+C로 종료)"
tail -n 10 -F "$log_dir/mic.log" "$log_dir/intent.log" "$log_dir/tts.log" "$log_dir/status.log"
