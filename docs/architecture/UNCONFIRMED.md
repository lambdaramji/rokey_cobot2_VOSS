# 미확인 사항

- Web PC와 Robot PC의 배치는 사용자의 10/16 Robot PC 실행 기록 및 10/14 Web PC Runbook으로 확인했다. 현재 프로세스가 계속 실행 중인지, 두 기록의 코드 커밋 차이가 동작에 영향을 주는지는 실기에서 다시 확인하지 않았다.
- Doosan 외부 드라이버, RealSense, RG2 Modbus, 컨트롤러 TCP, 음성 장치와 AI 모델 가중치의 현장 연결을 시험하지 않았다.
- 운영 PostgreSQL의 실제 테이블, migration 적용 여부, 데이터와 권한을 조회하지 않았다. ERD는 저장소 DDL 기준이다. 점선 3개는 값 기반 논리 연관이며 실제 FOREIGN KEY가 아니므로 모든 행의 매칭을 보증하지 않는다.
- Spring의 MQTT adapter는 `VOSS_MQTT_ENABLED=true`일 때만 활성화된다. 브로커와의 실제 연결은 시험하지 않았다.
- `hmi_bridge.py:138`의 `BoxMotion` 구독은 메시지 정의가 현재 `src/voss_msgs/msg`에 없어 조건부 경로이며, 실제 통신은 확인되지 않았다.
- `label_reader`의 Topic/Service는 OCR 준비 및 zone_map 수신 후에 생성된다. 기동 시점의 가용성을 항상 보장하지 않는다.
- 팔레트 2층 사용, 구역 교시, 16칸 운영은 설정과 현장 상태에 달려 있다.
- 통합 뷰어는 데스크톱 Chrome에서 탭·테마·확대 유지 시험을 했다. 모바일 터치 조작과 각 Export 메뉴의 다운로드 완료는 직접 시험하지 않았다.
- PNG는 Archify HTML에서 추출한 SVG를 Chrome으로 렌더한 이미지다. Viewer의 네이티브 PNG Export와 바이트 동일성을 확인하지 않았다.
