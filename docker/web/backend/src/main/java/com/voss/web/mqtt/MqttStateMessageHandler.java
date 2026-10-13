// T13 #22 MQTT voss/state JSON을 검증하고 최신 상태를 저장한다.
// 입력: hmi_bridge에서 전달한 MQTT JSON 문자열.
// 출력: 계약에 맞는 SortStateMessage만 저장.
// 근거: docs/interfaces/mqtt.md, voss_msgs.md.

package com.voss.web.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.dto.SortStateMessage;
import com.voss.web.service.SortStateStore;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class MqttStateMessageHandler {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(MqttStateMessageHandler.class);

    private static final List<String> TEXT_FIELDS = List.of(
            "state",
            "box_id",
            "pending_question",
            "session_id"
    );

    private static final Set<String> VALID_STATES = Set.of(
            "IDLE",
            "RUNNING",
            "PICKING",
            "RECHECK",
            "ASKING",
            "PAUSED"
    );

    private final ObjectMapper objectMapper;
    private final SortStateStore stateStore;

    /**
     * JSON 변환기와 최신 상태 저장소를 전달받는다.
     */
    public MqttStateMessageHandler(
            ObjectMapper objectMapper,
            SortStateStore stateStore
    ) {
        this.objectMapper = Objects.requireNonNull(objectMapper);
        this.stateStore = Objects.requireNonNull(stateStore);
    }

    /**
     * MQTT 상태 JSON의 필수 필드를 검증하고 저장한다.
     * 형식이나 타입이 틀리면 기존 상태를 유지한다.
     */
    public void handle(String jsonPayload) {
        if (jsonPayload == null || jsonPayload.isBlank()) {
            LOGGER.warn("voss/state: 빈 메시지를 받았습니다.");
            return;
        }

        try {
            JsonNode root = objectMapper.readTree(jsonPayload);

            if (!isValidState(root)) {
                LOGGER.warn("voss/state: 계약에 맞지 않는 메시지입니다.");
                return;
            }

            SortStateMessage message = objectMapper.treeToValue(
                    root,
                    SortStateMessage.class
            );

            stateStore.update(message);
        } catch (JsonProcessingException exception) {
            LOGGER.warn("voss/state: JSON 분석에 실패했습니다.", exception);
        }
    }

    /**
     * 필수 필드와 상태값이 계약에 맞는지 확인한다.
     */
    private boolean isValidState(JsonNode root) {
        if (root == null || !root.isObject()) {
            return false;
        }

        if (!hasValidTextFields(root)) {
            return false;
        }

        if (!hasValidNumberAndBooleanFields(root)) {
            return false;
        }

        if (!hasValidNotReadyList(root)) {
            return false;
        }

        return VALID_STATES.contains(root.get("state").asText());
    }

    /**
     * 문자열 필드가 빠지지 않고 올바른 타입인지 확인한다.
     * 빈 문자열은 계약상 허용하므로 거부하지 않는다.
     */
    private boolean hasValidTextFields(JsonNode root) {
        for (String fieldName : TEXT_FIELDS) {
            JsonNode value = root.get(fieldName);

            if (value == null || !value.isTextual()) {
                return false;
            }
        }

        return true;
    }

    /**
     * track_id가 int32 정수이고 ready가 불리언인지 확인한다.
     */
    private boolean hasValidNumberAndBooleanFields(JsonNode root) {
        JsonNode trackId = root.get("track_id");

        if (trackId == null || !trackId.isIntegralNumber()) {
            return false;
        }

        if (!trackId.canConvertToInt()) {
            return false;
        }

        JsonNode ready = root.get("ready");

        return ready != null && ready.isBoolean();
    }

    /**
     * not_ready가 문자열 배열인지 확인한다.
     */
    private boolean hasValidNotReadyList(JsonNode root) {
        JsonNode notReady = root.get("not_ready");

        if (notReady == null || !notReady.isArray()) {
            return false;
        }

        for (JsonNode item : notReady) {
            if (!item.isTextual()) {
                return false;
            }
        }

        return true;
    }
}