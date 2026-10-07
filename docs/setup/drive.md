# 팀 Google Drive 구조와 규칙

레포에 넣지 않는 것(규칙 8: 녹화·촬영 원본, 학습 세트, 모델 가중치, 발표·결과 영상)은 팀 Drive 한 곳에 둔다. **팀 공용 Google 계정** 하나를 모두 로그인해서 쓴다(따로 공유 설정 없음). 루트는 그 계정의 `내 드라이브/rokey_cobot2_VOSS/`. 레포가 공개라 이 문서에는 계정·링크·폴더 ID 를 적지 않는다.

```
rokey_cobot2_VOSS/
├─ README.md            이 문서 사본
├─ docs/
│  ├─ requirements/    BRD 기준판 docx, SRD, 개발일정 — 각 1부
│  ├─ presentations/   1007_중간발표, 1016_최종발표
│  └─ handoff/         MMDD_<이름>_<내용>.md (현장 대리 작업·전달 기록)
├─ raw/                 현장 원본. 올린 뒤 수정·이름 변경·삭제 금지
│  ├─ 1006/            voss_1006_calib_ocr.tar.gz, voss_1006_t17.tar
│  └─ 1007/ …          날짜(MMDD)마다 폴더
├─ datasets/            raw 에서 만든 학습·평가 세트 (버전 접미사 _v1, _v2)
│  └─ t17_yolo_v1/     t17_yolo_v1.zip (train·holdout·holdout_check), check.csv (사람 확인본)
├─ models/              배포 후보 가중치 (.onnx/.pt) — 예 box_yolo11n_v1.onnx
├─ colab/               Colab 작업 공간
│  └─ t17/runs/        학습 체크포인트 (세션 끊김 대비)
├─ results/             측정·게이트·리허설·시연 결과
│  ├─ gate_1008/  gate_1010/  rehearsal/  demo_1015/
└─ reference/           프로젝트 산출물이 아닌 참고자료
   ├─ lectures/  samples/  hardware/
   └─ _archive/        옛 판 (BRD v1.0, 중복 일정표 등)
```

## 규칙
1. **raw 는 날짜로 나누고 지우지 않는다.** 파일명 `voss_<MMDD>_<내용>`. 공용 계정이라 Drive 수정 기록으로는 누가 올렸는지 알 수 없으므로, **올린 사람은 `docs/handoff/` 에 한 줄(누가·무엇을·어디서·어떤 설정으로) 남긴다.**
2. **datasets·models 는 버전을 붙인다.** 파일 설명란에 만든 커밋·명령을 적는다(예: `3fe5371 tools/vision/eval_bag.py --export-yolo …`). 레포 코드는 버전 이름으로만 가리킨다.
3. **문서는 한 부만.** BRD·SRD 원본은 Claude Docs, 기준판 docx 는 `docs/requirements/`. 일정 xlsx 의 기준은 레포 `docs/requirements/`. 옛 판은 `reference/_archive/`.
4. **"링크가 있는 모든 사용자" 로 열지 않는다.** 공용 계정 밖으로 새는 길은 이것뿐이다. 밖(강사 등)으로 보내야 하면 사본을 따로 만들어 보내고 끝나면 닫는다.
5. **Colab:** 같은 계정이라 경로는 모두 `/content/drive/MyDrive/rokey_cobot2_VOSS/…`. 노트북은 `tools/colab/` 이 원본이고 Drive 에는 실행 사본만 둔다. **GPU 할당량도 계정 하나를 나눠 쓰므로 학습은 한 번에 한 명만** 돌리고 Slack 에 알린다.
6. **용량:** 무료 계정이면 팀 전체가 15 GB 를 나눠 쓴다(10/07 기준 raw 만 약 4.1 GB). 원본 bag 은 tar 하나만 두고 같은 파일을 두 번 올리지 않는다. 중간 산출물(크롭·시트)은 개인 PC 에 두고 결과 표·대표 이미지만 올린다.

## 레포에서 가리키는 경로
| 쓰는 곳 | Drive 경로 |
|---|---|
| `tools/colab/t17_yolo_train.ipynb` | 입력 `datasets/t17_yolo_v1/t17_yolo_v1.zip`·`check.csv`, 체크포인트 `colab/t17/runs/`, 출력 `models/` |
| box_tracker `detector: yolo` (10/08 이후) | `models/box_yolo11n_v<N>.onnx` 를 공용 PC `~/voss_ws/models/` 로 내려받아 쓴다 |
| T16 재측정 절차서, 현장 업로드 | `raw/<MMDD>/` |

## 변경 이력
- 2026-10-07: 신설. 사람 이름 폴더(`현지/`)·`project/reference/` 를 이 구조로 정리, 옛 판은 `reference/_archive/` (남현지).
- 2026-10-07: 팀 공용 계정 기준으로 고침 — 공유·바로가기 규칙 삭제, 올린 사람 기록·Colab GPU 할당량·15 GB 용량 규칙 추가.
