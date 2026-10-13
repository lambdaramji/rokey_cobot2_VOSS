# Sorting Workspace 파지·운반 표시 계약 제안 (승인 대기)

상태: **남현지·김학민·정의석 승인으로 이벤트 전달 코드 반영; 실측 오프셋 미확인으로 LIVE 운반 박스 위치 표시 보류.** 기존 `BoxTrack`, `/voss/robot/pose`, `SortState`, `SortResult`, DB 집계의 의미는 유지한다. 로봇 제어에는 사용하지 않는다.

## 기존 신호의 한계

- `SortState.track_id`는 처리 중인 비전 트랙을 가리키지만, `PICKING`은 파지 성공을 뜻하지 않는다. `TrackAndGrasp.Result(grasped=true, reason=OK)`는 manager만 받으며 웹으로 전달되지 않는다. manager는 이 결과와 현재 `box_id`·`session_id`·`track_id`를 연결할 수 있다.
- `MoveToZone.Response.placed_stamp`는 그리퍼 개방 완료 시각이지만, PLACE 서비스 응답은 OBSERVE 복귀 **후** manager에 도착한다. `SortResult.stamp`가 이 시각을 담더라도 웹은 개방 순간과 복귀 구간을 실시간으로 구분할 수 없다. `SortResult`만으로 파지 성공도 알 수 없다.
- `RobotState.action`·그리퍼 폭이나 TCP와 박스의 거리, BoxTrack 중단은 파지·개방 성공 신호가 아니다.
- 현재 `MoveToZone`의 RECHECK `PICK` 모드는 gateway에서 `NOT_CONFIGURED`로 거부된다. 재확인 구역 재파지 표시는 그 동작이 구현·검증된 뒤 별도로 다룬다.

## 승인된 최소 추가 계약

1. 새 `BoxMotion` 이벤트를 같은 ROS 토픽 `/voss/box_motion`에 발행한다. 필드: `session_id`, `box_id`, `track_id`, `phase` (`GRASPED` 또는 `RELEASED`), `stamp`, `zone`. `GRASPED`는 manager가 해당 goal의 `reason=OK && grasped=true`를 확인한 뒤 한 번만 발행한다. `RELEASED`는 gateway가 해당 PLACE의 RG2 개방 성공 직후 `placed_stamp`로 한 번만 발행한다. `zone`은 RELEASED에서 실제 요청 구역, GRASPED에서 빈 문자열이다. 재시도·중복 이벤트는 `(session_id, box_id, phase, stamp)`로 식별한다.
2. gateway가 RELEASED에 원래 박스 ID를 실을 수 있도록 `MoveToZone.Request` 끝에 `session_id`, `box_id`, `track_id`를 추가한다. manager가 PLACE 요청에만 현재 값을 채운다. ID 없는 외부 요청은 RELEASED 시각화 이벤트를 발행하지 않는다. 기존 구역·슬롯·모드·응답 의미는 유지한다. 이 IDL 변경은 사용 노드의 재빌드가 필요하다.
3. hmi_bridge는 `BoxMotion`을 MQTT `voss/box_motion` QoS 1·retain=false로, Spring Boot는 SSE `box_motion`으로 그대로 전달한다. LIVE 화면은 같은 ID의 GRASPED에만 박스를 TCP에 연결하고, 같은 ID의 RELEASED에만 분리한다. 불확실하거나 누락된 이벤트는 성공으로 추정하지 않는다. 기존 `SortResult`·`by_zone`은 수량 갱신과 늦은 정리에만 사용한다.
4. BoxTrack의 `position_base`는 박스 **윗면 중심**, PoseStamped는 `base_link`의 **TCP 핑거 끝**이다. 정확한 부착 위치에는 검증된 `T_tcp→box_top_center`가 필요하다. 기존 `robot_pose` JSON에 PoseStamped의 orientation을 전달하고, 프론트는 검증된 `VITE_VOSS_TCP_BOX_TOP_OFFSET_MM=x,y,z`와 `VITE_VOSS_BOX_OFFSET_VERIFIED=true`가 함께 있을 때만 회전된 오프셋을 적용해 운반 박스를 그린다. **현재 실측값이 없으므로 기본 빌드에서는 운반 박스 위치를 표시하지 않는다.** 오프셋·단위·축·보정 방법은 비전·로봇 담당자가 실측으로 확인해야 한다.

## 승인 및 구현 경계

- 남현지(manager·비전): goal 결과와 ID 연결, `BoxMotion` GRASPED 발행, PLACE 요청 ID, BoxTrack 기준점·오프셋 확인.
- 김학민(robot gateway): ID 수용과 RG2 개방 성공 시 RELEASED 발행, `placed_stamp`·TCP 좌표계 확인.
- 박병후(servo): `grasped=true`가 LIFT·VERIFY 완료라는 기존 의미와 박스 상대 위치 검증에 대한 확인. servo 변경은 제안하지 않는다.
- 정의석(웹·MQTT): bridge→MQTT→SSE 전달 및 LIVE 표시, DEMO 분리, DB 전용 Truck 수량 유지.
- `interface` 라벨 PR에 이 계약과 ROS 메시지·서비스 해시 변경을 포함한다. 운영 배포·실로봇 실행은 이 변경에 포함하지 않는다. 미완료: 실측 오프셋 검증, RECHECK `PICK` 구현·검증.
