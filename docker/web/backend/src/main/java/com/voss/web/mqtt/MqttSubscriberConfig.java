// Spring Boot MQTT 7개 토픽 구독과 명령 발행을 설정한다.
// 입력: 환경 변수의 MQTT 계정 정보. 출력: MQTT ↔ Spring 메시지 채널.
// 근거: docs/interfaces/mqtt.md (#20), web_api.md.
package com.voss.web.mqtt;

import java.util.UUID;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "voss.mqtt.enabled", havingValue = "true")
public class MqttSubscriberConfig {
    private static final String MQTT_BROKER_URL = "tcp://127.0.0.1:1883";
    private static final String MQTT_USERNAME = "web";
    private static final String[] INPUT_TOPICS = {
            "voss/state", "voss/result", "voss/zone_map", "voss/robot",
            "voss/command/ack", "voss/log_status"};
    private static final int[] INPUT_QOS = {1, 1, 1, 0, 1, 1};

    /** 브로커 인증 정보를 환경 변수에서 읽어 MQTT 클라이언트에 넣는다. */
    @Bean
    public MqttPahoClientFactory mqttClientFactory(
            @Value("${VOSS_MQTT_WEB_PASSWORD:}") String password) {
        if (password.isBlank()) { throw new IllegalStateException("VOSS_MQTT_WEB_PASSWORD 환경 변수가 필요합니다."); }
        MqttConnectOptions options = new MqttConnectOptions();
        options.setServerURIs(new String[]{MQTT_BROKER_URL});
        options.setUserName(MQTT_USERNAME);
        options.setPassword(password.toCharArray());
        options.setConnectionTimeout(5);
        options.setAutomaticReconnect(true);
        DefaultMqttPahoClientFactory factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    /** 모든 MQTT 수신 토픽을 전달할 내부 채널을 만든다. */
    @Bean
    public MessageChannel mqttStateInputChannel() { return new DirectChannel(); }

    /** MQTT 수신 토픽별 QoS를 지정하고 메시지를 채널로 전달한다. */
    @Bean
    public MqttPahoMessageDrivenChannelAdapter mqttStateAdapter(
            MqttPahoClientFactory clientFactory,
            @Qualifier("mqttStateInputChannel") MessageChannel channel) {
        MqttPahoMessageDrivenChannelAdapter adapter =
                new MqttPahoMessageDrivenChannelAdapter("voss-web-input-" + UUID.randomUUID(),
                        clientFactory, INPUT_TOPICS);
        adapter.setQos(INPUT_QOS);
        adapter.setOutputChannel(channel);
        return adapter;
    }

    /** 브로커에서 받은 토픽과 JSON을 해당 이벤트 처리기에 전달한다. */
    @Bean
    @ServiceActivator(inputChannel = "mqttStateInputChannel")
    public MessageHandler mqttStateMessageConsumer(MqttEventRouter router) {
        return message -> {
            Object topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC);
            Object payload = message.getPayload();
            if (topic instanceof String topicText && payload instanceof String jsonText) {
                router.receive(topicText, jsonText);
            }
        };
    }

    /** 웹 명령 발행을 위한 내부 채널을 만든다. */
    @Bean
    public MessageChannel mqttCommandChannel() { return new DirectChannel(); }

    /** voss/command로만 QoS 1·retain=false 명령을 발행한다. */
    @Bean
    @ServiceActivator(inputChannel = "mqttCommandChannel")
    public MessageHandler mqttCommandConsumer(MqttPahoClientFactory clientFactory) {
        MqttPahoMessageHandler handler = new MqttPahoMessageHandler(
                "voss-web-command-" + UUID.randomUUID(), clientFactory);
        handler.setDefaultTopic("voss/command");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        return handler;
    }
}
