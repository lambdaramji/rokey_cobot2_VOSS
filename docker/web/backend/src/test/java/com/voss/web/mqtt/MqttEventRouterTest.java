// T13 #22 MQTT 상태·구역 데이터 라우팅의 계약을 검증한다.
// 입력: 모의 MQTT 토픽과 JSON. 출력: 최신 상태 및 정식 동 목록.
// 근거: docs/interfaces/mqtt.md.
package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.service.LiveEvents;
import com.voss.web.service.MqttLinkStatusStore;
import com.voss.web.service.SortStateStore;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MqttEventRouterTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private final SortStateStore stateStore = new SortStateStore();
    private final MqttEventRouter router = new MqttEventRouter(mapper,
            new MqttStateMessageHandler(mapper, stateStore), stateStore,
            new LiveEvents(mapper, new MqttLinkStatusStore()));

    /** 명세에 없는 상태는 최신값으로 저장하지 않는다. */
    @Test
    void testInvalidStatePayloadIsNotStored() {
        router.receive("voss/state", "{\"state\":\"RUNNING\"}");
        assertTrue(stateStore.getLatestState().isEmpty());
    }

    /** 정식 동은 허용하되 별칭은 웹 명령용으로 허용하지 않는다. */
    @Test
    void testZoneMapAcceptsOnlyCanonicalDong() {
        router.receive("voss/zone_map", """
                {"version":"v1","entries":[{"dong":"역삼동","zone":"A","code":"S1","aliases":["역삼"]}]}
                """);
        assertTrue(router.isCanonicalDong("역삼동"));
        assertFalse(router.isCanonicalDong("역삼"));
    }

    /** 정상 MQTT SortState 메시지는 원형대로 전달한다. */
    @Test
    void testValidStatePayloadUpdatesStore() {
        router.receive("voss/state", """
                {"state":"RUNNING","box_id":"B1","pending_question":"","track_id":1,
                 "ready":true,"not_ready":[],"session_id":"20261010T143012-a3f9"}
                """);
        assertEquals("B1", stateStore.getLatestState().orElseThrow().message().boxId());
    }
}
