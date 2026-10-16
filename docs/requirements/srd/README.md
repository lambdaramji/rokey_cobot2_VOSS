# VOSS SRD v2.0 (잠정)

**작성일:** 2026-10-16(KST) · **상태:** 잠정 — 작성자 검토 중, 팀 기준선 승인(PL)·담당자 확인 전 · **기준:** BRD v1.7 레포판(PR old#166), main `fe11ded`

Sprint 2(팔레타이징·음성 시스템 기동·추종·파지 고도화)와 10/15 시연 뒤 상태를 반영한 시스템 요구사항 명세와 근거 자료다. ISO/IEC/IEEE 29148:2018 SyRS 참고 구성과 v1.0 의 ID 를 유지하고(삭제·재사용·폐기 없음) 신규 SYS 26·VT 26·IC 3·TBD 9·F 2 를 붙였다. 요구사항마다 기준 시점의 구현·검증 상태와 증거 출처를 적었다.

| 읽을 자료 | Markdown | Word |
|---|---|---|
| 배포·사용 안내 | [00 안내](markdown/00_배포_사용안내.md) | [Word](word/00_배포_사용안내.docx) |
| **SRD v2.0 본문** | [01 SRD](markdown/01_VOSS_SRD_v2.0.md) | [Word](word/01_VOSS_SRD_v2.0.docx) |
| v1.0 → v2.0 변경 대장 | [02 변경 대장](markdown/02_v1.0_v2.0_변경대장.md) | [Word](word/02_v1.0_v2.0_변경대장.docx) |
| 남은 결정·구현·실측(F-01~18) | [03 후속 대장](markdown/03_남은_결정_구현_실측_대장.md) | [Word](word/03_남은_결정_구현_실측_대장.docx) |
| 96개 요구사항 검증 추적표 | [04 검증 추적표](markdown/04_검증_추적표_v2.0.md) | [Word](word/04_검증_추적표_v2.0.docx) |
| BRD v1.3 → v1.7 대조 | [05 BRD 대조](markdown/05_BRD_v1.3_v1.7_대조기록.md) | [Word](word/05_BRD_v1.3_v1.7_대조기록.docx) |

- [근거 자료](sources/README.md) — fe11ded 계약 사본, 작성 원자료(P1) · [문서 검증 결과](문서검증결과.json) · [파일 해시](파일해시_manifest.json) · [manifest](manifest.json)
- 그림(배포·논리 구성도)은 아직 넣지 않았다. 본문 부록 F 의 자리에 추후 넣는다.
- **이전 판:** [v1.0 (2026-10-07, BRD v1.3 기준)](archive/v1.0/README.md) — 원문·해시 그대로 옮겼다(`archive/v1.0/파일해시_manifest.json`). [v0.2-r2](archive/README.md)
- v1.0 안의 옛 링크(`yujh5537` → `lambdaramji` 넘겨 주기)와 이슈 번호는 고치지 않았다. v2.0 의 근거 번호는 `old#n`(lambdaramji/rokey_cobot2_VOSS)·`_2#n`(임시 레포 rokeyhak/rokey_cobot2_VOSS_2, ADR-0015)으로 구분한다.

## 확정까지 남은 일

본문 부록 A 절차를 따른다: 담당자 확인(02 의 수정·신규 카드) → TBD-027~035 결정 → 문서 검증(ID·추적·계약 대조·독립 재검) → PL 기준선 승인 → "(잠정)" 제거·Word·manifest 생성.
