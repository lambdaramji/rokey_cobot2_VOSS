// T13 #22 웹 명령의 접근 제한과 MQTT 발행 조건을 검증한다.
// 입력: 로컬/원격 헤더 및 모의 명령. 출력: HTTP 계약 판정.
// 근거: docs/interfaces/web_api.md stop 원격 허용.
package com.voss.web.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voss.web.mqtt.MqttCommandPublisher;
import com.voss.web.mqtt.MqttEventRouter;
import com.voss.web.service.SortStateStore;
import com.voss.web.service.TimeProvider;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

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

    @Test
    void testRecheckUsesEmptyArgsAndRejectsRemote() throws Exception {
        var response = controller.command(
                mapper.readTree("{\"type\":\"recheck\",\"args\":{}}"), local());
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        ApiException error = assertThrows(ApiException.class, () -> controller.command(
                mapper.readTree("{\"type\":\"recheck\",\"args\":{}}"), remote()));
        assertEquals("FORBIDDEN_REMOTE", error.code());
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

    /** Sprint 2: 정식 동 1~3개 경로는 args 그대로(배열) MQTT 로 발행한다. */
    @Test
    @SuppressWarnings("unchecked")
    void testLocalPalletizePublishesRouteAsIs() throws Exception {
        canonical("대치동", "역삼동", "청담동");
        var response = controller.command(mapper.readTree(
                "{\"type\":\"palletize\",\"args\":{\"route\":[\"대치동\",\"역삼동\",\"청담동\"]}}"), local());
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        ArgumentCaptor<Map<String,Object>> sent = ArgumentCaptor.forClass(Map.class);
        verify(publisher).publish(sent.capture());
        assertEquals("palletize", sent.getValue().get("type"));
        JsonNode args = (JsonNode) sent.getValue().get("args");
        assertEquals(List.of("대치동", "역삼동", "청담동"),
                List.of(args.path("route").get(0).asText(), args.path("route").get(1).asText(),
                        args.path("route").get(2).asText()));
    }

    /** Sprint 2: palletize는 로봇을 움직이므로 원격에서 받지 않는다. */
    @Test
    void testRemotePalletizeIsRejected() throws Exception {
        canonical("역삼동");
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.11");
        ApiException error = assertThrows(ApiException.class, () -> controller.command(
                mapper.readTree("{\"type\":\"palletize\",\"args\":{\"route\":[\"역삼동\"]}}"), request));
        assertEquals("FORBIDDEN_REMOTE", error.code());
        verify(publisher, never()).publish(anyMap());
    }

    /** Sprint 2: 0개·4개·중복·빈 이름·문자열 아님·다른 키·배열 아님은 형식 오류로 발행하지 않는다. */
    @Test
    void testMalformedRoutesAreRejected() throws Exception {
        canonical("대치동", "역삼동", "청담동", "신사동");
        for (String args : List.of(
                "{\"route\":[]}",
                "{\"route\":[\"대치동\",\"역삼동\",\"청담동\",\"신사동\"]}",
                "{\"route\":[\"역삼동\",\"역삼동\"]}",
                "{\"route\":[\" \"]}",
                "{\"route\":[1]}",
                "{\"route\":[\"역삼동\"],\"unsafe\":1}",
                "{\"route\":\"역삼동,대치동\"}",
                "{}")) {
            ApiException error = assertThrows(ApiException.class, () -> controller.command(
                    mapper.readTree("{\"type\":\"palletize\",\"args\":" + args + "}"), local()), args);
            assertEquals("INVALID_QUERY", error.code(), args);
        }
        verify(publisher, never()).publish(anyMap());
    }

    /** Sprint 2: 별칭·미등록 동은 UNKNOWN_DONG 으로 발행하지 않는다. */
    @Test
    void testNonCanonicalRouteDongIsRejected() throws Exception {
        canonical("역삼동");
        ApiException error = assertThrows(ApiException.class, () -> controller.command(
                mapper.readTree("{\"type\":\"palletize\",\"args\":{\"route\":[\"역삼동\",\"대치\"]}}"), local()));
        assertEquals("UNKNOWN_DONG", error.code());
        verify(publisher, never()).publish(anyMap());
    }

    /** Sprint 2: reset_zone 에 PALLET 을 받는다. */
    @Test
    void testResetPalletZoneIsAccepted() throws Exception {
        var response = controller.command(mapper.readTree(
                "{\"type\":\"reset_zone\",\"args\":{\"zone\":\"PALLET\"}}"), local());
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        verify(publisher).publish(anyMap());
    }

    /** 공용 PC 로컬 Nginx 요청. */
    private MockHttpServletRequest local() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "127.0.0.1");
        return request;
    }

    private MockHttpServletRequest remote() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Real-IP", "192.0.2.11");
        return request;
    }

    /** 모의 zone_map 의 정식 동 이름. */
    private void canonical(String... dongs) {
        Set<String> names = Set.of(dongs);
        when(router.isCanonicalDong(anyString())).thenAnswer(call -> names.contains(call.getArgument(0, String.class)));
    }
}
