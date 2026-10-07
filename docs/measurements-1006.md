# 10/06 실측·확인 체크리스트

값은 **여기에만** 적는다. voss_config.yaml·SRD·ADR은 이 파일을 참조한다.

| # | 항목 | 담당 | 결과 (값·단위) | 관련 SR | 완료 |
|---|---|---|---|---|---|
| 1 | 벨트 속도: 아두이노 설정값별 cm/s 표, 10 cm/s 이하 설정 확인 | 김학민 | 아래 표. 개발 설정 h250 = 4.89 cm/s (5분 연속 후 4.79) → `belt.speed_cmps` = 4.8 | SR-HW-04, SR-FN-04 | ☑ |
| 2 | 두산 컨트롤러 DRCF·doosan-robot2 버전 | 김학민 | DRCF `GF02120100`, DRFL `GL013303` (10/06 real 로그, 전 프로젝트와 같음). doosan-robot2 `31750d6` (공용 PC). **부분 완료: 팀원 PC 3대 커밋 비교 남음** | SR-HW-01, SR-SW-04 | ◐ |
| 3 | 서보 스트리밍 토픽(servol_stream 계열) 유무, 주기 | 박병후 | | SR-IF-09 | ☐ |
| 4 | RG2 제어 경로 확인 (Modbus TCP 192.168.1.1:502 응답 / 드라이버) | 김학민 | 502 응답 (브링업 전·후). onrobot 드라이버 폴링(약 50 Hz)과 공존해도 직접 읽기·쓰기 정상 → Modbus TCP 직접 (ADR-0005) | SR-HW-02, SR-SW-05 | ☑ |
| 5 | 공용 PC GPU 모델·VRAM·RAM, USB 3.0 포트 수, NIC 2개 | 정의석 | MSI Katana 17 B13VFK / Ubuntu 24.04.5 / RTX 4060 Laptop 8 GB (드라이버 595.91.07, CUDA 13.2) / RAM 32 GB / USB3 3개 (ACPI 기준, 육안 확인 전) / 유선 RTL8111 + Wi-Fi O. 상세: [아래 5번](#5-공용-pc-사양-상세-sr-hw-09) | SR-HW-09 | ☐ |
| 6 | 작업대 치수, 로봇 베이스 위치·높이, 5구역 좌표(posx) | 김학민 | 5구역(트레이)·관측 자세·벨트·작업대 면 높이를 로봇 좌표로 측정 (아래 #6). 작업대 바깥 줄자 치수는 생략 | SR-HW-08 | ☑ |
| 7 | 벨트 평면 호모그래피 검증점 오차 (mm, ADR-0003. 정식 핸드아이는 별도) | 남현지 | **최대 2.63 mm** (V1 2.32 · V2 2.48 · V3R 2.63 · V4 1.66 · V5 1.66), 계산점 10 RMS 1.70, 기준 ≤ 5 mm(제안값) **합격**. 10/06 + 10/07 재측정 합침 (아래 #7) | SR-FN-02 | ☑ |
| 8 | 종이 박스 무손상 RG2 파지력·폭 | 김학민 | 14 N (최저 합격 12 N + 여유), 31 mm 면 파지, 쥔 폭 40.1~40.3 mm·빈손 38.7 mm (RG2 보고값) | SR-HW-02 | ☑ |
| 9 | 시연장 조도, 보조 LED 필요 여부, 노출 5~8 ms 확인 | 김학민 | 수동 노출 6.0 ms (값 60, 단위 0.1 ms), WB 4600, 1920×1080 에서 포화 0.33 %·코드 또렷 → 보조 LED 불필요. 조도 lux 는 측정 생략 (아래 #9) | SR-HW-12 | ☑ |
| 10 | 내장 마이크 1 m 호출어 인식 | 정의석 | | SR-HW-11 | ☐ |

## 벨트 설정값-속도 표
설정값 = 아두이노 `conveyor_test.ino` 의 `delayMicroseconds` 반주기(µs). A–B 740 mm, 스톱워치 3회.

| 아두이노 설정값 | 실측 cm/s (3회 평균) | 비고 |
|---|---|---|
| h500 | 2.47 | 원본 스케치 기본값. ±0.4 % |
| h330 | 3.69 | ±0.2 % |
| **h250** | **4.89** | 개발 설정. ±1.1 %. 5분 연속 후 4.79 (−2.0 %, 드리프트 없음) |
| h170 | 6.98 | ±0.9 % |
| h110 | 11.01 | 10 cm/s 초과. ±3.8 % (짧은 구간 스톱워치 오차) |

- 마이크로스텝은 실측으로 약 1/32 로 추정 (드라이버 SW1~SW3 미확인). 속도 ∝ 1/(반주기 + 약 11 µs).
- 진행 방향: 원본 D2 LOW / D3 HIGH. 반전은 D3 만 LOW 로 한다 (**D2 HIGH 금지**: 벨트가 멈추고 핀 과전류 위험).
- 컨베이어 러너북의 "펄스 400 µs" 는 원본 스케치(500 µs)와 다르다.

## #4 RG2 제어 경로
- 브링업 전: `rg2_check.py status` 폭 109.1 mm, 상태 정상.
- 브링업 후 (onrobot 드라이버가 같은 그리퍼를 약 50 Hz 폴링): 5 s 연속 읽기 정상, `open 90` → 89.9 mm / 1.21 s, 드라이버 joint_states 에도 반영 (−0.0724 rad ≈ 89.6 mm). joint_states `header.stamp` = 0.
- Compute Box 에 WebLogic 프로그램 "C2 - voss" (DIO 로 파지 39 mm/14 N, 개방 90 mm/15 N)가 있다. 시스템 운전 중에는 STOP 한다 (ADR-0005).

## 5. 공용 PC 사양 상세 (SR-HW-09)

- 확인: 2026-10-06 08:55–09:20 KST, 정의석, 호스트 `ms-03` (MSI Katana 17 B13VFK, 보드 MS-17L5)
- 읽기 전용 명령만 썼다. sudo, 설치, 설정 변경, GPU 테스트 컨테이너 실행은 하지 않았다.
- 기준은 SR-HW-09와 BRD 6.1(장비·네트워크 표)이다.

| 항목 | 기준 | 실측값 | 판정 |
|---|---|---|---|
| OS | Ubuntu 24.04 | Ubuntu 24.04.5 LTS, 커널 7.0.0-34-generic (HWE) | 충족 |
| CPU | (참고) | Intel Core i7-13620H, 10코어(6P+4E) / 16스레드, 최대 4.9 GHz | 참고 |
| RAM | 16 GB 이상 | 32 GB, swap 8 GB | 충족 |
| GPU | NVIDIA, nvidia-smi 정상 | Intel UHD (RPL-P) + NVIDIA RTX 4060 Laptop **8 GB**, 드라이버 595.91.07, CUDA 13.2, PRIME `on-demand` | 충족 |
| CUDA 툴킷 (호스트) | 없어도 됨 (컨테이너에서 사용) | `nvcc` 없음 | 해당 없음 |
| Docker GPU | GPU 컨테이너 실행 가능 | Docker 29.8.2, 런타임 `nvidia` 등록, nvidia-container-toolkit 1.20.1, `ms-03`이 `docker` 그룹 소속 | 충족 (실행 테스트 전) |
| 디스크 | (참고) | NVMe 512 GB, `/` 401 GB 남음 | 충족 |
| USB 3.0 | D435i 전용 1 + 아두이노·마이크용 여유 | USB 3 포트 3개 + USB 2.0 1개로 추정 (ACPI `hotplug` 포트 수와 MSI 공식 사양이 같음) | 충족 (추정). **육안 확인 필요** |
| NIC | 유선 1 + Wi-Fi 1 | 유선 Realtek RTL8111 `enp4s0`, Wi-Fi Intel CNVi `wlo1` (교육장 Wi-Fi) | 충족 |
| 로봇망 | 192.168.1.0/24, 로봇 192.168.1.100 | `enp4s0` = 192.168.1.10/24 (수동), 로봇 192.168.1.100 ping 0.3 ms, 192.168.1.1 ping 0.7 ms. 링크 속도 **100 Mb/s** | 충족 |
| 인터넷 경로 | OpenAI API는 Wi-Fi로 | 기본 경로가 `wlo1`(metric 600)로 나감. 유선 프로필에도 게이트웨이 192.168.1.1이 있음 (metric 20100) | 충족 (주의, 아래 3번) |
| 오디오 (SR-HW-11) | 내장 마이크·스피커 | 내장 DMIC, 아날로그 입출력 (sof-hda-dsp), HDMI 출력. USB 마이크 미연결 | 충족 (1 m 인식률은 #10에서 확인) |
| ROS 2 / Python | Jazzy, 3.12 | `/opt/ros/jazzy`, Python 3.12.3 | 충족 |
| RMW / 도메인 | CycloneDDS, ROS_DOMAIN_ID 30 | `rmw_cyclonedds_cpp`, `ROS_DOMAIN_ID=30` (`~/.bashrc`) | 충족 |
| CycloneDDS 인터페이스 | 개인 PC와 같은 LAN으로 DDS 통신 (BRD 6.1) | `~/.config/cyclonedds/cyclonedds.xml`이 **`lo`만** 사용 | **미달** |
| 아두이노 시리얼 권한 | `/dev/ttyACM*` 접근 | `ms-03`이 **`dialout` 그룹에 없음** | **미달** |
| RealSense SW | RGB 30 Hz (깊이 미사용, CLAUDE.md 규칙 4) | librealsense2 2.58.4, ros-jazzy-realsense2-camera 4.58.4, udev 규칙 설치. `librealsense2-dkms`는 커널 7.0용 미빌드 (`added`). D435i 미연결 | 확인 필요 |
| 워크스페이스 | `~/voss_ws/src/rokey_cobot2_VOSS` | 10/06에 이 경로로 클론함. 아직 빌드 전 | 충족 |

### 문제와 조치안

1. **CycloneDDS가 `lo`에만 묶여 있다 (미달).** 공용 PC 안의 노드끼리, 그리고 `--network host` 컨테이너와는 통신된다. 두산 드라이버는 DDS가 아니라 TCP(DRFL)로 컨트롤러에 붙으므로 로봇 연결과도 무관하다. 대신 **개인 PC ↔ 공용 PC의 DDS 통신(BRD 6.1)이 안 된다.** 개인 PC에서 토픽을 보거나, 공용 PC가 아닌 곳에서 HMI를 띄우면 노드가 보이지 않는다.
   - 조치안: `NetworkInterface`에 `wlo1`을 추가하거나 `lo`를 `wlo1`로 바꾼다. 로봇망(`enp4s0`)에는 DDS가 필요 없으니 넣지 않는다. 환경 설정 담당(김학민)이 정한다.
2. **`dialout` 그룹이 없다 (미달).** 아두이노를 꽂아도 `/dev/ttyACM0`를 열 수 없다.
   - 조치안: `sudo usermod -aG dialout ms-03` 실행 후 다시 로그인한다. sudo가 필요하므로 팀 승인을 받고 진행한다.
3. **유선 프로필의 게이트웨이가 192.168.1.1이다 (주의).** 이 주소는 BRD상 RG2 툴체인저 주소다. 지금은 유선의 인터넷 연결 확인이 실패해 NetworkManager가 유선 경로에 큰 metric(20100)을 붙였고, 그래서 인터넷이 Wi-Fi로 나간다. 하지만 이 동작에 기대는 것은 불안정하다.
   - 조치안: `Wired connection 1`, `Wired connection 2`의 게이트웨이를 비우고 `ipv4.never-default yes`로 둔다. 시스템 네트워크 설정을 바꾸는 일이므로 환경 설정 담당이 결정한다.
   - 참고: USB 랜 어댑터용 `Wired connection 2`도 IP가 192.168.1.10으로 같다. 내장 포트와 동시에 꽂지 않는다.
4. **유선 링크가 100 Mb/s다.** RTL8111은 기가비트를 지원하므로 상대 포트(컨트롤러나 스위치)가 100 Mb/s이거나 케이블 문제일 수 있다. 로봇 명령 트래픽에는 충분하다. 바꿀 필요는 없고 기록만 해 둔다.
5. **USB 포트가 빠듯하다.** D435i, 아두이노, 마우스(그리고 USB 마이크를 쓰면 마이크)로 포트 4개를 모두 쓴다. D435i는 USB 3 포트에 직접 꽂는다(허브 금지). 꽂은 뒤 `lsusb -t`로 `8086:0b3a`가 `Bus 002`(10000M 루트 허브)에 5000M으로 붙었는지 본다. 포트가 모자라면 아두이노와 마우스만 전원 허브로 옮긴다.
6. **RealSense는 D435i를 연결한 뒤 확인한다.** 깊이는 쓰지 않으므로 DKMS 미빌드의 영향은 작다. 남은 확인은 `rs-enumerate-devices`, `realsense-viewer`로 RGB 30 Hz와 수동 노출 5~8 ms(#9)가 되는지다.
7. **VRAM 8 GB는 미결정 #6(Whisper 모델 크기)의 판단 근거다.** YOLO, PaddleOCR, Whisper를 함께 올려야 하니, 통합 전에 각 모델의 VRAM 사용량을 `nvidia-smi`로 잰다.
8. **GPU 컨테이너 실행 테스트는 아직 안 했다.** 로컬에 이미 있는 이미지로 확인한다 (새로 받을 필요 없음): `docker run --rm --gpus all ros:jazzy-ros-base-noble nvidia-smi`

### 10/06 오후 갱신 (김학민, 실측 중 확인)
- 2번 `dialout`: **해결.** 팀 승인 후 `usermod -aG dialout ms-03`, 다시 로그인. `/dev/ttyACM0`(Arduino Uno `2341:0043`) 열림 확인.
- 5·6번 D435i: **해결.** 첫 포트에서는 `Bus 001` 480M(USB 2)로 잡혀 포트를 바꿨다. `Bus 002` Port 2 에 5000M 으로 연결. RGB 1920×1080 30 Hz, 수동 노출 6 ms 확인 (#9).
- 1번 CycloneDDS `lo`: 그대로 둠. 10/06 실측은 브링업·스크립트·카메라를 공용 PC 한 대에서 돌려 문제없었다.
- 3번 유선 게이트웨이: 그대로 둠.
9. 기타
   - `nvidia-driver-595`, `docker-ce`, `docker-ce-cli`, `containerd.io`가 apt hold 상태다. 일부러 고정한 것으로 보이니 그대로 둔다.
   - `nvidia-smi` 전력 값이 `590W / 80W`로 비정상 표시된다. 센서 값 오류로 보이며 동작에는 영향이 없다.
   - Wi-Fi 절전이 켜져 있다 (`default-wifi-powersave-on.conf`). 개인 PC와 DDS로 통신할 때 지연이 튀면 의심한다.
   - BRD 6.1 장비 표에는 "USB 마이크", 배포 구성에는 "내장 마이크"로 적혀 있어 서로 다르다. #10 결과를 보고 하나로 맞춘다.

<details>
<summary>원본 출력 (MAC 주소·Wi-Fi 이름·Wi-Fi 주소는 가림)</summary>

```
== 기기 / OS
Micro-Star International Co., Ltd. / Katana 17 B13VFK / MS-17L5 / hostname ms-03
Ubuntu 24.04.5 LTS (noble), 7.0.0-34-generic
== CPU / RAM
Model name: 13th Gen Intel(R) Core(TM) i7-13620H, CPU(s) 16, Core(s) per socket 10, Thread(s) per core 2, max 4900 MHz
Mem: total 31Gi  used 5.6Gi  available 25Gi / Swap 8.0Gi / MemTotal 32554264 kB
== GPU
00:02.0 VGA [0300]: Intel Corporation Raptor Lake-P [UHD Graphics] [8086:a7a8]
01:00.0 VGA [0300]: NVIDIA Corporation AD107M [GeForce RTX 4060 Max-Q / Mobile] [10de:28a0]
nvidia-smi: Driver Version 595.91.07, CUDA Version 13.2
  0  NVIDIA GeForce RTX 4060 ...  41C P0  590W / 80W  15MiB / 8188MiB  15%  Default
--query-gpu: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 595.91.07
prime-select query: on-demand
nvcc: command not found
lsmod: nvidia, nvidia_uvm, nvidia_drm, nvidia_modeset (nouveau 없음)
dpkg: hi nvidia-driver-595 / ii nvidia-utils-595 / ii nvidia-container-toolkit 1.20.1-1 / ii libnvidia-container1 1.20.1-1
apt-mark showhold: containerd.io, docker-ce, docker-ce-cli, nvidia-driver-595
== Docker
Docker version 29.8.2 / Runtimes: io.containerd.runc.v2 nvidia runc / Default Runtime: runc
NVIDIA Container Toolkit CLI version 1.20.1
groups: ms-03 adm cdrom sudo dip plugdev users lpadmin docker
images: doosanrobot/dsr_emulator:3.0.1, hello-world:latest, ros:jazzy-ros-base-noble
== 디스크
/dev/nvme0n1p2 468G 43G 401G 10% / ; nvme0n1 476.9G Micron_2400_MTFDKBA512QFM
== USB
00:14.0 USB controller: Intel Alder Lake PCH USB 3.2 xHCI Host Controller
Bus 001 root_hub xhci_hcd/12p 480M: 마우스(046d:c077), 내장 웹캠(5986:211b), MysticLight(1462:1601), BT(8087:0026)
Bus 002 root_hub xhci_hcd/4p 10000M: 연결 장치 없음 (D435i 미연결)
connect_type: usb2-port1~3 hotplug, usb2-port4 not used / usb1-port1,4,5,8 hotplug
/dev/ttyACM*, /dev/ttyUSB*: 없음
== 네트워크
04:00.0 Ethernet: Realtek RTL8111/8168/8211/8411 PCIe Gigabit
00:14.3 Network: Intel Raptor Lake PCH CNVi WiFi
enp4s0  UP  192.168.1.10/24   speed 100   (08:55 확인 시 NO-CARRIER, 09:15 재확인 시 연결)
wlo1    UP  172.24.x.x/22   (교육장 Wi-Fi)
nmcli connection: Wired connection 1 (enp4s0) manual 192.168.1.10/24 gw 192.168.1.1
                  Wired connection 2 (enx…, USB 랜) manual 192.168.1.10/24 gw 192.168.1.1
ip route: default via 172.24.x.1 dev wlo1 metric 600
          default via 192.168.1.1 dev enp4s0 metric 20100
          192.168.1.0/24 dev enp4s0 src 192.168.1.10 metric 100
ping 192.168.1.100: 2/2, avg 0.33 ms ; ping 192.168.1.1: 2/2, avg 0.65 ms
cyclonedds.xml: <NetworkInterface name="lo" .../>, AllowMulticast true, Socket buffer min 64MB
== 오디오
CAPTURE: card 1 sof-hda-dsp: HDA Analog(0), DMIC(6), DMIC16kHz(7)
PLAYBACK: card 1 sof-hda-dsp: HDA Analog(0), HDMI1-3 ; card 0 HDA NVidia: HDMI 0-3
== ROS / Python
/opt/ros/jazzy ; Python 3.12.3
ROS_DISTRO=jazzy ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
CYCLONEDDS_URI=file:///home/ms-03/.config/cyclonedds/cyclonedds.xml
librealsense2 2.58.4, librealsense2-dkms 1.3.33 (dkms: added), ros-jazzy-realsense2-camera 4.58.4
```
</details>

## #6 좌표 (Base, 플랜지 기준 posx, mm·deg)
펜던트에서 TCP 기준으로 읽고 플랜지로 변환했다. 펜던트 TCP = (1.382, 2.684, 246.642, 0, 0, 0), Tool Weight CoG = (0, 31.08, 29.84) mm.

| 항목 | 값 |
|---|---|
| 벨트 진행 방향 | 베이스 +x, −0.74° |
| 추종 가능 구간 | 748 mm (TCP x −107 → 638). 이보다 상류의 벨트 시작 구간은 로봇이 닿지 않음 |
| 벨트 윗면 | 작업대 +81 mm, 745 mm 동안 2.4 mm 기울기 |
| 벨트 위 파지 높이 | 플랜지 z 328.9 (핑거 끝 = 박스 밑면 +8 mm) |
| 구역 놓기 자세 | 트레이 안쪽 바닥 중심, 박스 밑면 +5 mm. 값은 voss_config.yaml `zones` (아래 트레이) |
| 관측 자세 = 홈 | [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03], 관절 (-93.89, -13.54, 97.73, -0.01, 94.88, -185.08) |
| 홈 복귀 | 현재 x, y 에서 플랜지 z ≥ 446.6 (TCP z 200)까지 수직 상승 후 수평 이동 (보류 구역 → 홈 직선 이동 시 벨트 충돌) |

검사 (record_pose analyze): 수직 기울기 ≤ 0.93°, 최대 리치 697 mm, 구역 중심 간격 ≥ 228 mm, 경고 없음. 원본: `~/voss_ws/measure_1006_data/poses_pendant*.csv` (레포 밖).

작업대(나무 테이블) 바깥 크기와 바닥 높이는 줄자로 재지 않는다. 로봇 동작에 필요한 위치는 모두 베이스 기준 좌표로 얻었다: 베이스 = 원점, 작업대 면 = `tip_table`, 벨트 = 3점, 구역 = 트레이 5점. 작업대나 로봇을 옮기면 이 절의 교시를 다시 한다.

### 트레이 (10/06 오후 설치, 5구역 재측정)
- 구역마다 플라스틱 트레이: 겉 220 × 150 × 45 mm, 안쪽 바닥 215 × 145 mm, 바닥 두께 5 mm, 안쪽 벽 40 mm. 긴 변이 벨트 방향(X). 네 귀퉁이를 테이프로 고정.
- 배치: 오른쪽 줄 연두 = A 역삼 / B 대치 / C 청담, 가운데 줄 파랑 = 재확인, 빨강 = 보류.
- 놓기 자세를 트레이 안쪽 바닥 중심에서 다시 교시했다. 테이프 중심 대비 4.6~7.4 mm 이동, 높이 +4.3~+6.1 mm (바닥 두께). 보류만 +8.2 mm (두 번 재도 같음, 그 트레이 바닥이 높음). 기울기 0°, 간격 ≥ 228 mm.
- 그리퍼 방향은 5구역 모두 −90° (펜던트 a − c = 90). A 는 측정 때 −93.4° 여서 회전만 −90° 로 맞췄다.
- **자세 표기 주의:** ry = ±180° 라 ZYZ 의 rx·rz 는 한 값으로 정해지지 않는다(rx − rz 만 의미). 그래서 구역마다 rx/rz 가 35/−54, 159/70 처럼 제각각이다. robot_gateway 는 movel 전에 `(rx − rz, 180, 0)` 형태로 정규화해 보간 중 손목이 돌지 않게 한다 (T32).
- **격자 (X 방향 한 줄):** A·B·C 3×1 (트레이 중심 기준 X −60 / 0 / +60, 박스 끝 ±83 mm), 재확인·보류 2×1 (X ±30, 박스 끝 ±53 mm). 안쪽 반폭 X ±107.5 mm. Y 는 모두 중심이라 Y(핑거 벌림) 방향 위치는 중심과 같다. 총 13칸 (시연 10개: A·B·C 최대 3, 재확인·보류 1~2).
- **놓을 때 벌림:** 놓을 때도 pre_open **90 mm** (보고값, 실제 약 80). 트레이 중심과 X 방향으로 옮긴 자리에서 90 mm 로 벌려도 벽에 닿지 않음을 확인했다 (김학민). Y 방향으로 옮겨 놓으면 핑거가 벽(±72.5)에 가까워지므로 격자는 X 방향 한 줄로만 둔다.
- **이동:** 벨트 파지 높이에서 박스 밑면은 작업대 +81 mm, 트레이 테두리는 +45 mm 다. 그 높이로 트레이 위까지 수평 이동 → 트레이 위에서 수직 하강, 놓은 뒤 수직 상승 후 이동.

## #8 RG2 파지력·폭
작업대 위 박스, **31 mm 면** 파지 (46 mm 변 = 벨트 방향), 목표 폭 39 mm.

| 힘 N | 시도 | grip 감지 | 찌그러짐 | 미끄러짐 | 쥔 폭 mm |
|---|---|---|---|---|---|
| 3 | 1 | 0 | 1 | 1 | 39.8 (놓침) |
| 8 | 1 | 1 | 0 | 1 | 41.4 |
| 10 | 1 | 1 | 0 | 1 | 40.6 |
| 12 | 3 | 3 | 0 | 0 | 40.3 |
| 14 | 2 | 2 | 0 | 0 | 40.2 |

- 빈손 (목표 39 mm, 12 N): 38.7 mm, grip_detected 꺼짐. 판정: `grip_detected` 주, 폭 39.5~41.5 mm 보조.
- RG2 보고 폭 ≈ 실제 간격 + 10 mm (캘리퍼스: 40.3 → 30, 90 → 80). 사전 개방 90 mm (보고) = 실제 약 80 mm.
- 낙하 시험은 10/07~08 T34.

## #9 카메라
1920×1080 30 fps, 깊이 끔. 노출 스윕 (벨트 위 송장, 관측 자세): 50/60/70/80 → 포화 0.20/0.33/1.64/3.09 %, 밝기 117/130/141/151. 설정 기록: `~/voss_calib/camera_settings.txt` (레포 밖). 최종 값은 10/07 T33.

조도 lux 는 재지 않는다. 작업실 조명이 일정하고 시연도 같은 환경에서 하므로, 판정(노출 5~8 ms 에서 송장이 읽히는가, 보조 LED 가 필요한가)은 위 카메라 실측으로 대신한다. 시연 장소나 조명이 바뀌면 같은 노출 스윕(`exposure_sweep.py`)을 다시 돌린다.

## #7 벨트 평면 호모그래피 (T16, ADR-0003)
판정 규칙은 측정 전(10/07 재측정 절차서)에 확정: **검증점 5곳 모두 ≤ 5 mm**. 결과를 본 뒤 점을 빼지 않는다.

| 구분 | 점 | 출처 |
|---|---|---|
| 계산점 10 | C1~C6 | 10/06 (김학민, 화면 하류 절반) |
| | C7·C8·C9·C10 | 10/07 재측정 (김학민). C8 은 사진 뒤 박스가 약 3.5 mm 밀려 현장에서 **C8_2** 로 다시 잼 |
| 검증점 5 | V1·V2 | 10/06 |
| | V3R·V4·V5 | 10/07. V5 는 하류 한계로 x 0 |
| 제외 | V3 (10/06) | 6.97 mm, 벨트 방향 −6.6 mm 치우침 — 사진·터치 사이 박스 이동 의심. 10/07 V3R 로 대체 |
| | C8 첫 시도 (10/07) | 사진 뒤 이동(사진→chk 송장 중심 14 px) |

- **결과:** 검증 V1 2.32 · V2 2.48 · V3R 2.63 · V4 1.66 · V5 1.66 mm → 최대 **2.63 mm 합격**. 계산점 RMS 1.70 mm. 접촉점 z 평균 100.8 mm, 범위 1.8 mm(≤ 3). 터치 툴축 − 관측 툴축 최대 1.0°(경고 2° 이내, 관측 자세 자체가 수직에서 0.93°).
- **두 날을 섞어도 되는 근거:** 10/07 OBS 펜던트 posx 가 10/06 과 0.18 mm·0.02° 차, 빈 벨트 E0 vs 10/06 C1 화면 이동 1.3 px(≤ 2 px), 카메라 설정·K 같음, TCP 등록 (1.382, 2.684, 246.642) 같음.
- **박스 그대로였는지:** 10/07 점마다 터치 뒤 OBS 로 돌아와 다시 찍은 `_chk` 와 송장 중심 차 0.3~1.9 px(약 0.1~0.5 mm).
- **픽셀:** 송장 흰 영역 자동 검출 중심(사람이 겹쳐 그린 그림으로 15장 확인). 터치는 송장 가운데를 눈으로 맞춤(± 2~3 mm) — 계산점 RMS 1.70 mm 에는 이 터치 오차가 들어 있다.
- **유효 범위(`calib_hull_px`):** 박스 윗면 중심 기준 베이스 x **−100 ~ +3 mm(약 103 mm)**, y −294 ~ −257 mm. 상류 끝은 로봇 도달 한계, 하류 끝은 화면 아래 끝. 벨트 4.8 cm/s(h250)에서 약 **2.1 s**, 2.47 cm/s(h500)에서 약 4.2 s. 밖은 `position_valid=false`.
- **결과 파일:** `config/belt_homography.yaml` (관측 자세 정지 전용). 원본 사진·기록은 Drive `raw/1006/`, `raw/1007/`.
- **정식 핸드아이(이동 중 좌표, G0 필수)** 는 별도 측정이다(ADR-0003 갱신 절).
