# VOSS SRD v1.0

**게시일:** 2026-10-07(KST) · **관리 이슈:** [#6](https://github.com/yujh5537/rokey_cobot2_VOSS/issues/6)

#50~#55 전체 댓글과 최종 정정을 반영한 시스템 요구사항 명세와 근거 자료다. ISO/IEC/IEEE 29148:2018 참고 구성과 70개 SYS·70개 VT·18개 IC·26개 TBD·34개 MC ID를 유지했다.

| 읽을 자료 | Markdown | Word |
|---|---|---|
| 배포·사용 안내 | [00 안내](markdown/00_배포_사용안내.md) | [Word](word/00_배포_사용안내.docx) |
| **SRD v1.0 본문** | [01 SRD](markdown/01_VOSS_SRD_v1.0.md) | [Word](word/01_VOSS_SRD_v1.0.docx) |
| 34개 MC 합의 종합·근거 | [02 합의 종합](markdown/02_상호확인_합의_종합.md) | [Word](word/02_상호확인_합의_종합.docx) |
| 16개 남은 결정·구현·실측 | [03 후속 대장](markdown/03_남은_결정_구현_실측_대장.md) | [Word](word/03_남은_결정_구현_실측_대장.docx) |
| 70개 SYS/VT 검증 추적표 | [04 검증 추적표](markdown/04_검증카드_70개요구사항_추적표.md) | [Word](word/04_검증카드_70개요구사항_추적표.docx) |
| BRD v1.1/v1.2/v1.3 대조 | [05 BRD 대조](markdown/05_BRD_v1.1_v1.2_대조기록.md) | [Word](word/05_BRD_v1.1_v1.2_대조기록.docx) |

- 전체 자료 묶음이 필요하면 GitHub의 Download ZIP을 쓴다. 폴더와 같은 파일을 한 번 더 담던 ZIP은 PR #77 리뷰에 따라 뺐다(최초 게시본: [7e5e928 ZIP](https://github.com/yujh5537/rokey_cobot2_VOSS/blob/7e5e92859cd452054ad62b7b83f0569ce123e8f2/docs/requirments/srd/VOSS_SRD_v0.3_%ED%95%A9%EC%9D%98%EB%B0%98%EC%98%81_%EC%A0%84%EC%B2%B4%EC%9E%90%EB%A3%8C.zip)).
- [논리 구조도](assets/VOSS_v0.3_논리구조.png) · [상세 구조도](assets/VOSS_v0.3_논리구조_전체.png) · DOT 원본은 같은 폴더 (v0.3에서 그린 책임·경로 그림이며 v1.0에서 바뀐 경로는 없다)
- [6개 이슈 전체 회신·이전 SRD·main 계약/IDL·BRD 근거](sources/) — 기준판 BRD는 [docs/requirements/VOSS_BRD_v1.3.docx](../VOSS_BRD_v1.3.docx)(#79), v1.2 Word는 [git 기록 e8dd5e5](https://github.com/yujh5537/rokey_cobot2_VOSS/blob/e8dd5e5/docs/requirements/VOSS_BRD_v1.2.docx)에 있다
- [문서 검증 결과](문서검증결과.json) · [원본 파일 해시](파일해시_manifest.json) · [합의/출처 manifest](manifest.json)
- [PR #56의 v0.2 자료 보관](archive/) — 이전 회신 원문·취합 양식·초안 등 45개 중 ZIP 2개를 뺀 43개 파일을 원본 그대로 보존(ZIP 2개는 PR #56 head 고정 링크)

## 현재 상태와 다음 작업

v1.0은 6개 상호확인 합의, PR #77 리뷰, 독립 재검 채택분, main@671c67f 재대조를 반영한 **기준 문서**다(작업 중 v1.0로 부르던 판). 당분간 이 판을 기준으로 삼고, 이후 변경은 SRD §9.2 절차로 v1.x에 기록한다. 팀 전체 기준선 승인(PL, #6), 런타임 구현, 실기 수락은 각각 기록한다. RETURN_FAILED 업무 결과·HOLD/RECHECK 용량·T34 파지 수치·stop 호출 주체·manager 로그·질문 회차·미반영 IDL·실측은 03 후속 대장에서 관리한다.

A 실제 1박스 흐름을 먼저 연결한다. B 음성·HMI·예외·이력 등은 최종 필수이며 C 규칙 변경·신규 구역 교시는 G0 이후 선택한다. 첫 실기 실험/실측 목표는 10/07, 실제 인식→이동 중 픽업→적재→DB commit/동일 box 조회→복귀 G0 통과 목표는 10/10이다.

본문 대조 기준은 main@`671c67f3a5e4f1de46dec3f34b4cf2975727c975`이다(v0.3은 fff1121). `sources/current_main/`은 그 시점 계약 사본 19개이며 실행 계약의 실제 변경은 `docs/interfaces/`·`src/voss_msgs/`·설정/구현 담당 PR에서 동기화한다. 이번 문서 게시가 미반영 IDL·미수행 실측의 완료를 뜻하지 않는다.

`markdown/00_배포_사용안내.md`의 “#6/#56을 갱신하지 않았다”는 v0.3 작성 시점 기록이다. 게시 이후 진행 상태와 PR 연결은 이슈 #6에서 확인한다. `sources/열린_PR68_web_api_참고.md`·`열린_PR70_파지방향_선택보고.json`은 v0.3 작성 당시 열린 PR 기록이며 두 PR은 이후 머지됐다. 저장 위치는 `docs/requirements/srd/`이며 `docs/requirements/README.md`에서 링크한다. PR #77 첫 커밋(7e5e928)의 `docs/requirments/`는 의도하지 않은 철자 오타여서 리뷰에 따라 옮겼다.
