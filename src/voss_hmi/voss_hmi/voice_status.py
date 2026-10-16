"""표시 전용 음성 JSON을 검증하고, 연결 중에만 기존 MQTT 클라이언트로 보낸다."""

import json

PHASES = {
    "AUDIO_DETECTED",
    "AUDIO_REJECTED",
    "WAKE_DETECTED",
    "COMMAND_ACCEPTED",
    "RECOGNITION_FAILED",
    "TIMED_OUT",
}


def parse_voice_status(raw):
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("phase"), str) or data["phase"] not in PHASES:
        return None
    if any(
        not isinstance(data.get(key), str)
        or not data[key].strip()
        or data[key] != data[key].strip()
        or len(data[key]) > 128
        for key in ("event_id", "utterance_id")
    ):
        return None
    return {key: data[key] for key in ("phase", "event_id", "utterance_id")}


def forward_voice_status(client, raw):
    """끊긴 동안의 호출어는 보관하지 않는다. QoS 0으로 재연결 후 재생을 방지한다."""
    payload = parse_voice_status(raw)
    if payload is None or not client.is_connected():
        return False
    result = client.publish("voss/voice_status", json.dumps(payload), qos=0, retain=False)
    return result.rc == 0
