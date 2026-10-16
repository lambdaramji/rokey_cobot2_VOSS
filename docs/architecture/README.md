# 아키텍처 도면

레포 코드(`src/`·`docker/`·`config/`) 기준으로 그린 도면 6장. 원본은 Mermaid(`.mmd`)라 텍스트로 고치고, PNG 는 아래 명령으로 다시 만든다.

| 파일 | 내용 |
|---|---|
| `01_system` | 배포 구성 — 공용 PC 호스트 프로세스 · 컨테이너 5종 · 로봇 셀 · Web PC · 네트워크 |
| `02_ros2` | ROS 2 통신 — 노드 · 토픽 · 서비스 · 액션 (입력 → 인지 → 판단 → 실행 → 장치, 사람·기록) |
| `03_control_loop` | 30 Hz 제어 루프 — 카메라 → box_tracker → belt_servo FSM → robot_gateway guard → speedl_stream → 로봇 → pose 피드백 |
| `04_flow` | 공정 플로우차트 — sort_manager 상태 전이 · 박스 한 개의 여정 · 예외(재확인 · 질문 · 보류 · stop · 구역 가득) · 팔레타이징 |
| `05_human_record` | 사람 · 기록 경로 — 음성(VAD → Whisper → 호출어 → intent → 검증 → FSM → TTS) · 웹(REST → MQTT → bridge → srv) · DB |
| `06_erd` | ERD — sort_log · pallet_log · session_plan |

```bash
# mermaid-cli (npm i -g @mermaid-js/mermaid-cli), 한글 폰트 Noto Sans CJK 필요
for f in 01_system 02_ros2 03_control_loop 04_flow 05_human_record 06_erd; do
  mmdc -i $f.mmd -o $f.png -c theme.json -b white -s 2 -w 2200
done
```

이름·수치가 바뀌면 `docs/interfaces/`·`docs/architecture.md` 와 함께 고친다(코드와 다르면 문서가 틀린 것).
