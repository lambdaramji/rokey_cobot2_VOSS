# voss_hmi — 정의석 (@EuiseokJeongNZ)
노드: hmi_bridge (ROS ↔ MQTT, docs/interfaces/mqtt.md), sort_logger (/voss/sort/result → DB sort_log 1행).
- Mosquitto 는 호스트 1883. 웹 HMI 자체는 docker/web/ 또는 호스트 (미정).
- HMI 반영 ≤ 1초. 결과 1건 = DB 1행.
- 결정 필요: 웹 스택, MQTT JSON, DB 종류 → docs/pending-decisions.md #13·14
