// T13 #22 MQTT 상태 JSON 처리 동작을 단위시험한다.
// 입력: 정상·비정상 MQTT JSON 문자열.
// 출력: 최신 상태의 저장 여부와 기존 상태 보존 검증.
// 근거: docs/interfaces/mqtt.md, web_api.md.

package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.voss.web.dto.SortStateMessage;
import com.voss.web.service.SortStateStore;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MqttStateMessageHandlerTest {

    private static final String VALID_STATE_JSON = """
            {
              "state": "RUNNING",
              "box_id": "BOX-001",
              "pending_question": "",
              "track_id": 7,
              "ready": true,
              "not_ready": [],
              "session_id": "20261010T143012-a3f9"
            }
            """;

    private final SortStateStore stateStore = new SortStateStore();

    private final MqttStateMessageHandler handler =
            new MqttStateMessageHandler(
                    new ObjectMapper(),
                    stateStore
            );

    /**
     * 정상 JSON을 받았을 때 최신 상태가 저장되는지 검사한다.
     */
    @Test
    void testValidJsonUpdatesLatestState() {
        handler.handle(VALID_STATE_JSON);

        assertTrue(stateStore.getLatestState().isPresent());
        assertFalse(stateStore.isStale());

        SortStateMessage message = stateStore.getLatestState()
                .orElseThrow()
                .message();

        assertEquals("RUNNING", message.state());
        assertEquals("BOX-001", message.boxId());
        assertEquals(7, message.trackId());
        assertTrue(message.ready());
        assertEquals("20261010T143012-a3f9", message.sessionId());
    }

    /**
     * 잘못된 JSON을 받더라도 이전 정상 상태를 유지한다.
     */
    @Test
    void testMalformedJsonDoesNotReplaceValidState() {
        handler.handle(VALID_STATE_JSON);

        SortStateStore.StateSnapshot previousState =
                stateStore.getLatestState().orElseThrow();

        handler.handle("{\"state\":");

        SortStateStore.StateSnapshot currentState =
                stateStore.getLatestState().orElseThrow();

        assertSame(previousState, currentState);
    }

    /**
     * 빈 문자열이나 null 입력은 상태를 변경하지 않는다.
     */
    @Test
    void testBlankPayloadDoesNotReplaceValidState() {
        handler.handle(VALID_STATE_JSON);

        SortStateStore.StateSnapshot previousState =
                stateStore.getLatestState().orElseThrow();

        handler.handle("");
        handler.handle("   ");
        handler.handle(null);

        SortStateStore.StateSnapshot currentState =
                stateStore.getLatestState().orElseThrow();

        assertSame(previousState, currentState);
    }

    /**
     * JSON null을 수신해도 기존 상태를 유지한다.
     */
    @Test
    void testJsonNullDoesNotReplaceValidState() {
        handler.handle(VALID_STATE_JSON);

        SortStateStore.StateSnapshot previousState =
                stateStore.getLatestState().orElseThrow();

        handler.handle("null");

        SortStateStore.StateSnapshot currentState =
                stateStore.getLatestState().orElseThrow();

        assertSame(previousState, currentState);
    }

        /**
     * 필수 필드 7개 중 하나라도 없으면 메시지를 거부한다.
     */
    @Test
    void testMissingRequiredFieldsAreRejected() throws Exception {
        String[] requiredFields = {
                "state",
                "box_id",
                "pending_question",
                "track_id",
                "ready",
                "not_ready",
                "session_id"
        };

        for (String fieldName : requiredFields) {
            ObjectNode json = createValidJsonNode();
            json.remove(fieldName);

            assertInvalidJsonKeepsLastState(json.toString());
        }
    }

    /**
     * 필드 타입이 계약과 다르면 상태를 저장하지 않는다.
     */
    @Test
    void testIncorrectFieldTypesAreRejected() throws Exception {
        ObjectNode invalidReady = createValidJsonNode();
        invalidReady.put("ready", "true");
        assertInvalidJsonKeepsLastState(invalidReady.toString());

        ObjectNode invalidBoxId = createValidJsonNode();
        invalidBoxId.put("box_id", 123);
        assertInvalidJsonKeepsLastState(invalidBoxId.toString());

        ObjectNode invalidTrackId = createValidJsonNode();
        invalidTrackId.put("track_id", "7");
        assertInvalidJsonKeepsLastState(invalidTrackId.toString());
    }

    /**
     * not_ready 배열에 문자열이 아닌 값이 있으면 거부한다.
     */
    @Test
    void testNotReadyListRejectsNonStringValues() throws Exception {
        ObjectNode json = createValidJsonNode();
        json.putArray("not_ready").add(123);

        assertInvalidJsonKeepsLastState(json.toString());
    }

    /**
     * 정의되지 않은 상태와 int32 범위 밖의 track_id를 거부한다.
     */
    @Test
    void testInvalidStateAndTrackIdOverflowAreRejected()
            throws Exception {
        ObjectNode invalidState = createValidJsonNode();
        invalidState.put("state", "INVALID");
        assertInvalidJsonKeepsLastState(invalidState.toString());

        ObjectNode invalidTrackId = createValidJsonNode();
        invalidTrackId.put("track_id", 2147483648L);
        assertInvalidJsonKeepsLastState(invalidTrackId.toString());
    }

    /**
     * 첫 start 이전의 빈 session_id는 정상 데이터로 허용한다.
     */
    @Test
    void testEmptySessionIdIsAccepted() throws Exception {
        ObjectNode json = createValidJsonNode();
        json.put("session_id", "");

        handler.handle(json.toString());

        SortStateMessage message = stateStore.getLatestState()
                .orElseThrow()
                .message();

        assertEquals("", message.sessionId());
    }

    /**
     * 정상 MQTT JSON을 수정 가능한 테스트 객체로 변환한다.
     */
    private ObjectNode createValidJsonNode() throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();

        return (ObjectNode) objectMapper.readTree(VALID_STATE_JSON);
    }

    /**
     * 잘못된 JSON을 입력해도 직전 정상 상태가 유지되는지 확인한다.
     */
    private void assertInvalidJsonKeepsLastState(
            String invalidJson
    ) {
        handler.handle(VALID_STATE_JSON);

        SortStateStore.StateSnapshot previousState =
                stateStore.getLatestState().orElseThrow();

        handler.handle(invalidJson);

        SortStateStore.StateSnapshot currentState =
                stateStore.getLatestState().orElseThrow();

        assertSame(previousState, currentState);
    }
}
