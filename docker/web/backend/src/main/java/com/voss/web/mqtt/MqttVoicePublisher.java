package com.voss.web.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.api.ApiException;
import java.util.Map;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

/** 허용된 버튼 이름만 Nodes PC의 음성 브리지로 전달한다. */
@Service
public class MqttVoicePublisher {
    private final ObjectProvider<MessageChannel> channel;
    private final ObjectMapper mapper;

    public MqttVoicePublisher(@Qualifier("mqttVoiceChannel") ObjectProvider<MessageChannel> channel,
                              ObjectMapper mapper) {
        this.channel = channel;
        this.mapper = mapper;
    }

    public void publish(Map<String, Object> request) {
        MessageChannel outbound = channel.getIfAvailable();
        if (outbound == null) { throw unavailable(); }
        try {
            String payload = mapper.writeValueAsString(request);
            if (!outbound.send(MessageBuilder.withPayload(payload).build(), 1500)) {
                throw unavailable();
            }
        } catch (JsonProcessingException | MessagingException exception) {
            throw unavailable();
        }
    }

    private ApiException unavailable() {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "VOICE_MQTT_DOWN",
                "Nodes PC 음성 요청을 MQTT로 전달할 수 없습니다.");
    }
}
