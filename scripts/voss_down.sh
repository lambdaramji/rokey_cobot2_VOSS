#!/usr/bin/env bash
# VOSS 종료 (T22 #31) — 기동의 역순, belt_servo 를 gateway 보다 먼저. IDLE·PAUSED 에서만(먼저 stop·벨트 12 V 끄기).
exec python3 "$(dirname "$(readlink -f "$0")")/voss_up.py" down "$@"
