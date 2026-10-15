"""표시 전용 MQTT 인증이 일반 bridge 인증과 섞이지 않는지 확인한다."""

from unittest.mock import Mock, patch

import pytest
from voss_hmi.hmi_bridge import HmiBridgeNode


@pytest.mark.parametrize(
    ("preview", "expected_user", "expected_password", "expected_client_id"),
    [
        (False, "bridge", "bridge-test-value", "voss-hmi-bridge"),
        (True, "voice_preview", "preview-test-value", "voss-hmi-voice-preview"),
    ],
)
def test_mqtt_credentials_are_selected_by_mode(
    monkeypatch, preview, expected_user, expected_password, expected_client_id
):
    monkeypatch.setenv("VOSS_MQTT_BRIDGE_PASSWORD", "bridge-test-value")
    monkeypatch.setenv("VOSS_MQTT_PREVIEW_USERNAME", "voice_preview")
    monkeypatch.setenv("VOSS_MQTT_PREVIEW_PASSWORD", "preview-test-value")
    with patch("voss_hmi.hmi_bridge.mqtt.Client") as client_type:
        HmiBridgeNode._create_mqtt_client(
            Mock(_voice_status_only=preview, _local_text_enabled=False)
        )
    assert client_type.call_args.kwargs["client_id"] == expected_client_id
    client_type.return_value.username_pw_set.assert_called_once_with(
        expected_user, expected_password
    )


@pytest.mark.parametrize("missing", ["VOSS_MQTT_PREVIEW_USERNAME", "VOSS_MQTT_PREVIEW_PASSWORD"])
def test_preview_requires_both_credentials(monkeypatch, missing):
    monkeypatch.setenv("VOSS_MQTT_BRIDGE_PASSWORD", "bridge-test-value")
    monkeypatch.setenv("VOSS_MQTT_PREVIEW_USERNAME", "voice_preview")
    monkeypatch.setenv("VOSS_MQTT_PREVIEW_PASSWORD", "preview-test-value")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=f"{missing} is required"):
        HmiBridgeNode._create_mqtt_client(Mock(_voice_status_only=True, _local_text_enabled=False))


def test_normal_mode_requires_only_bridge_password(monkeypatch):
    monkeypatch.delenv("VOSS_MQTT_PREVIEW_USERNAME", raising=False)
    monkeypatch.delenv("VOSS_MQTT_PREVIEW_PASSWORD", raising=False)
    monkeypatch.setenv("VOSS_MQTT_BRIDGE_PASSWORD", "bridge-test-value")
    with patch("voss_hmi.hmi_bridge.mqtt.Client") as client_type:
        HmiBridgeNode._create_mqtt_client(Mock(_voice_status_only=False, _local_text_enabled=False))
    client_type.return_value.username_pw_set.assert_called_once_with("bridge", "bridge-test-value")


def test_web_voice_mode_uses_only_dedicated_account(monkeypatch):
    monkeypatch.setenv("VOSS_MQTT_BRIDGE_PASSWORD", "bridge-test-value")
    monkeypatch.setenv("VOSS_MQTT_VOICE_WEB_PASSWORD", "voice-web-test-value")
    with patch("voss_hmi.hmi_bridge.mqtt.Client") as client_type:
        HmiBridgeNode._create_mqtt_client(Mock(_voice_status_only=True, _local_text_enabled=True))
    assert client_type.call_args.kwargs["client_id"] == "voss-hmi-voice-web"
    client_type.return_value.username_pw_set.assert_called_once_with(
        "voice_web", "voice-web-test-value"
    )


def test_web_voice_mode_rejects_missing_dedicated_password(monkeypatch):
    monkeypatch.setenv("VOSS_MQTT_BRIDGE_PASSWORD", "bridge-test-value")
    monkeypatch.delenv("VOSS_MQTT_VOICE_WEB_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="VOSS_MQTT_VOICE_WEB_PASSWORD is required"):
        HmiBridgeNode._create_mqtt_client(Mock(_voice_status_only=True, _local_text_enabled=True))
