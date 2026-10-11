// MQTT 명령 발행 실패 후 재시도·복구 및 SSE 상태 변화를 검증한다.
// 입력: 모의 MQTT MessageChannel 반환값. 출력: DOWN·UP 상태 및 MQTT_DOWN.
// 근거: docs/interfaces/web_api.md, mqtt.md, PR #146 PL 리뷰.
package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.api.ApiException;
import com.voss.web.service.LiveEvents;
import com.voss.web.service.MqttLinkStatusStore;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.messaging.MessageChannel;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MqttCommandPublisherTest {
    private final MqttLinkStatusStore link = new MqttLinkStatusStore();
    private final LiveEvents events = mock(LiveEvents.class);

    /** 구독 연결 상태가 DOWN이어도 발행 성공으로 상태를 복구한다. */
    @Test
    void testSuccessfulStopRetryRestoresMqttLinkAfterPublishFailure() {
        @SuppressWarnings("unchecked")
        ObjectProvider<MessageChannel> provider = mock(ObjectProvider.class);
        MessageChannel channel = mock(MessageChannel.class);
        when(provider.getIfAvailable()).thenReturn(channel);
        when(channel.send(any(), eq(1500L))).thenReturn(false, true);
        MqttCommandPublisher publisher = new MqttCommandPublisher(
                provider, link, new ObjectMapper(), events);

        ApiException failure = assertThrows(ApiException.class,
                () -> publisher.publish(Map.of("type", "stop")));
        assertEquals("MQTT_DOWN", failure.code());
        assertEquals(MqttLinkStatusStore.MqttLinkStatus.DOWN, link.getStatus());

        publisher.publish(Map.of("type", "stop"));
        assertEquals(MqttLinkStatusStore.MqttLinkStatus.UP, link.getStatus());
        verify(events, times(2)).publishLink();
    }

    /** MQTT 발행 채널이 없는 상태에서는 실제 명령을 보내지 못한다. */
    @Test
    void testMissingMqttChannelFailsClosed() {
        @SuppressWarnings("unchecked")
        ObjectProvider<MessageChannel> provider = mock(ObjectProvider.class);
        MqttCommandPublisher publisher = new MqttCommandPublisher(
                provider, link, new ObjectMapper(), events);
        ApiException failure = assertThrows(ApiException.class,
                () -> publisher.publish(Map.of("type", "start")));
        assertEquals("MQTT_DOWN", failure.code());
    }

    /** 구독 이벤트가 아직 없어도 발행 성공이 연결 상태를 UP으로 만든다. */
    @Test
    void testFirstPublishSuccessMarksMqttUp() {
        @SuppressWarnings("unchecked")
        ObjectProvider<MessageChannel> provider = mock(ObjectProvider.class);
        MessageChannel channel = mock(MessageChannel.class);
        when(provider.getIfAvailable()).thenReturn(channel);
        when(channel.send(any(), eq(1500L))).thenReturn(true);
        MqttCommandPublisher publisher = new MqttCommandPublisher(
                provider, link, new ObjectMapper(), events);
        publisher.publish(Map.of("type", "stop"));
        assertEquals(MqttLinkStatusStore.MqttLinkStatus.UP, link.getStatus());
        verify(events).publishLink();
    }
}
