// T13 #22 웹 명령의 접근 제한과 MQTT 발행 조건을 검증한다.
// 입력: 로컬/원격 헤더 및 모의 명령. 출력: HTTP 계약 판정.
// 근거: docs/interfaces/web_api.md stop 원격 허용.
package com.voss.web.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.mqtt.MqttCommandPublisher;
import com.voss.web.mqtt.MqttEventRouter;
import com.voss.web.service.SortStateStore;
import com.voss.web.service.TimeProvider;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class CommandControllerTest {
    private final MqttCommandPublisher publisher = mock(MqttCommandPublisher.class);
    private final MqttEventRouter router = mock(MqttEventRouter.class);
    private final CommandController controller = new CommandController(
            publisher, router, new SortStateStore(), new TimeProvider());
    private final ObjectMapper mapper = new ObjectMapper();

    /** 원격 start는 MQTT 발행 전에 거부한다. */
    @Test
    void testRemoteStartIsRejectedBeforePublishing() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.11");
        ApiException error = assertThrows(ApiException.class, () ->
                controller.command(mapper.readTree("{\"type\":\"start\",\"args\":{}}"), request));
        assertEquals("FORBIDDEN_REMOTE", error.code());
        assertEquals(HttpStatus.FORBIDDEN, error.status());
        verify(publisher, never()).publish(anyMap());
    }

    /** stop은 원격 요청이라도 발행 가능해야 한다. */
    @Test
    void testRemoteStopIsAllowed() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.11");
        var response = controller.command(mapper.readTree("{\"type\":\"stop\",\"args\":{}}"), request);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        verify(publisher).publish(anyMap());
    }

    /** X-Forwarded-For의 로컬 IP 위조를 믿지 않는다. */
    @Test
    void testForgedForwardedForIsNotTrusted() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.13");
        request.addHeader("X-Forwarded-For", "127.0.0.1");
        ApiException error = assertThrows(ApiException.class, () ->
                controller.command(mapper.readTree("{\"type\":\"resume\",\"args\":{}}"), request));
        assertEquals("FORBIDDEN_REMOTE", error.code());
    }

    /** 로컬 Nginx HMI는 실기 운전 플래그 없이도 start를 발행할 수 있다. */
    @Test
    void testLocalStartIsAllowedWithDefaultSettings() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "127.0.0.1");
        var response = controller.command(
                mapper.readTree("{\"type\":\"start\",\"args\":{}}"), request);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        verify(publisher).publish(anyMap());
    }

    /** 원격 운영자 IP는 기존 임시 설정과 무관하게 허용하지 않는다. */
    @Test
    void testRemoteOperatorIpCannotEnableStart() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.10");
        ApiException error = assertThrows(ApiException.class, () ->
                controller.command(mapper.readTree("{\"type\":\"start\",\"args\":{}}"), request));
        assertEquals("FORBIDDEN_REMOTE", error.code());
        verify(publisher, never()).publish(anyMap());
    }

    /** IPv6 loopback은 같은 공용 PC에서 사용되는 로컬 주소다. */
    @Test
    void testLocalIpv6IsAllowed() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "::1");
        var response = controller.command(
                mapper.readTree("{\"type\":\"resume\",\"args\":{}}"), request);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
    }

    /** stop은 원격에서도 args가 없어도 즉시 전달한다. */
    @Test
    void testRemoteStopWithoutArgsIsAccepted() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.12");
        var response = controller.command(mapper.readTree("{\"type\":\"stop\"}"), request);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        verify(publisher).publish(anyMap());
    }

    /** start 인자에 임의 키가 추가되면 발행하지 않는다. */
    @Test
    void testUnknownCommandArgsAreRejected() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "127.0.0.1");
        ApiException error = assertThrows(ApiException.class, () ->
                controller.command(mapper.readTree("{\"type\":\"start\",\"args\":{\"unsafe\":1}}"), request));
        assertEquals("INVALID_QUERY", error.code());
        verify(publisher, never()).publish(anyMap());
    }
}
