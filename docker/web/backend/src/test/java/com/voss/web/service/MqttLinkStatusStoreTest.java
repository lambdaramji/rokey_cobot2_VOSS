// T13 #22 MQTT 연결 상태의 저장 및 전환을 검증한다.
// 입력: 모의 연결 성공과 끊김 이벤트.
// 출력: DOWN·UP 상태에 대한 JUnit 검증 결과.
// 근거: docs/interfaces/web_api.md, mqtt.md.

package com.voss.web.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MqttLinkStatusStoreTest {

    /**
     * MQTT 연결 확인 전에는 DOWN 상태인지 검사한다.
     */
    @Test
    void testInitialStatusIsDownBeforeConnection() {
        MqttLinkStatusStore store = new MqttLinkStatusStore();

        assertEquals(
                MqttLinkStatusStore.MqttLinkStatus.DOWN,
                store.getStatus()
        );
    }

    /**
     * 연결 성공 알림을 받으면 UP으로 변경되는지 검사한다.
     */
    @Test
    void testStatusBecomesUpAfterConnection() {
        MqttLinkStatusStore store = new MqttLinkStatusStore();

        store.markConnected();

        assertEquals(
                MqttLinkStatusStore.MqttLinkStatus.UP,
                store.getStatus()
        );
    }

    /**
     * 연결이 끊기면 DOWN으로 변경되는지 검사한다.
     */
    @Test
    void testStatusBecomesDownAfterDisconnection() {
        MqttLinkStatusStore store = new MqttLinkStatusStore();

        store.markConnected();
        store.markDisconnected();

        assertEquals(
                MqttLinkStatusStore.MqttLinkStatus.DOWN,
                store.getStatus()
        );
    }

    /**
     * 연결과 끊김이 반복되어도 마지막 알림을 반영하는지 검사한다.
     */
    @Test
    void testRepeatedConnectionChangesKeepLatestStatus() {
        MqttLinkStatusStore store = new MqttLinkStatusStore();

        store.markConnected();
        store.markDisconnected();
        store.markConnected();

        assertEquals(
                MqttLinkStatusStore.MqttLinkStatus.UP,
                store.getStatus()
        );

        store.markDisconnected();

        assertEquals(
                MqttLinkStatusStore.MqttLinkStatus.DOWN,
                store.getStatus()
        );
    }
}