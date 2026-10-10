# U6' 게이트 집계 — gate_summary 현장 사용법

- 이슈 #13 (G1 게이트) · 판정 기준 [docs/g1-gate.md](../../../docs/g1-gate.md) · ADR-0002 · 작성 2026-10-10
- 하는 일: belt_servo 시도 로그(`<log.dir>/attempts/servo_attempts_*.jsonl`, GOAL_END 행 1개 = 사례 1건)를 읽어 g1-gate 3절 **회차 기록표와 같은 11열** 표 + 5절 "측정:" 문장 + 자동 힌트 표를 Markdown 으로 낸다.
- 로그만 읽는다. 로봇·벨트·그리퍼를 움직이지 않는다(ROS 노드도 띄우지 않는다).

## 현장 명령 (공용 PC, 레포 루트에서)
측정 중 중간 확인 — 화면에만 낸다:
```bash
ros2 run voss_servo gate_summary data/servo --since 2026-10-10T14:05 --series s1
```
측정이 끝난 뒤 — 무효를 지정하고 틱 요약까지 넣어 measurements 끝에 붙인다:
```bash
ros2 run voss_servo gate_summary data/servo --since 2026-10-10T14:05 --series s1 --ticks data/servo --exclude <goal_id 앞 8자리> --md docs/measurements-1010.md
```
- `data/servo` 는 belt_servo 기동 때 준 `log_dir:=` 와 같은 폴더다(attempts 파일이나 attempts 폴더를 직접 줘도 된다).
- `--since` = "본 측정 시작"을 말한 시각(시간대를 안 쓰면 KST). 그 전에 끝난 goal 은 연습으로 보고 표·분모에서 뺀다. **선언은 goal 과 goal 사이에** 한다(goal 이 끝난 시각으로 나눈다).
- `--exclude` = 무효(g1-gate 1절 두 경우, 사람 판단). 표에 "무효"로 남고 분모 칸은 쓰지 않는다(다음 goal 이 그 번호를 받는다). goal_id 는 아래 자동 힌트 표 두 번째 열의 앞자리를 쓴다.
- `--md` 는 파일 끝에 **붙인다**(기존 내용 유지). 두 번 돌리면 두 번 붙으니 붙인 뒤 확인한다.
- main 해시는 `git rev-parse --short HEAD` 로 채운다. 다른 커밋으로 돌렸으면 `--main <해시>`.
- 개인 PC 에서 시험할 때: `voss-ros python3 -m voss_servo.gate_summary <jsonl>` (도메인과 무관 — ROS 통신 없음).

## 표를 채우는 규칙
- **원인 열은 비워 둔다. 사람이(박병후) 영상·로그로 판정해 g1-gate 원인 코드(A·T·G·R·L·D·X·S) 하나를 적는다.** 박스(송장)·bag 시각 열도 사람이 채운다.
- 자동 힌트(L·R·G·D·X·?)는 reason·cause 로 고른 **보조**다. 예: GRASP_FAILED → G 로 나오지만 실제로는 접근 오차(A)나 타이밍(T)일 수 있다. DEVICE_ERROR 는 gateway 로그로 D 와 X 를 가른다.
- 성공 ○ = reason OK 이고 grasped true. 영상에서 박스가 안전 높이까지 들렸는지는 사람이 확인한다.
- 요약의 "실패 원인: A __ · …" 줄은 원인 열을 다 채운 뒤 사람이 센다. "설정" 줄의 sha 가 사례마다 다르면(경고로 나온다) 고정 조건이 바뀐 것 → 측정을 멈추고 새 시리즈.
