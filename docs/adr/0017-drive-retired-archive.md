# ADR-0017: 팀 Drive 를 닫고 기록을 레포(`archive/`)와 GitHub Release 로 옮긴다

- 날짜: 2026-10-18
- 상태: 승인됨 (PL 남현지 결정, 10/18)
- 결정자: PL 남현지
- 관련: `docs/setup/drive.md`(폐기), CLAUDE.md 규칙 8, ADR-0015(레포 이전)

## 배경
- 프로젝트가 끝났다(10/15 시연, 10/16 발표). 팀 공용 Google 계정의 Drive(`rokey_cobot2_VOSS/`)를 없애기로 했다.
- Drive 에는 규칙 8 때문에 레포에 넣지 않은 현장 원본(bag tar·사진·로그), 학습 세트·모델, 인수인계 md 가 있다. 레포 문서(measurements·ADR)가 그 경로를 근거로 가리킨다.
- 공용 PC 는 이미 반납했다. 공용 PC `~/voss_data` 에만 있던 원본은 복구할 수 없다(아래 '결과').

## 결정
1. **글·표·작은 그림은 git 의 `archive/` 로** 옮긴다 — Drive 경로를 그대로 따라 `archive/drive/…`, 개인 PC 에만 있던 것은 `archive/local/…`. 목록·출처·뺀 것은 `archive/README.md`.
2. **큰 바이너리(bag tar·mcap·데이터셋 zip·가중치·틱 로그·이미지 묶음)는 GitHub Release `drive-archive-20261018` 의 자산으로** 올린다. git 은 파일 하나 100 MB 를 넘지 못하고, 넣으면 모든 클론이 수 GB 를 받는다. Release 자산은 하나 2 GiB 미만이라 3.97 GB `voss_1006_t17.tar` 는 두 조각(`cat part0 part1 > voss_1006_t17.tar`)으로 나눈다. 자산마다 SHA-256 을 `archive/README.md` 와 자산 `SHA256SUMS` 에 적는다.
3. **CLAUDE.md 규칙 8 은 유지**한다(가중치·녹화를 git 에 커밋하지 않는다) — 보존본 위치만 Drive → Release 로 바꾼다.
4. **옮기지 않는 것**: 남이 만든 자료(강의 PDF, 수업 샘플 zip, 컨베이어 판매 페이지 PDF — 공개 레포라 저작권), 레포·Release 에 이미 같은 파일이 있는 사본, 중간 체크포인트(`epoch*.pt`), 빈 폴더·0 바이트 로그.
5. 공개 레포이므로 옮기기 전에 모든 텍스트(로그·md·csv·yaml·docx·xlsx 와 tar 안 텍스트)에서 키·토큰·비밀번호·Drive 링크를 검사했다 — 없음. 나오는 IP 는 실습실 사설 주소 192.168.1.x(이미 레포에 있음, ADR-0015)와 doosan-robot2 기본값 `rt_host 192.168.137.50` 뿐이다.

## 고려한 대안
- A: 전부 git(LFS 없이) — 100 MB 넘는 파일 9개가 들어가지 않고 클론이 7 GB 가 된다. 기각.
- B: Git LFS — 무료 저장·대역폭 한도가 작고 클론마다 대역폭을 쓴다. 기각.
- C: Drive 를 개인 계정으로 옮겨 유지 — 팀이 접근할 곳이 다시 한 사람 계정에 묶인다. 기각.

## 결과
- `docs/setup/drive.md` 는 폐기 표시와 "옛 Drive 경로 → 새 위치" 표만 남긴다. 문서 속 `Drive raw/<MMDD>/…` 는 그 표로 찾는다.
- **복구할 수 없는 것(공용 PC 반납)**: 10/10 bag 본체(약 60 GB — Drive 에는 `metadata.yaml` 과 LOST 3건 클립만), 10/12 손목 bag `u9_s2_bag_C`, 10/13 Sprint 2 게이트 녹화 `s2gate_pal`·`s2gate_rows.md`, 10/14 yaw 관측 이동 bag `C_moving`(metadata 만), 10/15 T19 1차 실기 `t19s2/`, 10/15 J6 회전 실기 `u14/`, 10/15 시연 1회차 `demo`. 값은 measurements·ADR 에 적힌 것이 전부다.
