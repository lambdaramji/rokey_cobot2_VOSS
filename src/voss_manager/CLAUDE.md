# voss_manager — 남현지 (@lambdaramji)
노드: sort_manager. 상태 IDLE → RUNNING → PICKING → RECHECK → ASKING → PAUSED (docs/architecture.md).
- voss_config.yaml 을 읽고 쓰는 **유일한** 노드. 바뀌면 /voss/sort/zone_map 재발행 (transient_local).
- 상태 전이는 순수 함수 (상태, 이벤트) → (다음 상태, 액션) 로 두고 pytest 로 6상태 전이를 시험한다.
- 로봇은 /voss/servo/track_and_grasp 액션과 /voss/robot/* 서비스로만. 두산 직접 호출 금지.
- OCR 신뢰도 < confidence_min → 재확인 구역 → 재판독 → 미확정이면 ASKING(음성 질문) → 응답 없으면 보류.
- 완료 기준: 6상태 단독 시험 통과, 흐린 송장 박스 완주 3회, 사이클 ≤ 30초.
