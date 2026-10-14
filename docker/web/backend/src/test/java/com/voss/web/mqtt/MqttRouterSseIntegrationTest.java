// 실제 MQTT/DB 없이 토픽 JSON → 라우터 → SSE HTTP 경로를 검증한다.
// 입력: 모의 MQTT JSON, 모의 session_plan 저장소, MockMvc SSE 연결.
// 출력: 브라우저에 전달할 event/data 및 새 세션 연결 호출 증거.
// 근거: docs/interfaces/mqtt.md (#20), web_api.md (#68).
package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.api.ApiException;
import com.voss.web.api.StreamController;
import com.voss.web.db.PlanRepository;
import com.voss.web.service.LiveEvents;
import com.voss.web.service.MqttLinkStatusStore;
import com.voss.web.service.SortStateStore;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;

class MqttRouterSseIntegrationTest {
    private static final String FIRST_SESSION = "20261010T143012-a3f9";
    private static final String SECOND_SESSION = "20261011T003012-b4f0";
    private static final String PALLET_STATE = """
            {"run_id":"20261013T100000-c3d4","state":"RUNNING","route":["대치동","역삼동","청담동"],
             "dongs":["대치동","역삼동","청담동"],"load":[3,7,6],"overflow":[3,0,0],"excluded":[0,0,0],
             "overflow_warning":true,"total":16,"done":0,"failed":0,"box_id":"",
             "slot_state":[],"slot_box_id":[],"slot_dong":[]}
            """;

    private final ObjectMapper mapper = new ObjectMapper();
    private final SortStateStore states = new SortStateStore();
    private final PlanRepository plans = mock(PlanRepository.class);
    private final LiveEvents live = new LiveEvents(mapper, new MqttLinkStatusStore());
    private final MqttEventRouter router = new MqttEventRouter(
            mapper, new MqttStateMessageHandler(mapper, states), states, live, plans);

    /** 모의 상태가 실제 HTTP SSE 본문에 전달되고 세션 수량이 한 번 연결되는지 확인한다. */
    @Test
    void testValidStateReachesSseAndAttachesNextPlanOnce() throws Exception {
        MvcResult stream = openSseStream();
        router.receive("voss/state", statePayload(FIRST_SESSION));
        router.receive("voss/state", statePayload(FIRST_SESSION));

        String body = stream.getResponse().getContentAsString();
        assertTrue(body.contains("event:state"));
        assertTrue(body.contains(FIRST_SESSION));
        assertEquals(FIRST_SESSION, states.getLatestState().orElseThrow().message().sessionId());
        verify(plans, times(1)).attachPending(FIRST_SESSION);
    }

    /** 첫 start 이전의 빈 세션은 next를 소비하지 않고 새 세션에만 붙인다. */
    @Test
    void testEmptySessionDoesNotAttachAndNewSessionDoes() {
        router.receive("voss/state", statePayload(""));
        verify(plans, never()).attachPending("");

        router.receive("voss/state", statePayload(FIRST_SESSION));
        router.receive("voss/state", statePayload(SECOND_SESSION));
        verify(plans).attachPending(FIRST_SESSION);
        verify(plans).attachPending(SECOND_SESSION);
    }

    /** DB 연결 실패에도 상태 SSE를 보존하고 다음 수신에서 연결을 재시도한다. */
    @Test
    void testPlanFailureDoesNotBlockStateSseAndIsRetried() throws Exception {
        ApiException failure = new ApiException(HttpStatus.SERVICE_UNAVAILABLE,
                "DB_ERROR", "테스트 DB 장애");
        doThrow(failure).doNothing().when(plans).attachPending(FIRST_SESSION);
        MvcResult stream = openSseStream();

        router.receive("voss/state", statePayload(FIRST_SESSION));
        assertTrue(stream.getResponse().getContentAsString().contains("event:state"));
        router.receive("voss/state", statePayload(FIRST_SESSION));
        verify(plans, times(2)).attachPending(FIRST_SESSION);
    }

    /** 결과·구역·로봇·ack·logger 이벤트가 HTTP SSE에 모두 도달하는지 확인한다. */
    @Test
    void testAllOtherInboundTopicsReachSse() throws Exception {
        MvcResult stream = openSseStream();
        router.receive("voss/result", "{\"box_id\":\"B1\",\"result\":\"PLACED\"}");
        router.receive("voss/zone_map", "{\"version\":\"v1\",\"entries\":[]}");
        router.receive("voss/robot", "{\"connected\":false,\"state\":\"IDLE\"}");
        router.receive("voss/command/ack", "{\"command_id\":\"test-id\",\"ok\":true}");
        router.receive("voss/log_status", "{\"status\":\"OK\"}");

        String body = stream.getResponse().getContentAsString();
        assertTrue(body.contains("event:result"));
        assertTrue(body.contains("event:zone_map"));
        assertTrue(body.contains("event:robot"));
        assertTrue(body.contains("event:command_ack"));
        assertTrue(body.contains("event:log_status"));
        verify(plans, never()).attachPending(FIRST_SESSION);
    }

    /** 늦게 연결한 브라우저는 retained 구역 지도 스냅샷을 받는다. */
    @Test
    void testLateSubscriberReceivesZoneMapSnapshot() throws Exception {
        router.receive("voss/zone_map", "{\"version\":\"snapshot-test\",\"entries\":[]}");
        MvcResult stream = openSseStream();
        assertTrue(stream.getResponse().getContentAsString().contains("snapshot-test"));
    }

    /** 잘못된 상태나 허용하지 않은 토픽은 SSE 및 세션 수량을 변경하지 않는다. */
    @Test
    void testInvalidStateAndUnknownTopicDoNotPublish() throws Exception {
        MvcResult stream = openSseStream();
        router.receive("voss/state", "{\"state\":\"RUNNING\"}");
        router.receive("voss/state", "not-json");
        router.receive("voss/unexpected", statePayload(FIRST_SESSION));

        String body = stream.getResponse().getContentAsString();
        assertFalse(body.contains("event:state"));
        assertTrue(states.getLatestState().isEmpty());
        verify(plans, never()).attachPending(FIRST_SESSION);
    }

    /** Sprint 2: 팔레트 배치도는 pallet_state 이벤트로 그대로 가고 늦은 브라우저도 스냅샷으로 받는다. */
    @Test
    void testPalletStateReachesSseAndSnapshot() throws Exception {
        MvcResult early = openSseStream();
        router.receive("voss/pallet/state", PALLET_STATE);
        assertTrue(early.getResponse().getContentAsString().contains("event:pallet_state"));
        assertTrue(early.getResponse().getContentAsString().contains("20261013T100000-c3d4"));

        MvcResult late = openSseStream();
        String body = late.getResponse().getContentAsString();
        assertTrue(body.contains("event:pallet_state"));
        assertTrue(body.contains("\"overflow_warning\":true"));
    }

    /** Sprint 2: 팔레타이징 중 SortState(PALLETIZING)를 버리지 않는다 — 버리면 3초 뒤 UNKNOWN. */
    @Test
    void testPalletizingStateIsAccepted() throws Exception {
        MvcResult stream = openSseStream();
        router.receive("voss/state", statePayload(FIRST_SESSION).replace("RUNNING", "PALLETIZING"));
        assertEquals("PALLETIZING", states.getLatestState().orElseThrow().message().state());
        assertTrue(stream.getResponse().getContentAsString().contains("PALLETIZING"));
    }

    /** 위치 이벤트는 실시간 전용이라 늦게 연결한 브라우저에 재생하지 않는다. */
    @Test
    void positionEventsAreNotReplayedToLateSubscribers() throws Exception {
        router.receive("voss/box_track", "{\"track_id\":7,\"position_valid\":true}");
        router.receive("voss/robot_pose", "{\"frame_id\":\"base_link\"}");
        router.receive("voss/robot_joints", "{\"name\":[],\"position\":[]}");
        router.receive("voss/box_motion", "{\"phase\":\"GRASPED\"}");
        String body = openSseStream().getResponse().getContentAsString();
        for (String name : new String[]{"box_track", "robot_pose", "robot_joints", "box_motion"}) {
            assertFalse(body.contains("event:" + name), name);
        }
    }

    /** 음성 이벤트는 기존 SSE로 전달하지만 새 연결에 과거 호출어를 재생하지 않는다. */
    @Test
    void voiceStatusIsLiveOnlyAndDeduplicated() throws Exception {
        MvcResult stream = openSseStream();
        String wake = "{\"phase\":\"WAKE_DETECTED\",\"event_id\":\"e1\",\"utterance_id\":\"u1\"}";
        router.receive("voss/voice_status", wake, true);
        assertFalse(stream.getResponse().getContentAsString().contains("event:voice_status"));
        router.receive("voss/voice_status", wake);
        String once = stream.getResponse().getContentAsString();
        assertTrue(once.contains("event:voice_status"));
        router.receive("voss/voice_status", wake);
        assertEquals(once, stream.getResponse().getContentAsString());
        MvcResult later = openSseStream();
        assertFalse(later.getResponse().getContentAsString().contains("event:voice_status"));
        router.receive("voss/voice_status", "{\"phase\":\"COMMAND_ACCEPTED\",\"event_id\":\"e2\",\"utterance_id\":\"u1\"}");
        assertTrue(stream.getResponse().getContentAsString().contains("COMMAND_ACCEPTED"));
        verify(plans, never()).attachPending(FIRST_SESSION);
    }

    /** 실제 브로커 대신 MockMvc로 SSE HTTP 연결을 만든다. */
    private MvcResult openSseStream() throws Exception {
        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new StreamController(live)).build();
        return mockMvc.perform(get("/api/stream"))
                .andExpect(request().asyncStarted())
                .andReturn();
    }

    /** 계약상 필수 SortState 필드를 모두 갖는 테스트 페이로드를 만든다. */
    private String statePayload(String sessionId) {
        return "{\"state\":\"RUNNING\",\"box_id\":\"B1\","
                + "\"pending_question\":\"\",\"track_id\":1,"
                + "\"ready\":true,\"not_ready\":[],\"session_id\":\"" + sessionId + "\"}";
    }
}
