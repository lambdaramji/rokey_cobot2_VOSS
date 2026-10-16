"""01_system — 시스템 배포 아키텍처 (PC · 컨테이너 · 호스트 프로세스 · 로봇 셀 · 네트워크). python3 gen_01_system.py"""

from archlib import Edge, Node, Zone, render

W, H = 2420, 1560
N = {}


def add(id, x, y, title, sub, kind="ros", lines=(), w=290, h=130):
    N[id] = Node(id, x, y, w, h, title, sub, kind, list(lines))


# 컨테이너 5종
add(
    "VC",
    90,
    100,
    "vision",
    "box_tracker · label_reader",
    "ctn",
    [
        "ros:jazzy-ros-base-noble",
        "PaddleOCR 3.7 · paddle 3.3.1 (cu126)",
        "compose.gpu.yml → OCR GPU",
    ],
)
add(
    "AI",
    360,
    100,
    "ai (GPU)",
    "FastAPI · uvicorn :8000",
    "ai",
    [
        "nvidia/cuda:12.6.3 · Python 3.12",
        "faster-whisper small (fp16)",
        "LangChain + OpenAI gpt-4o · tts",
    ],
)
add(
    "MQ",
    630,
    100,
    "mqtt",
    "Mosquitto 2 · 127.0.0.1:1883",
    "broker",
    ["allow_anonymous false · ACL", "web · bridge · debug · voice_*", "persistence · retained 3종"],
)
add(
    "PG",
    900,
    100,
    "db",
    "PostgreSQL 16 · 127.0.0.1:5432",
    "db",
    [
        "sort_log · pallet_log · session_plan",
        "voss_logger INSERT · voss_web SELECT",
        "/var/lib/voss/pgdata 볼륨",
    ],
)
add(
    "SB",
    1170,
    100,
    "web / backend",
    "Spring Boot 3.5 · Java 21 · :8080",
    "front",
    [
        "REST /api · SSE /api/stream",
        "spring-integration-mqtt (Paho)",
        "JDBC 읽기 · session_plan 쓰기",
    ],
)
add(
    "NG",
    1440,
    100,
    "web / frontend",
    "Nginx 1.27 · :80",
    "front",
    [
        "React 19 · Vite 6 · TypeScript 5.7",
        "/api → 8080 · /camera/* → 8091/8092",
        "원격 브라우저는 STOP 만",
    ],
)
# 호스트 프로세스
add(
    "CAMN",
    90,
    450,
    "realsense2_camera",
    "color 1920×1080×30 · 노출 6 ms",
    "ros",
    ["depth/infra/imu off · WB 4600", "camera_preview :8091 · usb :8092"],
)
add(
    "SM",
    360,
    450,
    "sort_manager",
    "작업 상태기계 · 준비 5항목 검사",
    "core",
    ["voss_config.yaml 유일 독자", "pallet_fsm · pallet_plan · readiness"],
)
add(
    "VO",
    630,
    450,
    "voss_voice 3노드",
    "voice_listener · intent_parser · speech_out",
    "ros",
    ["sounddevice 16 kHz · aplay 24 kHz", "HTTP → ai 컨테이너"],
)
add(
    "HB",
    900,
    450,
    "hmi_bridge",
    "ROS ↔ MQTT JSON · paho-mqtt",
    "ros",
    ["구독 11 토픽 → 발행 12 MQTT", "voss/command → srv sort/command"],
)
add(
    "SL",
    1170,
    450,
    "sort_logger",
    "SortResult · PalletResult → DB",
    "ros",
    ["psycopg2 · 스풀 /var/lib/voss/spool", "/voss/log/status 1 Hz"],
)
add(
    "CFG",
    1440,
    450,
    "config/ · 레포 밖 실값",
    "voss_config.yaml · hand_eye.yaml",
    "db",
    ["belt_homography.yaml", "~/voss_ws/config/belt_servo_real.yaml", "deploy/node/.env (비밀값)"],
)
add(
    "BR",
    90,
    700,
    "두산 브링업",
    "m0609_rg2_bringup · dsr_controller2",
    "ext",
    ["doosan-robot2 (레포 밖 ws_cobot_pjt)", "mode:=real host:=$VOSS_ROBOT_HOST :12345"],
)
add(
    "RG",
    360,
    700,
    "robot_gateway",
    "두산 서비스 단일 직렬 큐",
    "ros",
    ["servo guard · watchdog 200 ms", "pose 50 Hz (joint_states + fkin)", "RG2 pymodbus 직접"],
)
add(
    "BS",
    630,
    700,
    "belt_servo",
    "30 Hz 폐루프 비주얼 서보",
    "ros",
    [
        "v = v_belt + Kp·e · 사다리꼴 z",
        "action track_and_grasp 서버",
        "JSONL 틱·시도 로그 data/servo",
    ],
)
add(
    "UP",
    900,
    700,
    "scripts/voss_up.py",
    "T1 브링업 → T2 gateway → T3 카메라",
    "ext",
    [
        "→ T4 logger → T5 비전 → T7 servo",
        "→ T8 manager → 음성 3 → hmi_bridge",
        "준비 로그 대기 · 역순 종료",
    ],
)
add(
    "SIM",
    1170,
    700,
    "검증 3단계",
    "dry_run + 녹화 재생 (개인 PC)",
    "ext",
    ["두산 에뮬레이터 virtual_node", "실기 (공용 PC, 비상정지 옆)", "DOMAIN 30 에선 dry_run 거부"],
)
add(
    "CI",
    1440,
    700,
    "CI · 규칙",
    ".github/workflows/ci.yml",
    "ext",
    [
        "ruff → colcon build → test",
        "voss_msgs·config 변경 시 docs 강제",
        "ADR 16 · docs/interfaces 계약 우선",
    ],
)
# 로봇 셀
add(
    "CTRL",
    90,
    1060,
    "두산 컨트롤러",
    "M0609 · TCP :12345",
    "hw",
    ["유선 전용 서브넷", "툴·TCP 등록은 펜던트"],
)
add(
    "ROBOT",
    360,
    1060,
    "두산 M0609",
    "6축 · 가반 6 kg · 도달 900 mm",
    "hw",
    ["speedl_stream TCP 속도 제어", "MoveToZone 300 mm/s · 900 mm/s²"],
)
add(
    "RG2",
    630,
    1060,
    "OnRobot RG2",
    "Compute Box 192.168.1.1:502",
    "hw",
    ["폭 0~110 mm · 힘 3~40 N", "31 mm 파지 · 39 mm · 14 N"],
)
add(
    "D435",
    900,
    1060,
    "RealSense D435i",
    "손목 Eye-in-Hand · USB 3.0",
    "hw",
    ["RGB 만 (깊이 미사용)", "핸드아이 PARK + 터치 보정"],
)
add(
    "BELT",
    1170,
    1060,
    "탁상 컨베이어",
    "벨트 1040×70 mm · 약 4.6 cm/s",
    "hw",
    ["스텝모터 + Arduino Uno", "시리얼 9600 (속도 설정)"],
)
add(
    "C270",
    1440,
    1060,
    "Logitech C270 + 작업대",
    "USB 웹캠 · 120×65 cm 작업대",
    "hw",
    ["A·B·C 3×2×2 · 재확인·보류 2×1", "팔레트 4×2×2 · 박스 46×31×27 mm"],
)
# Web PC · 외부
add(
    "BROW",
    2110,
    450,
    "브라우저 HMI",
    "http://<Nodes PC>:80",
    "front",
    ["운전·분류·답변·팔레트 버튼", "3D 팔레트 · 카메라 · 음성 표시등"],
    w=270,
)
add(
    "WV",
    2110,
    700,
    "scripts/web_pc_voice.sh",
    "마이크·스피커 음성 노드 (ROS, DOMAIN 30)",
    "ros",
    ["command_transport=web_api", "hmi_bridge voice_status_only", "SSH -L 8000·8080·1883·5432"],
    w=270,
)
add(
    "OAI",
    2110,
    100,
    "OpenAI API",
    "gpt-4o intent · gpt-4o-mini-tts",
    "ext",
    ["별도 Wi-Fi NIC", "temperature 0 · 3 s timeout"],
    w=270,
)

zones = [
    Zone(
        60,
        60,
        1900,
        270,
        "공용 PC (Nodes PC) — Docker 컨테이너 5종 · network_mode: host · 같은 ROS_DOMAIN_ID 30",
        "#60a5fa",
    ),
    Zone(
        60,
        410,
        1900,
        560,
        "공용 PC (Nodes PC) — 호스트 프로세스 · Ubuntu 24.04 · ROS 2 Jazzy · rmw_cyclonedds_cpp · Python 3.12",
        "#f5c542",
    ),
    Zone(
        60,
        1020,
        1900,
        250,
        "로봇 셀 — 로봇 컨트롤러 유선 전용 서브넷 · 카메라 USB 3.0 · 아두이노 시리얼",
        "#fb923c",
    ),
    Zone(2080, 410, 320, 560, "Web PC (선택) — Ubuntu 24.04", "#a78bfa"),
]

E = []


def e(pts, label, kind="topic", lab_at=None, both=False, anchor="middle", width=2.0):
    E.append(Edge(pts, label, kind, lab_at, both, width, anchor))


# 컨테이너 ↔ 호스트 (세로)
e(
    [(235, 230), (235, 450)],
    "S1 · DDS /camera/color/image_raw ↑ · /voss/vision/box · label ↓",
    lab_at=(242, 370),
    both=True,
    anchor="start",
)
e(
    [(380, 230), (380, 300), (545, 300), (545, 450)],
    "S2 · /voss/vision/box · label → sort_manager (DDS)",
    lab_at=(552, 296),
    anchor="start",
)
e(
    [(855, 230), (855, 450)],
    "S5 · HTTP /ai/stt · intent · tts (:8000)",
    "http",
    lab_at=(862, 352),
    anchor="start",
)
e(
    [(1165, 230), (1165, 450)],
    "S6 · MQTT voss/* 발행 12 · 구독 3 (QoS 0/1 · retained 3종)",
    "mqtt",
    lab_at=(1172, 378),
    both=True,
    anchor="start",
)
e(
    [(1475, 230), (1475, 450)],
    "S7 · psycopg2 INSERT sort_log · pallet_log",
    "sql",
    lab_at=(1482, 352),
    anchor="start",
)
# 컨테이너 사이
e(
    [(1600, 230), (1600, 300), (1340, 300), (1340, 230)],
    "S8 · MQTT JSON ↔ (Paho, web 계정)",
    "mqtt",
    both=True,
    lab_at=(1470, 300),
)
e(
    [(1310, 165), (1330, 165)],
    "S9 · JDBC SELECT · session_plan (voss_web)",
    "sql",
    lab_at=(1320, 258),
)
e([(1620, 165), (1640, 165)], "S10 · proxy /api · SSE", "http", lab_at=(1630, 258))
e(
    [(1700, 230), (1700, 340), (320, 340), (320, 450)],
    "S11 · /camera/gripper → :8091 · /camera/usb → :8092 (Nginx proxy)",
    "http",
    lab_at=(1020, 324),
)
e([(690, 165), (710, 165)], "S12 · HTTP /ai (voice)", "http", lab_at=(700, 258))
# 호스트 내부 (가로)
e([(710, 515), (690, 515)], "S13 · /voss/voice/intent · say", lab_at=(770, 436))
e([(1000, 515), (1020, 515)], "S14 · /voss/sort/* · pallet/*", lab_at=(1090, 436))
e([(1310, 515), (1330, 515)], "S15 · /voss/sort/result", lab_at=(1400, 436))
e(
    [(545, 580), (545, 640), (855, 640), (855, 700)],
    "S16 · action track_and_grasp",
    "srv",
    lab_at=(700, 668),
    width=3,
)
e(
    [(470, 580), (470, 700)],
    "S17 · srv move_to_zone · stop ↓ · pose · state ↑",
    "srv",
    lab_at=(477, 612),
    width=3,
    anchor="start",
    both=True,
)
e([(690, 765), (710, 765)], "S18 · servo_cmd 30 Hz · pose 50 Hz", lab_at=(770, 860), both=True)
e(
    [(380, 765), (400, 765)],
    "S19 · DDS speedl_stream · dsr 서비스",
    "srv",
    lab_at=(350, 860),
    width=3,
    both=True,
)
e(
    [(1785, 580), (1785, 640), (1490, 640), (1490, 700)],
    "S20 · 설정 읽기 (config_dir · launch 인자)",
    "ghost",
    lab_at=(1600, 640),
)
# 호스트 ↔ 셀
e(
    [(235, 830), (235, 1060)],
    "S21 · 유선 TCP :12345 (dsr_controller2 ↔ 컨트롤러)",
    "bus",
    lab_at=(222, 980),
    anchor="start",
    both=True,
)
e([(380, 1125), (400, 1125)], "S22", "bus", lab_at=(350, 1215), both=True)
e([(690, 1125), (710, 1125)], "S23 · 플랜지", "bus", lab_at=(770, 1215))
e(
    [(470, 830), (470, 900), (855, 900), (855, 1060)],
    "S24 · Modbus TCP 192.168.1.1:502 (pymodbus, unit 65)",
    "mqtt",
    lab_at=(700, 900),
    both=True,
)
e(
    [(1165, 1060), (1165, 920), (170, 920), (170, 580)],
    "S25 · USB 3.0 → realsense2_camera",
    "bus",
    lab_at=(700, 920),
)
e(
    [(1785, 1060), (1785, 985), (280, 985), (280, 580)],
    "S26 · USB → usb_camera_preview :8092",
    "bus",
    lab_at=(1020, 985),
)
e(
    [(1475, 1060), (1475, 1010), (1180, 1010), (1180, 830)],
    "S27 · 시리얼 9600 (tools/arduino, 속도 설정만)",
    "ghost",
    lab_at=(1400, 1010),
)
e([(1000, 1125), (1020, 1125)], "S28 · 손목 장착", "bus", lab_at=(1090, 1215))
# Web PC · 외부
e([(1930, 165), (2110, 165)], "S29 · HTTPS\n(별도 NIC)", "http", lab_at=(2020, 110))
e([(1930, 515), (2110, 515)], "S30 · HTTP :80\n(원격 STOP 만)", "http", lab_at=(2020, 470))
e(
    [(1930, 765), (2110, 765)],
    "S31 · SSH -L 8000·8080\n1883·5432 → REST · /ai",
    "http",
    lab_at=(2020, 720),
    both=True,
)

legend = [
    ("ros", "호스트 ROS 2 노드", False),
    ("core", "작업 관리자", False),
    ("ctn", "비전 컨테이너", False),
    ("ai", "AI 컨테이너", False),
    ("broker", "브로커", False),
    ("db", "DB · 설정 파일", False),
    ("front", "웹", False),
    ("ext", "외부 · 스크립트", False),
    ("hw", "장치", False),
    ("topic", "ROS 토픽 (DDS)", True),
    ("srv", "서비스 · 액션", True),
    ("http", "HTTP · SSE", True),
    ("mqtt", "MQTT · Modbus", True),
    ("sql", "SQL", True),
    ("bus", "유선 · USB", True),
    ("ghost", "시리얼", True),
]
notes = [
    "공식 배치는 공용 PC 한 대(ADR-0006). Web PC 는 비구동 통합 시험·시연 보조용(SSH 포트 포워딩, deployment_two_pc_trial.md)",
    "근거: docker/*/compose.yml · src/voss_bringup/launch/voss_host.launch.py · scripts/voss_up.py · docs/architecture.md",
]

render(
    W,
    H,
    "VOSS 시스템 배포 아키텍처 — 공용 PC(호스트 프로세스 + 컨테이너 5종) · 로봇 셀 · Web PC (레포 main 기준)",
    list(N.values()),
    zones,
    E,
    legend,
    notes,
    out="01_system",
)
print("ok")
