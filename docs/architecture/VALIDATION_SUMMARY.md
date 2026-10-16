# 검증 요약

기준 코드 `70463ef435b50b45d243823b6f7318789728d786`, Archify 3.1.0 `f8021f7eee6870a552bbad3373cf6bad32c80f37` + 문서에 포함된 UI/도형 확장 패치. 아래 결과는 실제 실행 기록만 적었다. `pass`는 자동 게이트/조작이 실행되어 성공한 경우, `skipped`는 의도적으로 실행하지 않은 경우, `unconfirmed`는 결과를 확인할 수 없는 경우다.

| 결과물 | JSON/참조·레이아웃 validate | HTML deliver | provenance check | Chrome browser-check | SVG XML/PNG decode | 시각 확인 |
|---|---|---|---|---|---|---|
| 01 System | pass | pass | pass | pass | pass | pass |
| 02 ROS 2 | pass | pass | pass | pass | pass | pass |
| 03 ERD | pass | pass | pass | pass | pass | pass |
| 04 Flow | pass | pass | pass | pass | pass | pass |

각 `*.finalize-summary.json`에 네 게이트 상태가 있고, `*.finalize.json`, `*.delivery.json`, `*.browser-check.json`에 세부 증빙이 있다. `finalize`가 `validate → deliver → check → browser-check`를 실행했다. 04 Flow의 도형은 공식 3.1.0 기본 schema에 없어서 `renderer-extension/archify-voss-ui-shapes.patch`를 적용하고 validator를 재생성한 Archify 3.1.0으로 검증했다. 사용한 명령은 각 도면에 대해 다음 형식이다.

```sh
node /tmp/voss-archify/archify/bin/archify.mjs finalize <architecture|erd> docs/architecture/data/<name>.json docs/architecture/<name>.html --repo-root . --quality standard --json
```

`01_system`, `02_ros2`, `04_flow`는 `architecture`, `03_erd`는 `erd` 유형이다. 처음 생성한 후보는 ERD 필드 폭 및 일부 연결 라벨 겹침으로 `validate=fail`이었고 JSON의 라벨 위치/테이블 폭을 수정해 위의 최종 pass 상태를 얻었다. 01 System과 02 ROS 2는 실제 반환 흐름을 반대 화살표로 추가한 뒤, Web PC/Robot PC 물리 경계를 교정해 각각 `evidence/system-live-v5`, `evidence/ros2-live-v5`에서 다시 검증했다. 두 노란 경계는 PNG에서 겹치지 않음을 확인했다. 이전 receipt는 `evidence/*-direction-v1`에 보관했다. 03 ERD는 `evidence/erd-logical-relations-v4`에서 점선 논리 관계 3개와 0..1 대 0..N 표기를 재검증했다. 관계선 라벨은 `box_id`/`session_id`만 남겼다. 04 Flow는 도형 의미를 맞추고 Live 기본값을 적용한 뒤 `evidence/flow-shapes-live-v4`에서 다시 finalize했다. 최종 receipt 원본은 해당 디렉터리에 있으며 루트에도 사본을 두었다. 이전 후보의 receipt는 `evidence/flow-review-1`에 보관했다. 최종 pass는 `standard` 품질 프로필 기준이며 `showcase` 통과를 주장하지 않는다. 독립적인 standalone `validate`/`check` 명령은 최종 후보에 별도로 실행하지 않았고, `finalize`에 포함된 게이트 결과를 기록했다.

SVG/PNG는 `renderer-extension/export_assets.py`를 실제 실행해 HTML의 SVG를 추출하고 Chrome으로 PNG를 만들었다. 네 SVG는 XML parse, 네 PNG는 Pillow decode/verify에 `pass`했다. PNG는 native Viewer Export 다운로드가 아니다.

Chrome 1440×900에서 `index.html` 기본 화면을 열어 `evidence/workspace-desktop.png`로 캡처하고 시각적으로 확인했다. 네 PNG도 직접 살펴보았다. 01 System과 02 ROS 2의 PC 경계 및 화살표, 03 ERD의 논리 관계선, 04 Flow의 도형을 최종 PNG에서 육안 확인했다. Chrome에서 네 독립 HTML의 첫 실행 Live 상태 및 연결선 흐름을 확인했다. Still 선택은 새로고침 뒤에도 유지되고 Live로 복귀할 수 있으며, 운영체제의 reduced motion 설정도 존중한다. Playwright로 실제 Chrome에서 01→03→01 탭 전환, 125% 확대율 유지, 래퍼·내부 Viewer 라이트 테마 동기화, JS pageerror 0건을 확인했다 (`evidence/viewer-interaction.json`). 동적 연결선·토글 유지·reduced motion 검증은 `evidence/motion-and-relations-browser.json`에 기록했다. 개별 Archify `browser-check`도 네 도면에서 pass다. 이는 화면 기하·기본 조작의 증거이며 모든 UI 조합의 완전한 시험을 뜻하지 않는다.

| 항목 | 상태 | 이유 |
|---|---|---|
| 네 JSON의 소스 경로·커밋 검증 | pass | Archify `--repo-root .` finalize |
| Topic/Service/Action 실제 현장 송수신 | unconfirmed | ROS 장비와 서비스를 기동하지 않음 |
| 실제 DB migration/행/권한 | unconfirmed | 운영 DB에 연결하지 않음 |
| 모바일 터치/패널 전환 | unconfirmed | 모바일 실기 조작을 하지 않음 |
| Viewer의 네이티브 PNG/SVG 다운로드 완료 | unconfirmed | 메뉴 기능은 Viewer에 있으나 다운로드 조작 시험을 하지 않음 |
| `visual-check` CLI screenshot gate | skipped | 별도 게이트 대신 실제 PNG/통합 페이지를 Chrome으로 캡처해 직접 검토 |
| GitHub push/외부 배포 | skipped | 요청 범위 밖 |

남은 주요 제한: 두 PC 배치는 사용자가 제공한 10/16 실행 기록과 10/14 런북 기준이며, 현재 계속 실행 중인지와 외부 로봇·카메라·음성 장치 연결은 재관측하지 않았다. ERD는 코드의 DDL을 기준으로 하며 운영 DB 상태를 보증하지 않는다. 공정 도면은 주요 분기만 표시한다. PAUSED `resume`의 복귀 지점은 저장된 단계에 따라 달라 하나의 고정 연결선으로 표시하지 않았다.
