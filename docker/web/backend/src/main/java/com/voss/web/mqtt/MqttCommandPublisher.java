// 웹 명령을 MQTT voss/command 토픽으로 발행한다.
// 입력: 계약 명령 JSON. 출력: 브로커 전달 또는 MQTT_DOWN.
// 근거: docs/interfaces/mqtt.md, web_api.md.
package com.voss.web.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.api.ApiException;
import com.voss.web.service.MqttLinkStatusStore;
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

    /** 선택적으로 구성된 MQTT 발행 채널을 받는다. */
    public MqttCommandPublisher(@Qualifier("mqttCommandChannel") ObjectProvider<MessageChannel> channel,
                                MqttLinkStatusStore link, ObjectMapper mapper) {
        this.channel = channel;
        this.link = link;
        this.mapper = mapper;
    }

    /** 브로커 연결을 확인한 뒤 QoS 1로 명령을 전달한다. */
    public void publish(Map<String,Object> command) {
        if (link.getStatus() != MqttLinkStatusStore.MqttLinkStatus.UP) { throw unavailable(); }
        MessageChannel outbound = channel.getIfAvailable();
        if (outbound == null) { throw unavailable(); }
        try {
            String payload = mapper.writeValueAsString(command);
            boolean sent = outbound.send(MessageBuilder.withPayload(payload).build(), 1500);
            if (!sent) { throw unavailable(); }
        } catch (JsonProcessingException exception) {
            throw unavailable();
        } catch (org.springframework.messaging.MessagingException exception) {
            link.markDisconnected();
            throw unavailable();
        }
    }

    /** MQTT_DOWN을 공통 HTTP 오류로 표현한다. */
    private ApiException unavailable() {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "MQTT_DOWN", "MQTT 브로커로 명령을 전달할 수 없습니다.");
    }
}
