# 아키텍처 도면

레포 코드(`src/`·`docker/`·`config/`·`scripts/`) 기준으로 그린 도면 6장. Weld-Made(협동-1) 의 Archify 도면과 같은 시각 언어(다크 · 존 · 번호 붙은 선 · 범례)로 맞췄다.

| 파일 | 내용 | 원본 |
|---|---|---|
| `01_system` | 시스템 배포 아키텍처 — 공용 PC 호스트 프로세스 12 · 컨테이너 5종 · 로봇 셀 6 · Web PC · 외부, 연결 S1~S31 (프로토콜 · 포트 · 버전) | `gen_01_system.py` → SVG/PNG |
| `02_ros2` | ROS 2 통신 아키텍처 — 노드 10 · 외부 6 · 인터페이스 R1~R41 (토픽 · 서비스 · 액션 · HTTP · MQTT · Modbus, 타입 · 주기 · QoS) | `gen_02_ros2.py` → SVG/PNG |
| `03_control_loop` | 30 Hz 제어 루프 — 카메라 → box_tracker → belt_servo FSM → robot_gateway guard → speedl_stream → 로봇 → pose 피드백 | `03_control_loop.mmd` (Mermaid) |
| `04_flow` | 전체 공정 플로우차트 — sort_manager 상태 전이 · 박스 한 개의 여정 · 예외(재확인 · 질문 · 보류 · stop · 구역 가득) · 팔레타이징 | `04_flow.mmd` |
| `05_human_record` | 사람 · 기록 경로 — 음성(VAD → Whisper → 호출어 → intent → 검증 → FSM → TTS) · 웹(REST → MQTT → bridge → srv) · DB | `05_human_record.mmd` |
| `06_erd` | ERD — sort_log 19 · pallet_log 16 · session_plan 3 컬럼, 제약 · 논리 참조 | `gen_06_erd.py` → SVG/PNG |

```bash
pip install cairosvg                      # SVG → PNG (폰트: fonts-noto-cjk)
python3 gen_01_system.py && python3 gen_02_ros2.py && python3 gen_06_erd.py
npm i -g @mermaid-js/mermaid-cli          # 03 · 04 · 05
for f in 03_control_loop 04_flow 05_human_record; do mmdc -i $f.mmd -o $f.png -c theme.json -b '#020617' -s 2 -w 2200; done
```

`archlib.py` 가 공통 스타일(노드 종류별 색 · 선 종류 · 존 · 라벨 · 범례)을 가진다. 노드·선은 좌표를 직접 적는다(자동 배치 없음) — 노드를 옮기면 그 노드에 닿는 선의 끝점도 같이 옮긴다.

이름·수치가 바뀌면 `docs/interfaces/`·`docs/architecture.md` 와 함께 고친다(코드와 다르면 문서가 틀린 것). 선 번호(Sn · Rn)는 README 의 등록표와 같다.
