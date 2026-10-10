// T13 #22 MQTT 구성의 토픽·QoS·연결 비활성화를 검증한다.
// 입력: 모의 MQTT 설정과 문자열 메시지. 출력: JUnit 판정.
// 근거: docs/interfaces/mqtt.md, web_api.md.
package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.service.LiveEvents;
import com.voss.web.service.MqttLinkStatusStore;
import com.voss.web.service.SortStateStore;
import java.util.Map;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "voss.mqtt.enabled=false")
class MqttSubscriberConfigTest {
    private static final String TEST_PASSWORD = "test-only-password";
    private static final String VALID_STATE_JSON = """
            {"state":"RUNNING","box_id":"BOX-001","pending_question":"",
             "track_id":7,"ready":true,"not_ready":[],"session_id":"20261010T143012-a3f9"}
            """;

    @Autowired private ApplicationContext applicationContext;
    private final MqttSubscriberConfig config = new MqttSubscriberConfig();

    /** 개발 기본값에서는 실제 브로커용 Bean을 만들지 않는다. */
    @Test
    void testMqttBeansAreDisabledWithoutBroker() {
        assertFalse(applicationContext.containsBean("mqttClientFactory"));
        assertFalse(applicationContext.containsBean("mqttStateAdapter"));
        assertFalse(applicationContext.containsBean("mqttCommandChannel"));
    }

    /** 비밀번호 미설정 시 MQTT 연결 설정을 생성하지 않는다. */
    @Test
    void testMissingPasswordIsRejected() {
        assertThrows(IllegalStateException.class, () -> config.mqttClientFactory(""));
        assertThrows(IllegalStateException.class, () -> config.mqttClientFactory("   "));
    }

    /** 브로커 주소와 웹 계정은 mqtt.md의 확정 규칙을 따른다. */
    @Test
    void testConnectionOptionsMatchMqttContract() {
        MqttPahoClientFactory factory = config.mqttClientFactory(TEST_PASSWORD);
        MqttConnectOptions options = factory.getConnectionOptions();
        assertArrayEquals(new String[]{"tcp://127.0.0.1:1883"}, options.getServerURIs());
        assertEquals("web", options.getUserName());
        assertEquals(5, options.getConnectionTimeout());
        assertTrue(options.isAutomaticReconnect());
    }

    /** 수신 6개 토픽과 QoS를 전체 계약에 맞게 구독한다. */
    @Test
    void testSubscriberUsesContractTopicsAndQos() {
        MqttPahoClientFactory factory = config.mqttClientFactory(TEST_PASSWORD);
        MqttPahoMessageDrivenChannelAdapter adapter =
                config.mqttStateAdapter(factory, new DirectChannel());
        assertArrayEquals(new String[]{"voss/state", "voss/result", "voss/zone_map",
                "voss/robot", "voss/command/ack", "voss/log_status"}, adapter.getTopic());
        assertArrayEquals(new int[]{1, 1, 1, 0, 1, 1}, adapter.getQos());
    }

    /** 수신 채널은 토픽 헤더를 라우터로 전달한다. */
    @Test
    void testSubscriberForwardsStateToRouter() {
        ObjectMapper mapper = new ObjectMapper();
        SortStateStore stateStore = new SortStateStore();
        MqttStateMessageHandler stateHandler = new MqttStateMessageHandler(mapper, stateStore);
        MqttEventRouter router = new MqttEventRouter(mapper, stateHandler, stateStore,
                new LiveEvents(mapper, new MqttLinkStatusStore()));
        MessageHandler consumer = config.mqttStateMessageConsumer(router);
        consumer.handleMessage(new GenericMessage<>(VALID_STATE_JSON,
                Map.of(MqttHeaders.RECEIVED_TOPIC, "voss/state")));
        SortStateStore.StateSnapshot snapshot = stateStore.getLatestState().orElseThrow();
        assertEquals("RUNNING", snapshot.message().state());
        consumer.handleMessage(new GenericMessage<>(123,
                Map.of(MqttHeaders.RECEIVED_TOPIC, "voss/state")));
        assertSame(snapshot, stateStore.getLatestState().orElseThrow());
    }
}
