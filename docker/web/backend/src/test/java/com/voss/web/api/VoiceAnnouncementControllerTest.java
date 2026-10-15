package com.voss.web.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.mqtt.MqttVoicePublisher;
import com.voss.web.service.TimeProvider;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class VoiceAnnouncementControllerTest {
    private final MqttVoicePublisher publisher = mock(MqttVoicePublisher.class);
    private final VoiceAnnouncementController controller =
            new VoiceAnnouncementController(publisher, new TimeProvider());
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void localButtonPublishesOnlyActionAndMetadata() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "127.0.0.1");
        var response = controller.announce(mapper.readTree("{\"action\":\"stop\"}"), request);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> sent = ArgumentCaptor.forClass(Map.class);
        verify(publisher).publish(sent.capture());
        assertEquals("stop", sent.getValue().get("action"));
        assertEquals(3, sent.getValue().size());
    }

    @Test
    void remoteAndArbitrarySpeechCannotPublish() throws Exception {
        MockHttpServletRequest remote = new MockHttpServletRequest();
        remote.addHeader("X-Real-IP", "192.0.2.1");
        assertEquals(HttpStatus.FORBIDDEN, assertThrows(ApiException.class, () ->
                controller.announce(mapper.readTree("{\"action\":\"stop\"}"), remote)).status());

        MockHttpServletRequest local = new MockHttpServletRequest();
        local.addHeader("X-Real-IP", "127.0.0.1");
        assertEquals(HttpStatus.BAD_REQUEST, assertThrows(ApiException.class, () ->
                controller.announce(mapper.readTree("{\"action\":\"start\",\"text\":\"임의 음성\"}"), local)).status());
        verify(publisher, never()).publish(org.mockito.ArgumentMatchers.anyMap());
    }

    @Test
    void forgedLocalHeaderFromRemotePeerCannotAnnounce() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "127.0.0.1");
        request.setRemoteAddr("192.0.2.20");
        assertEquals(HttpStatus.FORBIDDEN, assertThrows(ApiException.class, () ->
                controller.announce(mapper.readTree("{\"action\":\"start\"}"), request)).status());
        verify(publisher, never()).publish(org.mockito.ArgumentMatchers.anyMap());
    }
}
