#!/usr/bin/env bash
# VOSS 기동 (T22 #31) — scripts/voss_up.py up. 실행은 사람이 한다. --real 은 비상정지 옆에서(CLAUDE.md 규칙 6).
#   scripts/voss_up.sh --real --print   # 계획만
#   scripts/voss_up.sh --real           # 실기
#   scripts/voss_up.sh --dry --playback <bag>
exec python3 "$(dirname "$(readlink -f "$0")")/voss_up.py" up "$@"
