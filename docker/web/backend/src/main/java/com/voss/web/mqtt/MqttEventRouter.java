// 확정된 MQTT 수신 토픽을 상태 저장, SSE, 세션 예정 수량에 연결한다.
// 입력: 토픽명과 MQTT JSON. 출력: 최신 SortState, SSE, session_plan 연결.
// 근거: docs/interfaces/mqtt.md, web_api.md (#20, #68).
package com.voss.web.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.api.ApiException;
import com.voss.web.db.PlanRepository;
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
    private final PlanRepository plans;
    private volatile JsonNode zoneMap;
    private String lastAttachedSessionId = "";

    /** MQTT 처리기, SSE, 예정 수량 저장소를 연결한다. */
    public MqttEventRouter(ObjectMapper mapper, MqttStateMessageHandler stateHandler,
                           SortStateStore stateStore, LiveEvents events, PlanRepository plans) {
        this.mapper = mapper;
        this.stateHandler = stateHandler;
        this.stateStore = stateStore;
        this.events = events;
        this.plans = plans;
    }

    /** 계약에 정의된 토픽과 JSON 객체만 처리한다. */
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
            LOGGER.warn("{}: MQTT JSON 분석에 실패했습니다.", topic);
        }
    }

    /** 상태를 먼저 SSE에 전송하여 DB 접속 지연으로 화면 반영을 막지 않는다. */
    private void handleState(String payload, JsonNode json) {
        SortStateStore.StateSnapshot before = stateStore.getLatestState().orElse(null);
        stateHandler.handle(payload);
        SortStateStore.StateSnapshot after = stateStore.getLatestState().orElse(null);
        if (after == null || after == before) { return; }

        events.publish("state", json);
        attachPlanForNewSession(after.message().sessionId());
    }

    /** 새 세션의 첫 상태 수신 시 next를 붙이고, DB 실패 시 다음 상태에서 재시도한다. */
    private synchronized void attachPlanForNewSession(String sessionId) {
        if (sessionId == null || sessionId.isEmpty()) { return; }
        if (sessionId.equals(lastAttachedSessionId)) { return; }
        try {
            plans.attachPending(sessionId);
            lastAttachedSessionId = sessionId;
        } catch (ApiException exception) {
            // 화면의 상태 SSE는 유지하고 다음 정상 수신 때 연결을 다시 시도한다 (web_api.md).
            LOGGER.warn("새 세션 예정 수량 연결 실패: {}", exception.code());
        }
    }

    /** 정식 동 이름만 허용하며 별칭은 명령 입력에 사용하지 않는다. */
    public boolean isCanonicalDong(String dong) {
        JsonNode current = zoneMap;
        if (current == null || !current.path("entries").isArray()) { return false; }
        for (JsonNode entry : current.path("entries")) {
            if (dong.equals(entry.path("dong").asText())) { return true; }
        }
        return false;
    }

    /** MQTT 토픽을 SSE 이름으로 바꾸되 command/ack만 별도 이름을 쓴다. */
    private String toEventName(String topic) {
        if ("voss/command/ack".equals(topic)) { return "command_ack"; }
        return topic.substring("voss/".length());
    }
}
