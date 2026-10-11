// T13 #22 MQTT 브로커의 연결 상태를 메모리에 저장한다.
// 입력: MQTT 연결 성공 또는 끊김 알림.
// 출력: 현재 연결 상태 UP 또는 DOWN.
// 근거: docs/interfaces/web_api.md, mqtt.md.

package com.voss.web.service;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class MqttLinkStatusStore {

    private final AtomicReference<MqttLinkStatus> currentStatus =
            new AtomicReference<>(MqttLinkStatus.DOWN);

    /**
     * MQTT 연결이 확인되면 UP으로 변경한다.
     * 실제 연결 확인 이벤트를 받는 쪽에서 호출한다.
     */
    public void markConnected() {
        currentStatus.set(MqttLinkStatus.UP);
    }

    /**
     * MQTT 연결이 끊기거나 실패하면 DOWN으로 변경한다.
     */
    public void markDisconnected() {
        currentStatus.set(MqttLinkStatus.DOWN);
    }

    /**
     * 현재 MQTT 연결 상태를 반환한다.
     * 아직 연결을 확인하지 못했다면 DOWN을 반환한다.
     */
    public MqttLinkStatus getStatus() {
        return currentStatus.get();
    }

    /**
     * 웹 API의 MQTT 연결 상태값을 정의한다.
     */
    public enum MqttLinkStatus {
        UP,
        DOWN
    }
}