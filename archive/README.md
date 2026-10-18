# archive — 팀 Drive·개인 PC 기록 보존본 (2026-10-18)

프로젝트를 마치며 팀 Drive 를 닫았다(ADR-0017). Drive 와 개인 PC 에만 있던 기록을 여기(git)와 GitHub Release `drive-archive-20261018` 로 옮겼다. **값의 근거는 여전히 `docs/measurements-*`·`docs/adr/*`** 이고, 이 폴더는 그 원자료다. 옛 문서의 `Drive raw/<MMDD>/…` 는 `docs/setup/drive.md` 맨 위 대응표로 찾는다.

## 구조
| 경로 | 내용 |
|---|---|
| `drive/` | Drive `rokey_cobot2_VOSS/` 의 글·표·작은 그림 — Drive 경로를 그대로 따른다. bag 폴더는 `metadata.yaml`(토픽·메시지 수·길이)만 |
| `drive/raw/<MMDD>/` | 현장 원자료: csv·yaml·md·txt·노드 로그(`1010/logs/ros_log`, 0 바이트 로그는 뺌)·현장 도구 py(`1010/*.py`, `1012/u9_tools/`)·사진(`1008/recheck_view`·`g0A_ocr_playback`, `1012/u9_frames`, `1014/yaw_obs/*_frames`) |
| `drive/docs/handoff/` | 현장 대리 작업·인수인계 md(10/06~10/13), 레포 이전(ADR-0015) 순서·번들 안내, `_2` 후속 패치 |
| `drive/colab/t17/` | YOLO 학습 결과표·그림(`runs/t17_y11n/results.csv`·`args.yaml`·곡선), 출력이 남은 옛 노트북 `t17_yolo_train_old_86ce83f.ipynb` |
| `drive/docs/requirements/VOSS_BRD_v1.3.docx` | Drive 에 있던 v1.3 — 레포 `docs/requirements/VOSS_BRD_v1.3.docx` 와 파일이 다르다(따로 고친 판) |
| `drive/reference/_archive/` | BRD v1.0(docx·md), 10/05 개발일정 xlsx |
| `drive/README_drive_snapshot.md` | Drive 에 있던 `drive.md` 사본(옛 판) |
| `local/` | 개인 PC(남현지) 에만 있던 것: T16 호모그래피 계산 파일(10/06 실패판·10/07), T18 정지 송장 OCR 평가표 `eval_scale3*.csv`, 터치 검증 `touch.csv`, S2-T16 yaw 인수인계(병후), 캘리브레이션 보드 PDF, 10/16 발표 수치표, 10/11 비전 노드 로그 |

## Release `drive-archive-20261018` 자산
받기: `gh release download drive-archive-20261018 -p '<이름>'` (또는 Releases 페이지). 검증: 같은 Release 의 `SHA256SUMS` 로 `sha256sum -c`.

| 자산 | 크기 | 내용 (옛 Drive 경로) | SHA-256 앞 16자 |
|---|---|---|---|
| `raw_1006_voss_1006_t17.tar.part0` + `.part1` | 3.97 GB | T17 박스 검출 촬영 bag A·B·C(`raw/1006/`, ADR-0004·0011 정답셋 원본). `cat raw_1006_voss_1006_t17.tar.part0 raw_1006_voss_1006_t17.tar.part1 > voss_1006_t17.tar` | cd1912c7add21548 · 9528ac34e2631150 |
| `raw_1006_voss_1006_calib_ocr.tar.gz` | 134 MB | 10/06 T16 캘리브레이션 사진(C·V 점)·`camera_info`·촬영 설정·스크립트(`raw/1006/`) | f0155b57ce5a8361 |
| `raw_1007_voss_1007_t16_remeasure.tar.gz` | 38 MB | T16 재측정(`raw/1007/`) | 10efc6ecdc492d60 |
| `raw_1007_voss_1007_ocr_blur.tar.gz` | 26 MB | 흐린 송장 재인쇄 OCR | 83af261a06472250 |
| `raw_1007_voss_1007_servo_stream.tar.gz` | 0.3 MB | 서보 스트리밍 실측 CSV | 2d84273756955712 |
| `raw_1007_voss_1007_missing.tar.gz` | 57 MB | 10/07 흐린 송장 sigma 실험(`ocr_sigma/`)·카메라 노드 로그·서보 스트리밍 추가 기록 | 7bbe7f4a3463677f |
| `raw_1008_voss_1008_handeye.tar.gz` | 57 MB | 핸드아이 보드 27장·풀이 스크립트(`raw/1008/handeye/`) | f721bec3a51016bd |
| `raw_1008_voss_1008_touch_moving.tar.gz` | 22 MB | 터치·이동 중 검증(`raw/1008/touch_moving/`) | 3e183ff42f15add3 |
| `raw_1008_voss_1008_missing.tar.gz` | 23 MB | 10/08 F-04 watchdog CSV(`f04/`)·box_tracker 확인 그림·카메라 노드 로그 등 | 45a01948c6bf8c0f |
| `raw_1010_voss_1010_g1_s1_clips.tar` | 1.62 GB | G1 s1 의 LOST 3건 bag 클립 t26·t31·t32_t33(`tools/vision/box_overlay.py` 입력) | 18155e625a482c17 |
| `raw_1010_voss_1010_missing_small.tar.gz` | 71 MB | 10/10 G1 s1 `label_crop` bag(1단계 OCR 재생용)·노드 로그 | 921753d360095e61 |
| `raw_1010_1012_servo_ticks.tar.gz` | 11 MB | belt_servo 30 Hz 틱 로그 21개(`raw/1010/logs/servo/ticks/`·`raw/1012/ticks/`) | 392a09e9ec7009f9 |
| `raw_1011_pick_01-05.tar.gz` · `raw_1011_voss_1011_missing_small.tar.gz` | 3.5 · 4.2 MB | 10/11 MoveToZone PICK bag 5개 / `soak_153` bag·soak CSV·그리퍼 힘 12 N 시험 전후 voss_config | ed2b4fc5b31cb3fd · 9504a93ae775174e |
| `raw_1014_yaw_obs_bags_A.tar` · `_B.tar` | 1.62 · 0.81 GB | 10/14 yaw 관측 실험 정지 bag 30개(A 14각·A2 위치 6 / B 박스 10) | fe6f9795f80d97a9 · 67759889b6bbb0bc |
| `raw_1015_demo2_bag.tar` | 8.5 MB | 10/15 시연 2회차 bag(17.6 분) | b2b386e4b73e2bae |
| `raw_1015_t19s2b.zip` | 13 MB | T19 2단계 고친 판 재실기(measurements-1015 §6) | 61fcb84dd6f9f2ea |
| `datasets_t17_yolo_v1.zip` | 640 MB | YOLO 학습·holdout 세트 v1 | 6c09df79ecf84a47 |
| `models_box_yolo11n_v1.onnx` | 11 MB | YOLO11n v1(ADR-0011 대비책) | 4583866efe10a21d |
| `colab_t17_y11n_best.pt` · `_last.pt` | 5.4 MB 씩 | 학습 가중치 | f3201ba0a05b2ff2 · a94c359fbd300e2e |
| `local_1006_t18_crops.tar.gz` | 17 MB | T18 OCR 평가에 쓴 송장 크롭(개인 PC) | d3649d00b97f0a74 |
| `git_bundles_20261018.tar` | 113 MB | 정리하며 지운 브랜치·레포 이전(ADR-0015) git bundle 과 목록(개인 PC) | bdc341a17bced456 |

## 옮기지 않은 것
- 남이 만든 자료: 강의 PDF 19개, 수업 샘플 zip 3개, 컨베이어 판매 페이지 PDF — 공개 레포라 저작권.
- 같은 파일이 이미 있는 사본: Colab 노트북(= `tools/colab/t17_yolo_train.ipynb`), `best.onnx`(= 모델 자산), BRD v1.2(= git `b998dfa`), 개발일정 xlsx 중복 1부, 시도 로그 8개(= `data/servo/attempts/`), 중간발표 PDF(= `docs/presentations/`).
- 중간 체크포인트 `epoch*.pt` 8개, 빈 폴더(`results/*`, `runo-dev/`), 0 바이트 로그 191개, `__pycache__`.

## 잃은 것 (공용 PC 반납으로 복구 불가)
10/10 bag 본체 약 60 GB(G1 s1·G0·추종 리허설 — `metadata.yaml` 만 남음) · 10/12 손목 bag `u9_s2_bag_C` · 10/13 Sprint 2 게이트 녹화 `s2gate_pal`·`s2gate_rows.md` · 10/14 yaw 관측 이동 bag `C_moving`(metadata 만) · 10/15 T19 1차 실기 `t19s2/` · 10/15 J6 회전 실기 `u14/` · 10/15 시연 1회차 `demo`. 값은 measurements·ADR 에 적힌 것이 전부다.

## 읽을 때 주의
- **10/14 yaw 관측 실험은 실제로 했다** — `drive/raw/1014/yaw_obs/진행기록.md`·`record.csv`. `src/voss_servo/design/S2T18-hld.md` 의 "yaw 관측 실험은 하지 않고"와 다르다(그 실험 값을 S2-T18 파라미터에 쓰지 않았다는 뜻으로 읽는다). 요약: 정지 14각 bag 안 yaw 오차 0.3° 안, 0° 근처는 +0.25° 한 값에 붙음(추측: minAreaRect), 이동 37트랙은 외곽 각보다 + 쪽 +3~5°.
- 공개 레포라 옮기기 전에 텍스트 전부(로그·md·csv·yaml·docx·xlsx, tar 안 텍스트 포함)에서 키·토큰·비밀번호·Drive 링크를 검사했다 — 없음. IP 는 실습실 사설 192.168.1.x(이미 레포에 있음)와 doosan-robot2 기본값 `rt_host 192.168.137.50` 뿐이다. handoff 의 "Password = 토큰" 은 입력 안내 문구다.
- 현장 도구(`drive/raw/1010/servo_goto.py` 등)는 실로봇을 움직인다 — 기록용이다. 실행은 CLAUDE.md 규칙 6 대로 사람이 비상정지 옆에서.
