"""02_ros2 — ROS 2 통신 아키텍처 (노드 · 토픽 · 서비스 · 액션 전체). python3 gen_02_ros2.py"""

from archlib import Edge, Node, Zone, render

W, H = 2900, 1400
N = {}


def add(id, x, y, title, sub, kind="ros", lines=(), w=320, h=110):
    N[id] = Node(id, x, y, w, h, title, sub, kind, list(lines))


add(
    "CAM",
    80,
    80,
    "realsense2_camera",
    "/camera/color/image_raw · camera_info",
    "ext",
    ["D435i RGB 1920×1080 30 fps · 깊이 미사용"],
)
add(
    "BT",
    80,
    340,
    "box_tracker",
    "OpenCV HSV 분할 + 등속 예측 추적",
    "ctn",
    ["핸드아이 픽셀→베이스 · 검출 p95 4 ms"],
)
add(
    "LR",
    440,
    340,
    "label_reader",
    "PaddleOCR 3.7 korean · 자모 편집거리",
    "ctn",
    ["1·2단계 발행 · 3단계 서비스"],
)
add(
    "VL",
    900,
    80,
    "voice_listener",
    "VAD → POST /ai/stt → 호출어 매칭",
    "ros",
    ["정지 키워드는 호출어 없이 통과"],
)
add(
    "IP",
    1300,
    80,
    "intent_parser",
    "지름길 → /ai/intent → 허용 목록 재검증",
    "ros",
    ["command_transport ros | web_api"],
)
add(
    "SO",
    1700,
    80,
    "speech_out",
    "/voss/voice/say 큐 20 → POST /ai/tts",
    "ros",
    ["aplay S16LE 24 kHz mono"],
)
add(
    "AI",
    2100,
    80,
    "FastAPI :8000",
    "faster-whisper · OpenAI gpt-4o · tts",
    "ai",
    ["AI 컨테이너 (CUDA 12.6 GPU)"],
)
add(
    "SM",
    860,
    440,
    "sort_manager",
    "작업 상태기계 · voss_config.yaml 유일 독자",
    "core",
    [
        "IDLE·RUNNING·PICKING·RECHECK·ASKING·PAUSED·PALLETIZING",
        "준비 5항목 검사 · stop 코얼레싱 · pallet_plan 순수 함수",
    ],
    w=420,
    h=140,
)
add(
    "BS",
    1480,
    455,
    "belt_servo",
    "30 Hz 서보 v = v_belt + Kp·e",
    "ros",
    ["PREPARE→TRACK→DESCEND→GRASP→LIFT→VERIFY"],
)
add(
    "RG",
    1980,
    455,
    "robot_gateway",
    "두산 서비스 단일 직렬 큐 · servo guard",
    "ros",
    ["watchdog 200 ms · z≥78 mm · TCP 등록 검사"],
)
add(
    "DSR",
    2480,
    340,
    "두산 dsr_controller2",
    "/dsr01 · M0609 · doosan-robot2",
    "ext",
    ["speedl_stream · move_line · spline · ikin/fkin"],
)
add(
    "RG2",
    2480,
    600,
    "OnRobot RG2",
    "Modbus TCP 192.168.1.1:502 (pymodbus)",
    "hw",
    ["폭 0~110 mm · 힘 3~40 N · grip_detected"],
)
add(
    "HB",
    80,
    820,
    "hmi_bridge",
    "ROS ↔ MQTT JSON 번역 (paho-mqtt)",
    "ros",
    ["command_id 600 s 중복 억제 · retained 3종"],
)
add(
    "SL",
    560,
    820,
    "sort_logger",
    "SortResult · PalletResult → DB 1행",
    "ros",
    ["실패 → JSONL 스풀 재전송"],
)
add(
    "MQ",
    80,
    1060,
    "Mosquitto :1883",
    "voss/* · 계정별 ACL · 익명 금지",
    "broker",
    ["→ Spring Boot :8080 → SSE → React :80"],
)
add(
    "PG",
    560,
    1060,
    "PostgreSQL 16",
    "sort_log · pallet_log · session_plan",
    "db",
    ["writer voss_logger · reader voss_web"],
)

zones = [
    Zone(50, 312, 740, 178, "비전 컨테이너", "#60a5fa"),
    Zone(870, 52, 1180, 166, "음성 (호스트)", "#f5c542"),
    Zone(1450, 432, 890, 160, "로봇 (호스트)", "#f5c542"),
    Zone(50, 792, 870, 418, "사람 · 기록 (호스트)", "#f5c542"),
]

E = []


def e(pts, label, kind="topic", lab_at=None, both=False, anchor="middle", width=2.0):
    E.append(Edge(pts, label, kind, lab_at, both, width, anchor))


# 비전
e([(240, 190), (240, 340)], "R1 · /camera/color/image_raw · camera_info", lab_at=(240, 236))
e(
    [(400, 120), (420, 120), (420, 400), (440, 400)],
    "R2 · image_raw (read_label 요청 중만)",
    "ghost",
    lab_at=(420, 262),
)
e([(400, 380), (440, 380)], "R3 · /voss/vision/label_crop LabelCrop ≤5 Hz", lab_at=(420, 474))
e(
    [(240, 450), (240, 520), (860, 520)],
    "R4 · /voss/vision/box BoxTrack ~30 Hz best_effort",
    lab_at=(560, 530),
)
e([(330, 450), (330, 640), (1640, 640), (1640, 565)], "R5 · /voss/vision/box", lab_at=(1000, 640))
e([(150, 450), (150, 820)], "R6 · /voss/vision/box (≤10 Hz)", lab_at=(46, 700), anchor="start")
e(
    [(600, 450), (600, 485), (860, 485)],
    "R7 · /voss/vision/label LabelRead stage 1·2",
    lab_at=(745, 500),
)
e([(860, 470), (700, 470), (700, 450)], "R8 · srv read_label · zone_map", "srv", lab_at=(790, 468))
e(
    [(960, 440), (960, 230), (300, 230), (300, 340)],
    "R9 · /voss/sort/state SortState 2.5 Hz",
    lab_at=(630, 230),
)
# 음성
e([(1220, 135), (1300, 135)], "R10 · /voss/voice/transcript", lab_at=(1260, 58))
e(
    [(1400, 190), (1400, 330), (1130, 330), (1130, 440)],
    "R11 · /voss/voice/intent Intent",
    lab_at=(1300, 330),
)
e(
    [(1180, 440), (1180, 365), (1440, 365), (1440, 190)],
    "R12 · /voss/sort/zone_map · state",
    lab_at=(1300, 380),
)
e(
    [(1000, 440), (1000, 270), (1060, 270), (1060, 190)],
    "R13 · /voss/sort/state",
    lab_at=(1000, 340),
)
e(
    [(1240, 440), (1240, 400), (1800, 400), (1800, 190)],
    "R14 · /voss/voice/say (질문 · 되읽기 · 완료)",
    lab_at=(1520, 400),
)
e([(1620, 135), (1700, 135)], "R15 · /voss/voice/say", lab_at=(1660, 58))
e(
    [(1140, 80), (1140, 35), (1860, 35), (1860, 80)],
    "R16 · /voss/voice/say (TIMED_OUT 안내)",
    lab_at=(1500, 35),
)
e(
    [(1000, 80), (1000, 12), (2260, 12), (2260, 80)],
    "R17 · POST /ai/stt (WAV)",
    "http",
    lab_at=(2010, 12),
)
e(
    [(1560, 190), (1560, 215), (2200, 215), (2200, 190)],
    "R18 · POST /ai/intent (JSON) · GET /api/stats → Spring",
    "http",
    lab_at=(1900, 215),
)
e([(2020, 135), (2100, 135)], "R19 · POST /ai/tts (PCM)", "http", lab_at=(2060, 58))
e(
    [(980, 80), (980, 55), (40, 55), (40, 875), (80, 875)],
    "R20 · /voss/voice/status",
    lab_at=(46, 575),
    anchor="start",
)
e(
    [
        (1340, 190),
        (1340, 250),
        (1090, 250),
        (1090, 310),
        (860, 310),
        (860, 600),
        (380, 600),
        (380, 820),
    ],
    "R21 · /voss/voice/text ← · → text/reply",
    lab_at=(620, 600),
    both=True,
)
# 로봇
e(
    [(1280, 500), (1480, 500)],
    "R24 · action\ntrack_and_grasp",
    "action",
    lab_at=(1370, 500),
    width=3,
)
e([(1800, 480), (1980, 480)], "R25 · servo_cmd\nTwistStamped 30 Hz", lab_at=(1890, 480))
e([(1980, 545), (1800, 545)], "R26 · /voss/robot/pose\nPoseStamped 50 Hz (TCP)", lab_at=(1890, 585))
e(
    [(1640, 455), (1640, 432), (2100, 432), (2100, 455)],
    "R27 · srv gripper · stop",
    "srv",
    lab_at=(1880, 432),
    width=3,
)
e(
    [(1280, 540), (1420, 540), (1420, 690), (2180, 690), (2180, 565)],
    "R28 · srv move_to_zone · stop (멱등)",
    "srv",
    lab_at=(1750, 690),
    width=3,
)
e(
    [(2060, 565), (2060, 615), (1300, 615), (1300, 580)],
    "R29 · /voss/robot/pose · /voss/robot/state 2 Hz transient_local",
    lab_at=(1600, 615),
)
e(
    [(2020, 455), (2020, 300), (380, 300), (380, 340)],
    "R30 · /voss/robot/pose (촬영 시각 보간)",
    lab_at=(1150, 300),
)
e(
    [(2260, 565), (2260, 770), (330, 770), (330, 820)],
    "R31 · /voss/robot/pose · state · /dsr01/joint_states (≤20 Hz)",
    lab_at=(1300, 770),
)
e(
    [(2300, 470), (2530, 470), (2530, 450)],
    "R32 · speedl_stream\nsrv move_line·spline·ikin\nfkin·posx·move_stop",
    "srv",
    lab_at=(2390, 512),
    width=3,
)
e(
    [(2620, 450), (2620, 540), (2300, 540)],
    "R33 · /dsr01/joint_states 100 Hz\nerror · robot_disconnection",
    lab_at=(2480, 570),
)
e(
    [(2300, 555), (2360, 555), (2360, 655), (2480, 655)],
    "R34 · Modbus TCP\n(reg 0·1·2 · 267 · 268)",
    "mqtt",
    lab_at=(2360, 705),
    both=True,
)
# 사람 · 기록
e(
    [(1020, 580), (1020, 850), (880, 850)],
    "R35 · /voss/sort/result · /voss/pallet/result · srv list_placements",
    lab_at=(1020, 700),
    anchor="start",
)
e(
    [(720, 820), (720, 800), (1060, 800), (1060, 580)],
    "R36 · /voss/log/status 1 Hz",
    lab_at=(900, 800),
)
e([(560, 875), (400, 875)], "R37 · /voss/log/status", lab_at=(480, 905))
e(
    [(940, 580), (940, 940), (240, 940), (240, 930)],
    "R38 · /voss/sort/state · result · zone_map · /voss/pallet/state · result",
    lab_at=(600, 940),
)
e(
    [(300, 820), (300, 700), (900, 700), (900, 580)],
    "R39 · srv /voss/sort/command (start · stop · resume · priority · answer · reset_zone · palletize)",
    "srv",
    lab_at=(600, 700),
    width=3,
)
e(
    [(160, 930), (160, 1060)],
    "R40 · MQTT voss/state … 12종 ↓ · voss/command · voice/request · voice/text ↑",
    "mqtt",
    lab_at=(46, 1000),
    both=True,
    anchor="start",
)
e(
    [(720, 930), (720, 1060)],
    "R41 · INSERT ON CONFLICT DO NOTHING (psycopg2)",
    "sql",
    lab_at=(720, 1000),
)

legend = [
    ("ros", "ROS 2 노드 (호스트)", False),
    ("ctn", "비전 컨테이너 노드", False),
    ("core", "작업 관리자", False),
    ("ai", "AI 컨테이너", False),
    ("ext", "외부 드라이버", False),
    ("hw", "장치", False),
    ("broker", "브로커", False),
    ("db", "DB", False),
    ("topic", "토픽", True),
    ("srv", "서비스 · 액션", True),
    ("http", "HTTP", True),
    ("mqtt", "MQTT · Modbus", True),
    ("sql", "SQL", True),
    ("ghost", "요청 중만 구독", True),
]
notes = [
    "Rn 번호는 README 의 인터페이스 등록표와 같다 · 같은 방향의 여러 인터페이스는 한 선으로 묶었다 · 응답·feedback 은 호출의 역방향",
    "근거: src/*/setup.py · 각 노드 create_publisher/subscription/service/client · docs/interfaces/topics.md",
]

render(
    W,
    H,
    "VOSS ROS 2 통신 아키텍처 — 노드 10 · 외부 6 · 인터페이스 41 (레포 main 기준)",
    list(N.values()),
    zones,
    E,
    legend,
    notes,
    out="02_ros2",
)
print("ok")
