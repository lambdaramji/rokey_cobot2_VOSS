# 비전 컨테이너 (T22 #31, 남현지)

box_tracker(OpenCV 분할, ADR-0011 — GPU 불필요)와 label_reader(PaddleOCR)를 **서비스 하나씩** 띄운다. 이미지는 하나(`voss-vision:cpu` / `:gpu`).
호스트 노드와는 `network_mode: host` + 같은 `ROS_DOMAIN_ID`·`rmw_cyclonedds_cpp` + **호스트 CycloneDDS 설정 파일 마운트**로 붙는다(SRD 상호확인 합의 — ROS 컨테이너는 CycloneDDS 설정을 공유).

> `docker compose up`·`docker run` 은 사람이 실행한다(Claude 는 빌드·설정 확인까지). box_tracker·label_reader 는 로봇을 움직이지 않지만, 운용 도메인(30)에서 띄우면 sort_manager 가 그 결과로 로봇을 움직인다 — 공용 PC 에서는 런북 순서대로.

## 파일
| 파일 | 내용 |
|---|---|
| `Dockerfile` | `ros:jazzy-ros-base-noble` + cyclonedds·mcap + apt numpy·opencv(box_tracker) + PaddleOCR venv `/opt/voss_ocr`(label_reader, 공용 PC 호스트 venv 와 같은 paddlepaddle 3.3.1·paddleocr 3.7.0). 빌드 인자 `OCR_DEVICE=cpu|gpu`(gpu = CUDA 12.6 휠). 빌드 중 두 노드 import 확인. `--target test` 는 voss_vision pytest |
| `Dockerfile.dockerignore` | context(레포 루트)에서 `src/voss_msgs`·`src/voss_vision`·`entrypoint.sh` 만 보낸다 — `data/`·녹화가 섞이지 않게 |
| `compose.yml` | CPU 기본. config·DDS 설정은 읽기 전용 bind(경로가 틀리면 빈 폴더를 만들지 않고 실패), 녹화 `/data`(읽기 전용), 노드 로그, PaddleOCR 모델 캐시 볼륨 `paddlex-cache` |
| `compose.gpu.yml` | 덧붙임: `:gpu` 이미지, label_reader 만 GPU(`ocr_device:=gpu:0`, nvidia 장치 예약) |
| `.env.example` | 경로·인자. `cp .env.example .env` 뒤 고친다(`.env` 는 커밋 안 함) |

## 도메인 — 셸 값이 먼저
compose 는 **셸에 export 된 변수를 `.env` 보다 먼저** 쓴다. 컨테이너는 compose 를 실행한 셸의 `ROS_DOMAIN_ID`·`ROS_AUTOMATIC_DISCOVERY_RANGE` 를 그대로 따른다(호스트 노드와 같아진다 — 공용 PC 는 30·범위 없음 = SUBNET). 셸에 도메인이 없으면 `entrypoint.sh` 가 77·LOCALHOST(시험)로 띄워, 운용 노드와 안 보이는 쪽으로 실패한다. 두 값은 `.env` 에 적지 않는다 — 셸 30 에 `.env` 의 LOCALHOST 만 섞이면 호스트와 다른 discovery 설정으로 뜬다.

## 개인 PC 시험 (CPU, 녹화 재생, 도메인 77) — 터미널 4개
`ros2 launch`·`ros2 topic hz/echo` 는 Ctrl+C 전까지 끝나지 않으니 **터미널마다 하나씩**. 순서 **B → A → C → D**(zone_map 을 먼저 내면 label_reader 가 크롭을 "준비 전 버림" 하지 않는다). 처음 한 번은 `cp .env.example .env`, `mkdir -p ~/voss_data/logs/vision`(없으면 docker 가 root 소유로 만들어 `~/voss_data` 에 녹화를 못 쓴다), `docker compose build`(몇 분).

**B — sort_manager (zone_map 발행용, 먼저)**
```bash
source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch voss_manager sort_manager.launch.py    # IDLE 로 두고 start 는 보내지 않는다(77 에는 로봇이 없다)
```
**A — 비전 컨테이너**
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/vision
[ -f .env ] || cp .env.example .env
export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
docker compose up -d
docker compose logs -f                             # box_tracker 5 초 통계, label_reader "판독 준비 완료"·"track N s1: …"
```
**C — 판독 결과**
```bash
source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic echo /voss/vision/label
```
**D — (선택) 박스 발행 주기**
```bash
source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic hz /voss/vision/box                     # 박스가 보일 때 약 30 Hz. 박스 사이 빈 구간에는 평균이 떨어진다(정상)
```
**끝:** D·C·B 에서 Ctrl+C → A 에서 Ctrl+C 뒤 `docker compose down`.

- label_reader 는 `/voss/sort/zone_map`(transient_local)을 받아야 판독 준비가 끝나고 `/voss/vision/label` 발행자를 만든다. zone_map 은 sort_manager 가 기동 때 voss_config 로 발행한다.
- 녹화(A_MIX_01, 약 90 s)가 끝나면 box_tracker 컨테이너는 스스로 끝난다(정상). 다시 재생: A 에서 `docker compose up -d box_tracker`.
- 첫 OCR 은 모델을 받는다(인터넷) → `paddlex-cache` 볼륨에 남아 다음부터는 바로 뜬다(10/11 개인 PC: 첫 15.8 s → 캐시 뒤 4.1 s). 시연장 Wi-Fi 가 불안하면 공용 PC 에서 미리 한 번 띄워 둔다.
- 10/11 개인 PC 결과(참고, 완료 수치는 공용 PC): box_tracker 30.0 Hz·검출 p95 ≤ 4.8 ms, 호스트 `ros2 topic hz` 로 컨테이너 토픽 수신, 트랙 9개 stage 1 판독 9/9 코드·동 일치(180° 뒤집힌 송장·"역심동" 퍼지 포함), OCR CPU 1.6~1.8 s/장(180° 는 두 번 읽어 3.2~3.8 s).

## 공용 PC (GPU, 운용 도메인 30) — T22 22-4
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/vision
cp .env.example .env    # VOSS_CONFIG_HOST=${HOME}/voss_ws/config, BOX_TRACKER_ARGS= (비움 = 카메라 실시간)
mkdir -p ~/voss_data/logs/vision
# 셸 ROS_DOMAIN_ID=30·CYCLONEDDS_URI (~/.bashrc) 그대로. 로그 첫 줄이 RANGE=(기본 SUBNET)·CYCLONEDDS_URI=file:///etc/voss/cyclonedds.xml 인지 본다
docker compose -f compose.yml -f compose.gpu.yml up -d --build
docker compose logs -f label_reader       # "OCR 엔진 준비 gpu:0 …", 판독 준비 완료
nvidia-smi                                # AI 컨테이너(Whisper)와 같이 띄운 상태의 VRAM → measurements
```
확인할 것(22-4, measurements 에 기록): GPU 컨테이너 기동, OCR 1장 시간(호스트 CPU 약 3 s 대비), VRAM(비전 + Whisper), box_tracker 30 Hz·카메라→발행 지연(≤ 100 ms). 카메라 노드는 호스트에서 띄운다(USB, 런북 T3).

## 문제가 생기면
- **호스트에서 토픽이 안 보임:** `docker compose logs` 첫 줄 `[voss-vision] ROS_DOMAIN_ID=… RANGE=… CYCLONEDDS_URI=…` 를 호스트 셸(`echo $ROS_DOMAIN_ID $ROS_AUTOMATIC_DISCOVERY_RANGE $CYCLONEDDS_URI`)과 맞춰 본다 — 도메인·범위가 같은지, `CYCLONEDDS_XML` 이 호스트 `CYCLONEDDS_URI` 의 파일인지.
- **`bind source path does not exist`:** `.env` 의 `VOSS_CONFIG_HOST`·`CYCLONEDDS_XML` 경로가 틀림(일부러 빈 폴더를 만들지 않게 해 두었다). 호스트에 CycloneDDS 설정 파일이 아예 없는 PC 는 `CYCLONEDDS_XML=/dev/null`(컨테이너도 Cyclone 기본값).
- **`~/voss_data` 에 녹화가 안 써짐(Permission denied):** `mkdir -p` 없이 처음 띄워 docker 가 root 소유로 만든 것 — `sudo chown -R $USER: ~/voss_data`.
- **노드 로그 파일 주인이 root:** 컨테이너가 root 로 돈다. 지울 때는 `sudo`.
