# Sorting Workspace 6축 관절 표시 계약 제안

상태: **승인 (10/14 #37 PL 리뷰, 표시 전용)**. 2026-10-13 김학민(로봇)·정의석(웹·MQTT)·남현지(PL) 구두 승인 전달(정의석). 운영 배포는 이 문서의 범위 밖이다.

- 기존 소스: `/dsr01/joint_states` (`sensor_msgs/JointState`). `name` 배열에서 `joint_1`…`joint_6`을 이름으로 찾아 읽는다. `position` 단위는 ROS 규약의 **rad**이며 `header.stamp`는 원본 측정 시각이다. 원본은 약 100 Hz; bridge는 최대 20 Hz로 샘플링한다. 이름 누락, 길이 불일치, 비유한값, bridge 시계와 1초 넘게 차이 나는 시각(과거·미래)은 폐기한다.
- 신규 표시 전용 MQTT: `voss/robot_joints`, bridge write/web read, QoS 0, retain=false. JSON: `{"stamp":"ISO-8601","frame_id":"base_link","name":["joint_1",…,"joint_6"],"position":[rad 6개]}`. `position`은 `name` 순서에 대응하며 이름별 정렬을 강제한다. 명령이나 DB로 연결하지 않는다.
- Spring Boot는 JSON 객체를(필드 검증은 브라우저) SSE `robot_joints`로 전달하며 저장·재전송하지 않는다. 브라우저는 수신 시각 0.5초 이내를 최신으로 표시하고, 이후 마지막 FK 자세를 고정하고 갱신 중단을 표시한다. 최초 수신 전 LIVE에는 6축 팔 자세를 그리지 않는다.
- FK 모델: 기존 RViz2 `scene.urdf.xacro`가 포함하는 `m0609_rg2_bringup/urdf/m0609_with_rg2.urdf.xacro` → `dsr_description2/urdf/m0609.urdf`의 `base_link`→`joint_1`…`joint_6`→`tool0`. SVG는 URDF 관절 원점·축·길이를 X/Y 상면으로 투영한다. `tool0`은 플랜지 프레임이며 `/voss/robot/pose`의 핑거 끝 TCP와 동일하다고 주장하지 않는다.
- 기존 BoxTrack, TCP PoseStamped, 박스 운반 오프셋, `by_zone` DB 집계 계약은 그대로 유지한다. 모델 버전 또는 로봇 프레임이 바뀌면 FK 상수와 검증값을 함께 재검토한다.

## 변경 이력
- 2026-10-13: 초안 (T13 #37, 정의석).
- 2026-10-14: #37 PL 리뷰 — 승인(표시 전용), 시각 검사 문구를 코드와 맞춤.
