// T13 #22 MQTT voss/state JSON 변환 계약을 검증한다.
// 입력: mqtt.md의 필드 구조를 따르는 모의 JSON.
// 출력: JUnit 테스트 통과 또는 실패.
// 근거: docs/interfaces/mqtt.md, voss_msgs.md.

package com.voss.web.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SortStateMessageTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private static final String STATE_JSON = """
            {
              "state": "IDLE",
              "box_id": "",
              "pending_question": "",
              "track_id": -1,
              "ready": false,
              "not_ready": ["ROBOT", "LOG"],
              "session_id": ""
            }
            """;

    /**
     * MQTT JSON의 필드가 Java 객체에 정확히 들어오는지 검사한다.
     */
    @Test
    void testMqttJsonFieldsAreDeserializedCorrectly() throws Exception {
        SortStateMessage message = OBJECT_MAPPER.readValue(
                STATE_JSON, SortStateMessage.class
        );

        assertEquals("IDLE", message.state());
        assertEquals("", message.boxId());
        assertEquals("", message.pendingQuestion());
        assertEquals(-1, message.trackId());
        assertFalse(message.ready());
        assertEquals(2, message.notReady().size());
        assertEquals("ROBOT", message.notReady().get(0));
        assertEquals("LOG", message.notReady().get(1));
    }

    /**
     * 첫 start 이전의 빈 session_id를 임의로 변경하지 않는지 검사한다.
     */
    @Test
    void testEmptySessionIdIsPreserved() throws Exception {
        SortStateMessage message = OBJECT_MAPPER.readValue(
                STATE_JSON, SortStateMessage.class
        );

        assertEquals("", message.sessionId());
    }

    /**
     * Java 객체를 다시 JSON으로 바꿀 때 계약 필드명을 유지한다.
     */
    @Test
    void testSerializedJsonUsesMqttFieldNames() throws Exception {
        SortStateMessage message = OBJECT_MAPPER.readValue(
                STATE_JSON, SortStateMessage.class
        );

        JsonNode json = OBJECT_MAPPER.readTree(
                OBJECT_MAPPER.writeValueAsString(message)
        );

        assertTrue(json.has("box_id"));
        assertTrue(json.has("pending_question"));
        assertTrue(json.has("track_id"));
        assertTrue(json.has("not_ready"));
        assertTrue(json.has("session_id"));
        assertFalse(json.has("boxId"));
        assertEquals(7, json.size());
        assertEquals("", json.get("session_id").asText());
    }
}