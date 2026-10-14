// 웹 명령을 MQTT voss/command 토픽으로 발행한다.
// 입력: 계약 명령 JSON. 출력: 브로커 전달 또는 MQTT_DOWN.
// 근거: docs/interfaces/mqtt.md, web_api.md.
package com.voss.web.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.api.ApiException;
import com.voss.web.service.MqttLinkStatusStore;
import com.voss.web.service.LiveEvents;
import java.util.Map;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class MqttCommandPublisher {
    private final ObjectProvider<MessageChannel> channel;
    private final MqttLinkStatusStore link;
    private final ObjectMapper mapper;
    private final LiveEvents events;

    /** 선택적으로 구성된 MQTT 발행 채널을 받는다. */
    public MqttCommandPublisher(@Qualifier("mqttCommandChannel") ObjectProvider<MessageChannel> channel,
                                MqttLinkStatusStore link, ObjectMapper mapper, LiveEvents events) {
        this.channel = channel;
        this.link = link;
        this.mapper = mapper;
        this.events = events;
    }

    /** 링크 DOWN 이후에도 실제 발행 재시도로 복구를 확인한다. */
    public void publish(Map<String,Object> command) {
        MessageChannel outbound = channel.getIfAvailable();
        if (outbound == null) {
            markLinkDown();
            throw unavailable();
        }
        try {
            String payload = mapper.writeValueAsString(command);
            boolean sent = outbound.send(MessageBuilder.withPayload(payload).build(), 1500);
            if (!sent) {
                markLinkDown();
                throw unavailable();
            }
            markLinkUp();
        } catch (JsonProcessingException exception) {
            throw unavailable();
        } catch (org.springframework.messaging.MessagingException exception) {
            markLinkDown();
            throw unavailable();
        }
    }

    /** 발행 성공·실패를 링크 SSE에 즉시 반영한다. */
    private void markLinkUp() {
        if (link.getStatus() == MqttLinkStatusStore.MqttLinkStatus.UP) { return; }
        link.markConnected();
        events.publishLink();
    }

    private void markLinkDown() {
        link.markDisconnected();
        events.publishLink();
    }

    /** MQTT_DOWN을 공통 HTTP 오류로 표현한다. */
    private ApiException unavailable() {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "MQTT_DOWN", "MQTT 브로커로 명령을 전달할 수 없습니다.");
    }
}
