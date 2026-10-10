// 확정된 7개 MQTT 입력 토픽을 상태 저장과 SSE 이벤트에 연결한다.
// 입력: 토픽명과 MQTT JSON payload. 출력: 최신 상태와 SSE.
// 근거: docs/interfaces/mqtt.md, web_api.md.
package com.voss.web.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.service.LiveEvents;
import com.voss.web.service.SortStateStore;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class MqttEventRouter {
    private static final Logger LOGGER = LoggerFactory.getLogger(MqttEventRouter.class);
    private static final Set<String> INPUT_TOPICS = Set.of(
            "voss/state", "voss/result", "voss/zone_map", "voss/robot",
            "voss/command/ack", "voss/log_status");
    private final ObjectMapper mapper;
    private final MqttStateMessageHandler stateHandler;
    private final SortStateStore stateStore;
    private final LiveEvents events;
    private volatile JsonNode zoneMap;

    /** 원본 메시지를 상태 저장소와 SSE 이벤트 흐름에 연결한다. */
    public MqttEventRouter(ObjectMapper mapper, MqttStateMessageHandler stateHandler,
                           SortStateStore stateStore, LiveEvents events) {
        this.mapper = mapper;
        this.stateHandler = stateHandler;
        this.stateStore = stateStore;
        this.events = events;
    }

    /** 정확히 알려진 토픽의 JSON만 받아 처리한다. */
    public void receive(String topic, String payload) {
        if (!INPUT_TOPICS.contains(topic)) { return; }
        if (payload == null || payload.isBlank()) { return; }
        try {
            JsonNode json = mapper.readTree(payload);
            if (json == null || !json.isObject()) { return; }
            if ("voss/state".equals(topic)) {
                handleState(payload, json);
                return;
            }
            if ("voss/zone_map".equals(topic)) { zoneMap = json.deepCopy(); }
            events.publish(toEventName(topic), json);
        } catch (JsonProcessingException exception) {
            LOGGER.warn("{}: MQTT JSON을 분석하지 못했습니다.", topic);
        }
    }

    /** 유효한 SortState만 최신 상태에 반영하고 SSE로 보낸다. */
    private void handleState(String payload, JsonNode json) {
        SortStateStore.StateSnapshot before = stateStore.getLatestState().orElse(null);
        stateHandler.handle(payload);
        SortStateStore.StateSnapshot after = stateStore.getLatestState().orElse(null);
        if (after != null && after != before) { events.publish("state", json); }
    }

    /** 정식 동 이름이 최근 zone_map에 있는지 확인한다. */
    public boolean isCanonicalDong(String dong) {
        JsonNode current = zoneMap;
        if (current == null || !current.path("entries").isArray()) { return false; }
        for (JsonNode entry : current.path("entries")) {
            if (dong.equals(entry.path("dong").asText())) { return true; }
        }
        return false;
    }

    /** 토픽을 계약된 SSE 이벤트 이름으로 변환한다. */
    private String toEventName(String topic) {
        if ("voss/command/ack".equals(topic)) { return "command_ack"; }
        return topic.substring("voss/".length());
    }
}
