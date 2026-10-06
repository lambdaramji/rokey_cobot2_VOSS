# 10/06 실측 키트 — 로봇 제어·환경 설정 (김학민)

`docs/measurements-1006.md` 의 #1 · #2 · #4 · #6 · #8 · #9 를 하루에 닫기 위한 절차와 스크립트.
값은 측정 후 **measurements-1006.md 에만** 적는다(conventions). 여기 있는 숫자는 판정 기준과 근거다.

| 파일 | 실측 # | 로봇/그리퍼를 움직이나 |
|---|---|---|
| `env_report.sh` | #2 (+#5 보조) | 아니오. 읽기·핑만 |
| `measure_belt_speed.py` | #1 | 아니오 (`serial` 은 아두이노에 사람이 입력한 줄만 보냄) |
| `rg2_check.py` | #4 · #8 | `status`·`summary` 아니오 / `open`·`move`·`grip` **그리퍼가 움직임** |
| `record_pose.py` | #6 | 아니오. 두산 조회 서비스만 차례로 부름 |
| `exposure_sweep.py` | #9 | 아니오. 카메라 파라미터만 바꿈 |

측정 결과(CSV·PNG·로그)는 `~/voss_ws/measure_1006_data/` 에 쌓인다(레포 밖). `VOSS_MEASURE_DIR` 로 바꿀 수 있다.

---

## 0. 안전 규칙 (모든 항목 공통)

- 실기 명령은 사람이 실행하고, **비상정지 앞에 한 명이 항상 선다**(2인 1조).
- **두산 서비스를 부르는 프로그램은 한 번에 하나만.** 동시에 부르면 `dsr_controller2` 가 응답을 멈추고, 그러면 소프트웨어 정지도 안 된다(전 프로젝트 실측: 복구는 브링업 재시작뿐). `record_pose.py`, 캘리브레이션 스크립트(남현지), servol 확인(박병후)을 **겹쳐 돌리지 않는다.** 로봇 시간표를 아침에 정하는 이유다.
- 툴·TCP 등록은 브링업을 다시 켤 때마다 풀린다. 이 키트는 **플랜지 좌표로 기록**하므로 TCP 가 풀려도 값이 흔들리지 않는다.
- `/onrobot/sendCommand` 의 `'c'` 는 기본 힘이 **40 N(최대)** 이다(onrobot 드라이버 `rgfr = max_force`). 종이 박스에 쓰지 않는다. 파지 시험은 `rg2_check.py grip --force N` 으로 한다.
- `ros2 run dsr_example dance` 같은 예제를 실기에서 돌리지 않는다.

## 1. 아침 10분 — 팀과 정할 것

로봇 1대를 넷이 나눠 쓴다. 아래는 제안이다. 로봇이 필요 없는 일은 로봇을 기다리는 동안 한다.

| 순서 | 로봇 사용 | 누가 | 내용 | 예상 |
|---|---|---|---|---|
| A | 아니오 | 학민 | 줄자 실측(#6-a), 벨트 표시·속도(#1), 조도(#9-a), 송장 시험 인쇄 | 로봇 슬롯 사이사이 |
| R1 | 예 | 학민 | 브링업 → `env_report.sh`(#2) → RG2 경로(#4) → 파지력(#8, 그리퍼만) | 45분 |
| R2 | 예 | 병후 | servol_stream 계열 확인(#3) | 30분 |
| R3 | 예 | 현지 + 학민 | 핸드아이 캘리브레이션(#7). 관측 자세 후보도 이때 같이 본다 | 60~90분 |
| R4 | 예 | 학민 | 좌표 교시 `record_pose.py walk`(#6-b) → 노출 스윕(#9-b) | 60분 |

- 로봇을 어느 PC 에서 띄우는지 정한다(공용 MSI 권장). **스크립트는 그 PC 에서 돌린다.**
  - 학민 노트북은 CycloneDDS 가 `lo` 만 쓰게 설정돼 있다(`~/.config/cyclonedds/cyclonedds.xml`). 브링업과 스크립트를 이 노트북 한 대에서 다 돌리면 괜찮지만, 공용 PC 의 로봇 토픽은 이 노트북에서 안 보인다.
  - 공용 PC 에서: `cd ~/voss_ws/src/rokey_cobot2_VOSS && git fetch && git switch chore/measure-1006-kit` (또는 이 폴더만 복사).
- 송장 시험 인쇄: `~/Downloads/VOSS_송장_인쇄.docx` 를 오늘 한 장 뽑는다. #9 노출 시험과 남현지 OCR 시험(정지 50장)에 필요하다.

## 2. 준비물

줄자(2 m↑), 자 또는 버니어 캘리퍼스, 마스킹테이프, 네임펜, 휴대폰(60 fps 영상, 조도계 앱 — 예: "Lux Light Meter"), 미니 박스 3개 이상, 시험 인쇄 송장 몇 장, 노트북 충전기, (공용 PC 가 아닌 PC 로 로봇을 띄울 경우) 유선 LAN 케이블.

## 3. PC 준비 (R1 전에 5분)

```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/scripts/measure_1006
bash env_report.sh            # 지금 상태를 먼저 본다 (핑·포트·dialout·DDS 인터페이스)
```

- **유선 고정 IP** (로봇 컨트롤러는 DHCP 를 안 준다). 로봇 LAN 에 꽂은 뒤, 인터페이스 이름은 `ip -br link` 로 확인. 같은 망의 다른 PC 와 IP 가 겹치지 않게 끝자리를 고른다.
  ```bash
  nmcli con add type ethernet ifname enp2s0 con-name robot ipv4.method manual ipv4.addresses 192.168.1.10/24
  nmcli con up robot && ping -c 3 192.168.1.100 && ping -c 3 192.168.1.1
  ```
- **아두이노 시리얼 권한**: `dialout` 그룹이 없으면 `/dev/ttyACM0` 를 못 연다. 학민 노트북은 지금 없다.
  `sudo usermod -aG dialout $USER` → 로그아웃/로그인. (아두이노를 IDE 시리얼 모니터나 버튼으로 조작한다면 필요 없다)

---

## #2 컨트롤러·드라이버 버전 (R1, 5분)

**합격**: DRCF·DRFL 버전, doosan-robot2 커밋을 기록. 전 프로젝트 실기값 DRCF `GF02120100`, DRFL `GL013303` 과 같은지 표시.

```bash
# 터미널 1 (사람)
source ~/cobot2_ws/install/setup.bash
ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100   # = roboton 별칭
# 터미널 2 — 브링업이 "Configured and activated dsr_controller2" 를 찍은 뒤
bash env_report.sh
```

- 보고서의 "두산 컨트롤러" 칸이 **오늘 날짜 real 로그**인지 확인한다(로그 경로에 날짜가 있다). 아니면 브링업 터미널의 `DRCF version = ...` 줄을 직접 옮긴다.
- doosan-robot2 커밋: 학민 노트북은 `31750d6` (ROKEY-SPARK/doosan-robot2_jazzy). **로봇을 띄우는 PC 의 커밋**을 적고, 4명 PC 가 같은지 확인한다.

## #4 RG2 제어 경로 (R1, 15분) — 결정 #9 를 오늘 닫는다

**확인할 것**: (1) Modbus TCP 192.168.1.1:502 가 응답하는가, (2) 브링업의 onrobot 드라이버가 같이 떠 있어도 직접 Modbus 읽기·쓰기가 되는가.

```bash
# 브링업 전 (드라이버 없이)
python3 rg2_check.py status
# 브링업 후 (드라이버가 같은 그리퍼를 계속 폴링 중)
python3 rg2_check.py status --watch 5       # 값이 계속 읽히는지, 에러가 없는지
python3 rg2_check.py open --width 90        # 그리퍼가 90 mm 로 열린다 (손 조심)
ros2 topic echo /onrobot_joint_states --once  # 드라이버 쪽 상태도 바뀌었는지
```

**비교 (소스 확인 결과)**

| | Modbus TCP 직접 (robot_gateway 안) | onrobot ROS 2 드라이버 (`/onrobot/sendCommand`) |
|---|---|---|
| 힘 지정 | 0.1 N 단위로 바로 지정 | 기본 40 N, `'d'` 한 번에 −2.5 N 씩만 조정 |
| 폭 지정 | 0.1 mm | 0.1 mm (숫자 문자열) |
| 파지 감지 (TR-PICK-07) | 상태 레지스터 268 bit1 `grip_detected` + 폭 | 서비스 응답은 항상 success. joint_states 의 각도만 |
| 완료 대기 | busy 비트 폴링 | 응답이 이동 완료를 안 기다림 |
| 검증 이력 | 수업 코드 `onrobot.py` 가 같은 레지스터 사용 | 전 프로젝트 Virtual 에서만 호출 |
| 단일 소유 | robot_gateway 가 로봇·그리퍼를 다 가짐 (규칙 3과 같은 결) | 별도 노드 |

**제안**: Modbus TCP 직접. 단, 위 (2) 공존 시험이 통과해야 한다. 실패하면(연결 거부·값 튐) 브링업에서 onrobot 드라이버를 빼는 launch 인자를 voss_bringup 에 둔다.
결정은 `docs/pending-decisions.md #9` 에 적고, 간단한 ADR(0003)로 남긴다.

## #8 RG2 파지력·폭 (R1, 20분)

**합격**: 종이 박스가 찌그러지지 않고, 손으로 살짝 당겨도 미끄러지지 않는 **가장 낮은 힘 + 한 단계 여유**. 그때 읽힌 폭(파지 성공 판정 기준)도 기록.

로봇은 정지. 그리퍼만 움직인다. 박스를 손으로 핑거 사이에 넣는다. **46 mm 면을 핑거가 잡게**(닫힘축 = 벨트 진행 방향), 송장이 위로.

```bash
python3 rg2_check.py open --width 90
python3 rg2_check.py grip --force 3      # 결과 입력: 찌그러짐 y/n, 미끄러짐 y/n
python3 rg2_check.py open --width 90
# 힘 3 → 5 → 8 → 10 → 15 N, 힘마다 2회. 박스는 시도마다 새 면/새 박스
python3 rg2_check.py grip --force 5 --target 40   # 빈 손으로 1회: 박스 없을 때 폭·grip_detected 확인
python3 rg2_check.py summary             # 마크다운 표 → measurements #8 에 붙인다
```

- 목표 폭 `--target 40` 은 박스(46 mm)보다 작아야 한다. 그래야 힘에 닿아 멈추고 `grip_detected` 가 켜진다.
- 기록할 값: 고른 힘 N, 쥔 폭(약 46 mm 근처), **빈손으로 닫혔을 때 폭** → 파지 실패 판정 기준(예: `grip_detected` 이고 폭 46±3 mm)을 robot_gateway 에 쓴다.
- 찌그러짐은 눈 + 캘리퍼스(쥔 뒤 46 mm 가 줄었나). 송장 면이 구겨지면 OCR 에도 나쁘다.
- 들어 올린 상태의 낙하 시험은 로봇이 움직여야 하므로 10/07~08 T34 에서 한다(10회 무손상이 그 완료 기준).
- 결과로 `config/voss_config.yaml` 의 `gripper.force_n` 을 채운다.

## #1 벨트 속도 (로봇 불필요, 40분)

**합격 (SR-HW-04)**: 설정값-속도 표. 개발에 쓸 설정이 **≤ 10 cm/s**, 시도 간 편차 **±5% 이내**.

1. 벨트를 멈추고, 프레임 옆면에 테이프로 **A·B 두 표시를 800 mm 간격**으로 붙인다(양 끝 100 mm 는 피한다). 줄자로 다시 재서 실제 거리를 적는다(`--distance`).
   진행 방향(상류→하류) 화살표와 **작업자가 박스를 올리는 쪽**을 프레임에 표시한다(NFR-10: 로봇 대기 위치와 겹치면 안 된다).
2. 아두이노로 속도를 어떻게 바꾸는지부터 확인한다(가변저항·버튼·시리얼 명령·스케치 상수). 시리얼이면:
   ```bash
   python3 measure_belt_speed.py serial --port /dev/ttyACM0 --baud 115200   # 받은 줄·보낸 줄이 로그로 남는다
   ```
   ⚠ 포트를 열면 보드가 리셋될 수 있다(벨트가 멈추거나 기본값으로 돌아감). 프로토콜을 모르면 판매처 자료·스케치를 먼저 본다.
3. 설정값마다: 5초 돌려 안정 → 박스를 A 앞 상류에 올림 → **휴대폰 60 fps 로 A·B 를 한 화면에** 찍거나 스톱워치로 앞 모서리 A→B 시간. **3회.**
   ```bash
   python3 measure_belt_speed.py trial --setting <설정값> --distance 800   # 8.12 또는 f487@60 입력
   python3 measure_belt_speed.py video clip.mp4 --setting <설정값> --distance 800   # 영상에서 프레임 찍기
   ```
   스톱워치는 반응 오차가 약 0.1~0.2 s 라 10 cm/s(8 s)에서 2% 안팎이다. 편차 판정이 애매하면 영상으로 다시 잰다.
4. 낮은 설정부터 10 cm/s 를 넘을 때까지 4~5단계. 쓸 만한 설정 하나는 **5분 연속 운전 뒤 한 번 더** 재서 드리프트를 본다.
5. 표와 추천값:
   ```bash
   python3 measure_belt_speed.py table --target 5
   ```

- **개발 기준 속도 제안: 약 5 cm/s.** SRD 13장: 사전 개방 90 mm 의 ±22 mm 여유는 5 cm/s 에서 ±0.4 s, 10 cm/s 에서 ±0.2 s 다. 최종 속도는 박병후와 정한다(게이트 10/10).
- 결과로 `voss_config.yaml` 의 `belt.speed_cmps` 를 채운다.

## #6 작업대·로봇 위치·5구역 좌표

### 6-a 줄자 (로봇 불필요, 30분)

위에서 본 스케치를 종이에 그리고 숫자를 적어 사진으로 남긴다. 팀 스케치(`~/Downloads/작업 환경 구성도.png`)는 로봇이 왼쪽, 위 줄에 역삼·대치·청담, 가운데 줄에 재확인·보류, 아래에 벨트다.

- 작업대 가로×세로, 바닥에서 높이
- 로봇 베이스 중심 위치(작업대 두 모서리에서 거리), **베이스 바닥면이 작업대 면보다 얼마나 높은가**(받침판 두께 h)
- 벨트: 중앙선이 작업대 가장자리·베이스 중심에서 얼마나 떨어졌나, 벨트 윗면 높이(작업대 기준), 상류·하류 끝 위치
- 구역 5개: 각 사각형 크기와 위치. **2×2 격자(pitch 60 mm)에 박스(46×31)를 놓으려면 구역 하나가 약 106×91 mm 를 차지한다 → 130×120 mm 이상 권장.** 재확인 구역은 벨트에 가장 가깝게(BRD 2.4)
- 모든 구역이 베이스 중심에서 반경 약 850 mm 안인지 (리치 900 mm)

### 6-b 좌표 교시 (R4, 로봇 사용, 45분)

브링업이 떠 있고, 협동 속도 제한이 걸린 상태에서 **직접교시(손으로 끌기)** 로 옮긴다. 자세는 수직 아래(펜던트에서 B≈180°)로 맞춘다.
박스를 쥐는 단계는 #8 에서 고른 힘으로 `rg2_check.py grip --force <N>` 을 먼저 한다.

```bash
python3 record_pose.py walk          # 라벨 안내대로 옮기고 Enter. 중간에 끊겨도 --start <라벨> 로 이어서
python3 record_pose.py analyze       # 벨트 축·높이·추종 구간·구역 놓기 자세 + voss_config 조각
```

| 라벨 | 자세 | 얻는 것 |
|---|---|---|
| `tip_table` | 그리퍼 닫고 핑거 끝을 작업대에 | 작업대 높이(플랜지 기준) |
| `tip_belt_up` / `_mid` / `_down` | 핑거 끝을 벨트 중앙선 상류 끝·가운데·하류 끝(닿는 데까지)에 | 벨트 진행 방향(베이스 기준 각도, `direction_axis`), 벨트 높이, **추종 가능 구간 ≥ 500 mm (SR-HW-01)** |
| `box_on_table` | 박스를 쥐고 밑면이 작업대에 막 닿게 | 핑거가 박스 윗면에서 몇 mm 내려가 잡는지 → 벨트 위 파지 높이 |
| `zone_A` `zone_B` `zone_C` `zone_recheck` `zone_hold` | 박스를 쥐고 **구역 중심**에 밑면이 막 닿게, 닫힘축은 벨트에서 집을 때와 같은 방향 | 구역 놓기 자세(analyze 가 +5 mm 여유를 더함) |
| `observe` | 관측 자세 후보 (카메라가 벨트 상류 약 20 cm 를 15~20 cm 높이에서 봄) | R3 에서 남현지·박병후와 같이 정한다 |
| `safe` | 구역 사이를 오갈 때 지나갈 높은 자세 | 이동 경로 |

`analyze` 경고를 보고 다시 찍는다: 수직에서 2° 넘게 기울어짐, 리치 끝(850 mm↑), 구역 중심끼리 130 mm 미만, 추종 구간 500 mm 미만, 벨트가 베이스 축과 3° 넘게 틀어짐.

- 기록은 플랜지 posx(TCP 미적용)와 그때의 TCP posx 를 같이 남긴다(`poses.csv`). measurements #6 에는 **"플랜지 기준"** 이라고 명시한다.
- 관절값도 같이 남으니, 나중에 같은 자세로 돌아갈 때(movej) 쓴다.

## #9 조도·카메라 노출 (조도는 아무 때, 스윕은 R4 끝에 15분)

**합격**: 수동 노출 5~8 ms, 고정 화이트밸런스에서 송장 분류코드가 선명하고 포화가 없다. 아니면 "보조 LED 필요" 로 기록.

1. 휴대폰 조도계로 벨트 관측 구간·재확인 구역·작업대 가운데의 lux 를 잰다(평소 조명, 시연 때와 같은 커튼 상태).
2. 카메라를 켠다: 브링업에 `camera:=true` 를 붙이거나 `realsense` 별칭. 송장 붙은 박스를 벨트 관측 구간에 두고 로봇을 관측 자세(`observe`)로.
3. 스윕:
   ```bash
   python3 exposure_sweep.py --values 50 60 70 80 --wb 4600 --tag lux<측정값>
   ```
   처음 줄에 `rgb_camera.exposure` 범위가 찍힌다. **1~10000 이면 단위가 0.1 ms** 라 50~80 이 5~8 ms 다. 다르면 값을 맞춰 다시 돌린다.
4. 판정: 표의 포화 % 가 0 에 가깝고, PNG 에서 `S07-0x` 가 또렷한 **가장 짧은 노출**을 고른다(짧을수록 번짐이 적다: 5 cm/s × 8 ms = 0.4 mm, 10 cm/s × 8 ms = 0.8 mm). 너무 어두우면(밝기 평균 대략 80 아래) gain 을 조금 올려 보고, 그래도 안 되면 LED.
5. PNG 폴더를 남현지에게 넘긴다(OCR 확인용, 레포에 커밋하지 않는다). 고른 노출·WB 값은 voss_bringup 카메라 파라미터로 옮긴다.

⚠ **해상도 확인 필요**: SRD 는 RGB 1920×1080 을 전제로 "관측 20 cm 에서 분류코드 5.5 mm ≈ 30 px" 를 계산했다. 지금 브링업·`realsense` 별칭은 **1280×720** 이라 같은 높이에서 약 20 px 로 줄어든다. 남현지와 해상도(1080p) 또는 관측 높이(15 cm)를 정한다.

---

## 4. 결과 정리 (끝나기 30분 전)

1. `docs/measurements-1006.md` 의 #1 #2 #4 #6 #8 #9 칸과 벨트 표를 채운다(숫자 + 단위 + 기준: "플랜지 기준", "1280×720" 등).
2. `config/voss_config.yaml` 에 `belt.speed_cmps`, `zones.*.pose`, `observe_pose`(정해졌으면), `gripper.force_n`.
   ⚠ CI 가 **voss_config.yaml 을 바꾸면 docs/interfaces/ 도 바뀌어야** 통과시킨다. 값만 채워도 `docs/interfaces/voss_config.md` 의 변경 이력에 한 줄을 적는다.
3. `docs/pending-decisions.md` #9 (RG2 경로) 결정 기록.
4. 한 PR 로 올린다(이슈 번호 붙여서). measurements·config 는 PL 승인 대상이다.
5. `~/voss_ws/measure_1006_data/` 를 통째로 팀 드라이브에 백업(사진·영상 포함, 레포 아님).

## 5. 팀에 물어볼 것 (오늘 결론 내면 좋은 것)

- **구역 pose 의 의미**: 이 키트는 "구역 중심 + 플랜지 기준"으로 기록한다. `docs/interfaces/voss_config.md` 에는 기준점(TCP/플랜지)과 슬롯 원점(중심/모서리)이 안 적혀 있다 → PL 에게 인터페이스 문서 보완 요청.
- **벨트 방향**: 벨트가 베이스 축과 틀어져 있으면 `direction_axis: "x"` 하나로는 부족하다 → 단위 벡터를 쓰자고 제안(박병후 피드포워드에 영향).
- **카메라 해상도**: 1280×720 vs 1920×1080 (위 #9).
- **송장 (결정 #10·#11, 기한 10/07)**: `VOSS_송장_인쇄.docx` 초안에 이미 14장이 있다. 받는 사람은 팀원 이름 4개, 흐린 송장은 인쇄 농도가 아닌 **번짐(blur) 처리로 2장**(둘 다 S07-01 역삼동)이다. BRD 는 흐린 송장 1장 → 몇 장을 쓸지, 번짐 방식으로 갈지만 정하면 #10·#11 을 닫을 수 있다. 시연 5단계 질문이 "역삼동인지 청담동인지" 라서 역삼동 흐린 송장과 맞는다.
