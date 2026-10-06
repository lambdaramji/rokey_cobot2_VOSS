# 10/06 실측·확인 체크리스트

값은 **여기에만** 적는다. voss_config.yaml·SRD·ADR은 이 파일을 참조한다.

| # | 항목 | 담당 | 결과 (값·단위) | 관련 SR | 완료 |
|---|---|---|---|---|---|
| 1 | 벨트 속도: 아두이노 설정값별 cm/s 표, 10 cm/s 이하 설정 확인 | 김학민 | | SR-HW-04, SR-FN-04 | ☐ |
| 2 | 두산 컨트롤러 DRCF·doosan-robot2 버전 | 김학민 | | SR-HW-01, SR-SW-04 | ☐ |
| 3 | 서보 스트리밍 토픽(servol_stream 계열) 유무, 주기 | 박병후 | | SR-IF-09 | ☐ |
| 4 | RG2 제어 경로 확인 (Modbus TCP 192.168.1.1:502 응답 / 드라이버) | 김학민 | | SR-HW-02, SR-SW-05 | ☐ |
| 5 | 공용 PC GPU 모델·VRAM·RAM, USB 3.0 포트 수, NIC 2개 | 정의석 | MSI Katana 17 B13VFK / Ubuntu 24.04.5 / RTX 4060 Laptop 8 GB (드라이버 595.91.07, CUDA 13.2) / RAM 32 GB / USB3 3개 (ACPI 기준, 육안 확인 전) / 유선 RTL8111 + Wi-Fi O. 상세: [아래 5번](#5-공용-pc-사양-상세-sr-hw-09) | SR-HW-09 | ☐ |
| 6 | 작업대 치수, 로봇 베이스 위치·높이, 5구역 좌표(posx) | 김학민 | | SR-HW-08 | ☐ |
| 7 | 핸드아이 캘리브레이션 검증점 오차 (mm) | 남현지 | | SR-FN-02 | ☐ |
| 8 | 종이 박스 무손상 RG2 파지력·폭 | 김학민 | | SR-HW-02 | ☐ |
| 9 | 시연장 조도, 보조 LED 필요 여부, 노출 5~8 ms 확인 | 김학민 | | SR-HW-12 | ☐ |
| 10 | 내장 마이크 1 m 호출어 인식 | 정의석 | | SR-HW-11 | ☐ |

## 벨트 설정값-속도 표
| 아두이노 설정값 | 실측 cm/s (3회 평균) | 비고 |
|---|---|---|
| | | |

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
| NIC | 유선 1 + Wi-Fi 1 | 유선 Realtek RTL8111 `enp4s0`, Wi-Fi Intel CNVi `wlo1` (Rokey_A) | 충족 |
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
9. 기타
   - `nvidia-driver-595`, `docker-ce`, `docker-ce-cli`, `containerd.io`가 apt hold 상태다. 일부러 고정한 것으로 보이니 그대로 둔다.
   - `nvidia-smi` 전력 값이 `590W / 80W`로 비정상 표시된다. 센서 값 오류로 보이며 동작에는 영향이 없다.
   - Wi-Fi 절전이 켜져 있다 (`default-wifi-powersave-on.conf`). 개인 PC와 DDS로 통신할 때 지연이 튀면 의심한다.
   - BRD 6.1 장비 표에는 "USB 마이크", 배포 구성에는 "내장 마이크"로 적혀 있어 서로 다르다. #10 결과를 보고 하나로 맞춘다.

<details>
<summary>원본 출력 (MAC 주소는 가림)</summary>

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
wlo1    UP  172.24.3.240/22   Rokey_A
nmcli connection: Wired connection 1 (enp4s0) manual 192.168.1.10/24 gw 192.168.1.1
                  Wired connection 2 (enx…, USB 랜) manual 192.168.1.10/24 gw 192.168.1.1
ip route: default via 172.24.0.1 dev wlo1 metric 600
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
