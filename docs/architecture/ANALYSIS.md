# VOSS 아키텍처 분석

기준: `webpc-freezing-16thOct`, commit `70463ef435b50b45d243823b6f7318789728d786`. 도면의 근거는 이 커밋의 코드·DDL·설정이며, 문서상 목표만으로 실행 연결을 추가하지 않았다. 이 결과물은 코드의 **구성 및 가능한 경로**를 보여 주며, 현장 장비의 현재 연결 상태를 뜻하지 않는다.

## 2026-10-16 실제 PC 배치 근거

도면의 노란 경계는 **프로세스가 실제 실행되는 물리 PC**를 나타낸다. 운영자가 어느 PC에서 SSH 명령을 입력했는지는 실행 위치와 구분했다. 이 배치는 사용자가 제공한 `10/16 main fe11ded` Robot PC 실행 기록과 [2026-10-14 Web PC Runbook](https://app.notion.com/p/3f9fe8937ec38184a945ced25f041bf1)을 기준으로 한다. 런북의 `Nodes PC`/`공용 PC`는 여기서 **Robot PC (`ms-03`)**로 표기한다. 도면의 코드 근거 커밋 `70463ef`와 실행 기록의 `fe11ded`는 다르므로, 이 절은 해당 실행 기록의 배치를 설명하며 현재 시점의 실행 상태를 재관측했다는 뜻은 아니다.

| 물리 PC | 실행 프로세스/서비스 | 명령 실행 위치와 통신 |
|---|---|---|
| Web PC (`runo-ros`) | PostgreSQL, Mosquitto, FastAPI AI, Spring Boot, Nginx/React, `voice_listener`, `intent_parser`, `speech_out`, `web_voice_status_bridge` | Docker 서비스와 `scripts/web_pc_voice.sh` 실행. Web PC에서 Robot PC로 SSH `-R` 1883/8000/5432, 카메라용 `-L` 8091/8092 터널 실행 |
| Robot PC (`ms-03`) | Doosan ROS bringup, `robot_gateway`, RealSense `camera`, GPU vision(`box_tracker`·`label_reader`), `belt_servo`, `sort_manager`, `sort_logger`, `hmi_bridge`, `camera_preview`, USB `usb_camera_preview` | 주요 ROS 노드는 팀원이 직접 실행. `sort_logger`·`hmi_bridge`·화면 서버는 의석님이 SSH로 접속해 기동해도 **Robot PC에서 실행** |

Robot PC의 `sort_logger`는 Web PC의 PostgreSQL에 `-R 5432` 터널로 접속한다. `hmi_bridge`는 `-R 1883`으로 Web PC의 Mosquitto에 접속한다. Web PC 브라우저는 `-L 8091/8092`로 Robot PC 화면 서버의 영상을 본다. 런북에는 Robot PC에 React 서버나 로컬 DB를 별도 실행하지 않는다고 명시되어 있다. 노란 경계는 서로 독립한 영역으로 배치했고, PC 간 선은 경계를 가로지르게 그렸다.

## 참고본과 생성 방식

로컬 Weld-Made `docs/architecture`의 네 HTML/PNG, `data/`, `renderer-extension/`, `index.html`, `site-wrapper.html`, preview, `ANALYSIS.md`, `BUILD_INFO.json`, `VALIDATION_SUMMARY.md`, `MANIFEST.json`, UI 수정 문서를 확인했다. 참고본은 Archify 3.0.1 공식 architecture renderer로 시스템·ROS를, 확장 architecture renderer로 ERD·공정도를 생성하고 내부 Viewer를 iframe으로 통합했다. SVG/PNG는 HTML의 renderer SVG에서 별도 추출했다. 원본 Viewer의 Path/Map/Lens/발표/검색/Export/테마/Live 기능을 유지하는 구조다.

이번에는 Archify 공식 3.1.0 `f8021f7eee6870a552bbad3373cf6bad32c80f37`을 사용했다. 3.1.0에 `erd`가 공식 유형으로 들어 있어 참고본의 ERD 확장은 적용하지 않았다. 시스템·ROS·공정은 3.1.0 `architecture`, ERD는 3.1.0 `erd` renderer를 기반으로 한다. 참고본의 extension은 3.0.1용이며 3.1.0에 그대로 적용할 호환성 보장이 없어 사용하지 않았다. 공식 3.1.0 Viewer는 한국어 카탈로그를 제공한다. 기본 동작이 Still로 시작하는 점과 architecture 렌더러에 순서도 도형 속성이 없는 점을 확인해, 3.1.0 원본에 `renderer-extension/archify-voss-ui-shapes.patch`를 적용했다. 패치는 Live 기본값(사용자가 선택한 Still/Live는 유지)과 Flow 전용 도형 6종 및 스키마를 추가한다. 정확한 재생성 절차는 renderer-extension/README.md에 있다. 각 HTML을 통합 페이지의 `srcdoc` iframe에 한 번만 넣어 탭 전환 중 카메라/확대 상태를 보존한다. Viewer 자체를 새로 구현하지 않았다.

## 프로젝트 경계

| 영역 | 확인한 구현 | 근거 | 상태 |
|---|---|---|---|
| 웹 UI | React/TypeScript, Nginx 정적 제공, `/api` 역방향 프록시 | `docker/web/frontend/src/App.tsx:153`, `docker/web/frontend/Dockerfile:1`, `docker/web/nginx/default.conf:25` | Implemented |
| 웹 API | Spring Boot REST, SSE, MQTT adapter | `docker/web/backend/src/main/java/com/voss/web/api/CommandController.java:45`, `StreamController.java:21`, `mqtt/MqttSubscriberConfig.java:24` | Implemented; MQTT는 설정 조건부 |
| DB | PostgreSQL 16, 3개 테이블 | `docker/db/compose.yml:1`, `docker/db/init/01_schema.sql:6-59` | Implemented DDL; 운영 DB 적용은 Unconfirmed |
| 브로커 | Mosquitto 2, host network | `docker/mqtt/compose.yml:1-13` | Implemented 구성; 실제 기동은 Unconfirmed |
| HMI bridge | ROS topic/service ↔ MQTT JSON | `src/voss_hmi/voss_hmi/hmi_bridge.py:84-163,239-574` | Implemented; 실제 브로커 연결은 Unconfirmed |
| 분류 제어 | `sort_manager`, `sort_fsm`, `pallet_fsm` | `src/voss_manager/voss_manager/sort_manager.py:123-156`, `sort_fsm.py:6-11`, `pallet_fsm.py:1-15` | Implemented |
| 비전 | RealSense 입력, box_tracker, label_reader/OCR | `src/voss_vision/voss_vision/box_tracker.py:180-202`, `label_reader.py:240-325` | Implemented; 현장 카메라/OCR 모델 상태는 Unconfirmed |
| Servo/로봇 | belt_servo ActionServer, robot_gateway, Doosan 서비스/직접 Modbus | `src/voss_servo/voss_servo/belt_servo.py:379-392`, `src/voss_robot/voss_robot/robot_gateway.py:150-294`, `doosan.py:250-322` | Implemented adapter; 외부 장비 실행은 Unconfirmed |
| 음성/AI | voice_listener→intent_parser→Intent, FastAPI AI HTTP | `src/voss_voice/voss_voice/voice_listener.py:174-209`, `intent_parser.py:60-70,232-254`, `docker/ai/app/main.py` | Implemented; 모델/오디오 장치는 Unconfirmed |
| 결과 기록 | sort_logger→sort_log/pallet_log, spool fallback | `src/voss_hmi/voss_hmi/sort_logger.py:1-2,36-38,137-140` | Implemented; 실제 DB 쓰기 성공은 Unconfirmed |
| 실기 기동 | host launch는 기본 dry_run; 실기 gateway·두산 bringup은 별도 | `src/voss_bringup/launch/voss_host.launch.py:1-25,127-180` | Partial 통합; 실기 기동은 Unconfirmed |

### 화살표 방향

System/ROS 2 도면에서 요청과 실제 응답·피드백이 있는 관계는 두 개의 반대 방향 화살표로 나누었다. 예를 들어 브라우저→Nginx→Spring의 요청과 Spring→Nginx→브라우저의 REST 응답/SSE, manager→belt_servo의 Action goal과 belt_servo→manager의 feedback/result다. MQTT 명령과 상태/ACK, Service 요청·응답도 같은 규칙이다. 순수 Topic 발행(예: 카메라→box_tracker, BoxTrack 발행)은 역방향 데이터를 만들어 표시하지 않았다. ROS 2 도면의 선 라벨은 공간상 줄였고 정확한 Topic/Service/Action 이름과 타입은 아래 표 및 `INTERFACES.md`를 따른다.

### 주요 데이터 방향

- 브라우저는 `/api/stream` SSE를 수신하고 REST 명령/이력을 사용한다 (`docker/web/frontend/src/App.tsx:153`, `docker/web/backend/src/main/java/com/voss/web/api/StreamController.java:21`, `CommandController.java:45`). WebSocket을 사용한다는 근거가 없어 그리지 않았다.
- Spring은 `VOSS_MQTT_ENABLED=true`에서 MQTT adapter를 만들고 (`MqttSubscriberConfig.java:24`), MQTT `voss/command`를 내보낸다. 브로커에서 hmi_bridge가 이를 받아 `/voss/sort/command` Service를 호출한다 (`hmi_bridge.py:50-54,105,239-252,504-574`). 상태/결과는 역방향으로 ROS→bridge→MQTT→Spring→SSE다.
- manager는 `TrackAndGrasp` ActionClient, `MoveToZone`/`Trigger`/`ReadLabel`/`ListPlacements` Service Client를 만든다 (`sort_manager.py:151-156`). Action goal은 manager→servo, feedback/result는 servo→manager다. Service 요청은 client→server, 응답은 반대다.
- sort_logger가 `SortResult`와 `PalletResult`를 구독해 DB에 기록한다 (`sort_logger.py:137-140`, `docker/db/init/01_schema.sql`). Spring은 이력을 조회하고 `session_plan`을 기록한다 (`docker/web/backend/src/main/java/com/voss/web/db/HistoryRepository.java`, `PlanRepository.java`).
- 음성 노드는 AI HTTP를 호출하고, parser가 ROS Intent를 발행한다. `intent_parser.py:232-254`에는 웹 API 전달 분기도 있으므로 ROS 경로가 유일한 경로라는 뜻은 아니다.

## ROS 2 인터페이스 등록표

다음 표는 핵심 정상 운전 경로의 명시적 등록이다. 표의 `→`는 Publisher→Subscriber, Client→Server 방향이다. 외부 Doosan 서비스의 실제 서버 실행 여부는 별도 확인이 필요하다. 정확한 요청/응답 필드는 `src/voss_msgs/msg`, `srv`, `action` 정의를 따른다.

| 발신 → 수신 | 종류 | 정확한 이름 | 타입 | 등록 근거 |
|---|---|---|---|---|
| box_tracker → sort_manager / belt_servo / hmi_bridge | Topic | `/voss/vision/box` | `voss_msgs/msg/BoxTrack` | `box_tracker.py:180`, `sort_manager.py:137-138`, `belt_servo.py:379`, `hmi_bridge.py:136` |
| box_tracker → label_reader | Topic | `/voss/vision/label_crop` | `voss_msgs/msg/LabelCrop` | `box_tracker.py:181`, `label_reader.py:240-244` |
| label_reader → sort_manager | Topic | `/voss/vision/label` | `voss_msgs/msg/LabelRead` | `label_reader.py:313-317`, `sort_manager.py:140` |
| sort_manager → label_reader | Service | `/voss/vision/read_label` | `voss_msgs/srv/ReadLabel` | `sort_manager.py:155`, `label_reader.py:318-322` |
| sort_manager → belt_servo | Action | `/voss/servo/track_and_grasp` | `voss_msgs/action/TrackAndGrasp` | `sort_manager.py:152`, `belt_servo.py:389-392` |
| belt_servo → robot_gateway | Topic | `/voss/robot/servo_cmd` | `geometry_msgs/msg/TwistStamped` | `belt_servo.py:381`, `robot_gateway.py:150-151` |
| robot_gateway → belt_servo / manager / bridge | Topic | `/voss/robot/pose` | `geometry_msgs/msg/PoseStamped` | `robot_gateway.py:107`, `belt_servo.py:380`, `sort_manager.py:143-144`, `hmi_bridge.py:141` |
| robot_gateway → manager / bridge | Topic | `/voss/robot/state` | `voss_msgs/msg/RobotState` | `robot_gateway.py:292-294`, `sort_manager.py:146-147`, `hmi_bridge.py:130-132` |
| sort_manager → robot_gateway | Service | `/voss/robot/move_to_zone` | `voss_msgs/srv/MoveToZone` | `sort_manager.py:153`, `robot_gateway.py:278-280` |
| manager / servo → robot_gateway | Service | `/voss/robot/stop` | `std_srvs/srv/Trigger` | `sort_manager.py:154`, `belt_servo.py:382`, `robot_gateway.py:155-156` |
| belt_servo → robot_gateway | Service | `/voss/robot/gripper` | `voss_msgs/srv/Gripper` | `belt_servo.py:383`, `robot_gateway.py:192-194` |
| sort_manager → bridge / voice_listener / intent_parser | Topic | `/voss/sort/state` | `voss_msgs/msg/SortState` | `sort_manager.py:123`, `hmi_bridge.py:112-116`, `voice_listener.py:66`, `intent_parser.py:81-82` |
| sort_manager → sort_logger / bridge | Topic | `/voss/sort/result` | `voss_msgs/msg/SortResult` | `sort_manager.py:124`, `sort_logger.py:138`, `hmi_bridge.py:118-122` |
| sort_manager → sort_logger / bridge | Topic | `/voss/pallet/result` | `voss_msgs/msg/PalletResult` | `sort_manager.py:132-133`, `sort_logger.py:139` |
| sort_manager → bridge | Topic | `/voss/pallet/state` | `voss_msgs/msg/PalletState` | `sort_manager.py:129-131`, `hmi_bridge.py:149-153` |
| sort_manager → label_reader / intent_parser / bridge | Topic | `/voss/sort/zone_map` | `voss_msgs/msg/ZoneMap` | `sort_manager.py:125-127`, `label_reader.py:246-248`, `intent_parser.py:78-79` |
| sort_logger → manager / bridge | Topic | `/voss/log/status` | `std_msgs/msg/String` | `sort_logger.py:137`, `sort_manager.py:142`, `hmi_bridge.py:143-145` |
| sort_manager → sort_logger | Service | `/voss/log/list_placements` | `voss_msgs/srv/ListPlacements` | `sort_manager.py:156`, `sort_logger.py:140` |
| hmi_bridge → sort_manager | Service | `/voss/sort/command` | `voss_msgs/srv/Command` | `hmi_bridge.py:105`, `sort_manager.py:151` |
| voice_listener → intent_parser | Topic | `/voss/voice/transcript` | `std_msgs/msg/String` | `voice_listener.py:68`, `intent_parser.py:84-85` |
| intent_parser → sort_manager | Topic | `/voss/voice/intent` | `voss_msgs/msg/Intent` | `intent_parser.py:60`, `sort_manager.py:141` |
| manager / parser / bridge → speech_out | Topic | `/voss/voice/say` | `std_msgs/msg/String` | `sort_manager.py:128`, `intent_parser.py:61`, `hmi_bridge.py:106`, `speech_out.py:42` |

추가 등록 호출 98개와 동적·조건부 표현식은 [INTERFACES.md](INTERFACES.md)에 보존했다. `BoxMotion`은 현재 `src/voss_msgs/msg`에 정의가 없어 `hmi_bridge.py:138`의 조건부 구독을 Partial로 분류한다.

상기 파일 이름의 짧은 표기는 각 패키지의 `src/<package>/<package>/` 아래를 뜻한다. 등록된 추가 표시 전용 Topic과 외부 드라이버 호출은 `src/voss_hmi/voss_hmi/hmi_bridge.py`, `src/voss_robot/voss_robot/doosan.py`를 참조한다.

## DB 제약과 논리적 연관

`docker/db/init/01_schema.sql`에 `sort_log`(19열), `pallet_log`(16열), `session_plan`(3열)이 있다. PK는 각각 `box_id`, `(run_id, box_id)`, `session_id`다. **선언된 FOREIGN KEY 및 UNIQUE 제약은 없다**(PK 자체의 유일성은 제외). 인덱스는 `sort_log(session_id,result)`, `sort_log(finished_at)`, `pallet_log(session_id,box_id)`다. ERD의 모든 물리 열·SQL 타입·NULL 여부를 표기했으며 CHECK/DEFAULT 전체 문장은 DDL이 기준이다. `pallet_log.box_id`와 `sort_log.box_id`는 논리적으로 연결되나 FK가 없고, 같은 박스가 실행별 적재 기록 0..N건을 가질 수 있다. `session_plan.session_id`와 결과 행의 `session_id`도 논리적 관계이며 FK가 없다. 그래서 ERD에 **물리 FK 관계선은 그리지 않았다**. 대신 `sort_log.box_id ↔ pallet_log.box_id`, `session_plan.session_id ↔ sort_log.session_id`, `session_plan.session_id ↔ pallet_log.session_id`를 `box_id`·`session_id` 라벨의 점선 논리 관계 3개로 표시했다. FK가 없으므로 각 결과 행이 가리키는 부모 행은 0..1개, 부모 행의 관련 결과는 0..N개로 표현한다. 실기 데이터의 모든 행이 매칭된다는 주장은 아니다. 기설치 DB는 `docker/db/migrations/20261012_sprint2_pallet.sql` 수동 적용이 필요하다.

## 공정 흐름과 구현 범위

`sort_fsm.py:6-11`의 정상 경로는 IDLE→start→RUNNING/OBSERVE→OCR 판정→PICKING→PLACE→SortResult→다음 박스다. 불확실하면 RECHECK/VIEW/ReadLabel, 계속 불확실하면 ASKING에서 운영자 답변을 기다리고 30초 무응답은 HOLD다. `stop`, 구역 포화 및 일부 실패는 PAUSED이며 `resume`은 저장된 단계에 따라 분기한다 (`sort_fsm.py:508-515,560-609`). 도면의 resume 노드에서 단일 단계로 선을 고정하지 않은 이유다. 팔레타이징은 자동 연결이 아닌 별도 `palletize` 명령이며 대상 조회→PICK→DROP→결과 기록 순서다 (`pallet_fsm.py:1-15,245-272,405-531`). belt_servo는 파지 확인 실패 시 조건을 만족하면 내부에서 최대 3회 재시도한다 (`src/voss_servo/voss_servo/fsm.py:273-292`). 팔레트 PICK도 GRIP_FAIL 시 최대 3회다 (`pallet_fsm.py:471-485`). 최대 16칸은 설정/교시와 레이어 조건에 따른 상한이며 항상 16개 적재되는 뜻은 아니다.

## 설계 문서와 실행 코드의 차이

`docs/interfaces/`와 `docs/requirements/`는 계약·목표를 담지만 실제 실행 여부를 보증하지 않는다. `voss_host.launch.py`의 기본값은 dry_run이며 실기에서는 gateway/Doosan bringup이 별도다. `application.yml`에서 MQTT는 기본 false다. PostgreSQL init SQL은 새 데이터 볼륨에서만 자동 실행되고 기존 볼륨은 migration을 사람이 적용한다. 따라서 다이어그램의 선은 구현된 코드 경로이며 특정 PC에서 동시 실행 중이라는 관측이 아니다.
