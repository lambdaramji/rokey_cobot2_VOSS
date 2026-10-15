package com.voss.web.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.mqtt.MqttTextPublisher;
import com.voss.web.service.TimeProvider;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class VoiceTextControllerTest {
    private final MqttTextPublisher publisher = mock(MqttTextPublisher.class);
    private final VoiceTextController controller = new VoiceTextController(publisher, new TimeProvider());
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void localTextUsesExistingIntentPath() throws Exception {
        String id = UUID.randomUUID().toString();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "127.0.0.1");
        var response = controller.submit(mapper.readTree("{\"request_id\":\"" + id
                + "\",\"text\":\"팔레타이징 실행해\"}"), request);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> sent = ArgumentCaptor.forClass(Map.class);
        verify(publisher).publish(sent.capture());
        assertEquals(id, sent.getValue().get("request_id"));
        assertEquals("팔레타이징 실행해", sent.getValue().get("text"));
    }

    @Test
    void remoteAndMalformedTextCannotPublish() throws Exception {
        String id = UUID.randomUUID().toString();
        var body = mapper.readTree("{\"request_id\":\"" + id + "\",\"text\":\"시작\"}");
        MockHttpServletRequest remote = new MockHttpServletRequest();
        remote.addHeader("X-Real-IP", "192.0.2.1");
        assertEquals(HttpStatus.FORBIDDEN,
                assertThrows(ApiException.class, () -> controller.submit(body, remote)).status());
        MockHttpServletRequest spoofed = new MockHttpServletRequest();
        spoofed.setRemoteAddr("192.0.2.1");
        spoofed.addHeader("X-Real-IP", "127.0.0.1");
        assertEquals(HttpStatus.FORBIDDEN,
                assertThrows(ApiException.class, () -> controller.submit(body, spoofed)).status());
        MockHttpServletRequest local = new MockHttpServletRequest();
        local.addHeader("X-Real-IP", "127.0.0.1");
        assertEquals(HttpStatus.BAD_REQUEST,
                assertThrows(ApiException.class, () -> controller.submit(
                        mapper.readTree("{\"request_id\":\"" + id + "\",\"text\":\"  \"}"), local)).status());
        verify(publisher, never()).publish(org.mockito.ArgumentMatchers.anyMap());
    }
}
