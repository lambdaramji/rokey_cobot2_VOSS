# yaw_obs — S2-T18 yaw 관측 실험 (2026-10-14 11:26~12:22, 공용 PC)

절차서: S2T18-yaw-observe-guide.md (박병후). 로봇은 관측 자세에 정지, goal·파지·J6 회전 없음. belt_servo·sort_manager 미기동.

| 파일 | 내용 |
|---|---|
| `A_*` (14) · `A2_*` (6) · `B_box01~10` (10) | 정지 녹화 각 5.5~5.6 s (mcap: 압축 영상·camera_info·/voss/robot/pose·/voss/vision/box) |
| `C_moving` | 벨트 h250 연속 녹화 284 s, 박스 37개 통과 |
| `record.csv` | 기록표(절차서 §6 열 + 시각·메시지 수·u·v·실시간 yaw). A·A2 는 **화면 yaw 를 보고 각도를 맞춤**(비고), B 는 박스 변을 벨트와 평행하게, C 는 박스 번호 미기록 |
| `build.txt` | 빌드 커밋 ed80f41(v15 yaw), BoxTrack yaw 2줄, 토픽 확인 |
| `진행기록.md` | 진행·사건·관측(Claude 가 로그·녹화에서 적음) |
| `C_tracks.csv` · `C_track_frames/` | C 트랙별 비전 yaw·박스 외곽 각(참고값)·확인 이미지, 스크립트 c_angles.py |
| `static_outline_check.csv` · `static_outline_frames/` | 정지 녹화에 같은 외곽 각 측정(참고값) |

실제 각 기준 = 휴대폰 사진(별도 폴더). 외곽 각은 박스 옆면이 섞여 수 도 치우칠 수 있는 참고값.
