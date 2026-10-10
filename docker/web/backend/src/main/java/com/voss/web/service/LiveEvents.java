// MQTT 실시간 이벤트를 보관하고 Spring SSE 구독자에게 전달한다.
// 입력: JSON 이벤트와 MQTT 연결 상태. 출력: SSE 및 최신 스냅샷.
// 근거: docs/interfaces/web_api.md GET /api/stream.
package com.voss.web.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Service
public class LiveEvents {
    private static final Logger LOGGER = LoggerFactory.getLogger(LiveEvents.class);
    private static final long SSE_TIMEOUT_MS = 0L;
    private static final List<String> SNAPSHOT_EVENTS =
            List.of("state", "zone_map", "robot", "log_status");

    private final ObjectMapper mapper;
    private final MqttLinkStatusStore link;
    private final Map<String,JsonNode> latest = new ConcurrentHashMap<>();
    private volatile Instant lastStateReceivedAt;
    private final CopyOnWriteArrayList<SseEmitter> listeners = new CopyOnWriteArrayList<>();

    /** JSON 변환기와 MQTT 연결 상태 저장소를 주입한다. */
    public LiveEvents(ObjectMapper mapper, MqttLinkStatusStore link) {
        this.mapper = mapper;
        this.link = link;
    }

    /** 이벤트를 스냅샷에 반영하고 모든 연결된 브라우저로 보낸다. */
    public void publish(String eventName, JsonNode data) {
        if (SNAPSHOT_EVENTS.contains(eventName)) { latest.put(eventName, data.deepCopy()); }
        if ("state".equals(eventName)) { lastStateReceivedAt = Instant.now(); }
        for (SseEmitter listener : listeners) { send(listener, eventName, data); }
    }

    /** MQTT 연결 상태를 link SSE 데이터로 발행한다. */
    public void publishLink() {
        JsonNode data = mapper.valueToTree(Map.of("mqtt", link.getStatus().name()));
        publish("link", data);
    }

    /** 새 브라우저에 최신 상태와 MQTT 연결 정보를 순서대로 전송한다. */
    public SseEmitter subscribe() {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MS);
        emitter.onCompletion(() -> listeners.remove(emitter));
        emitter.onTimeout(() -> listeners.remove(emitter));
        emitter.onError(error -> listeners.remove(emitter));
        listeners.add(emitter);
        for (String name : SNAPSHOT_EVENTS) {
            JsonNode data = latest.get(name);
            if ("state".equals(name) && isStateStale()) { continue; }
            if (data != null) { send(emitter, name, data); }
        }
        send(emitter, "link", mapper.valueToTree(Map.of("mqtt", link.getStatus().name())));
        return emitter;
    }

    /** 새 브라우저에게 3초 이상 오래된 상태를 최신 상태로 다시 보내지 않는다. */
    private boolean isStateStale() {
        Instant lastReceived = lastStateReceivedAt;
        if (lastReceived == null) { return true; }
        return Duration.between(lastReceived, Instant.now()).toMillis() >= 3000;
    }

    /** 유휴 SSE 연결을 유지하기 위한 코멘트를 발행한다. */
    public void heartbeat() {
        for (SseEmitter listener : listeners) {
            try { listener.send(SseEmitter.event().comment("heartbeat")); }
            catch (IOException | IllegalStateException exception) { listeners.remove(listener); }
        }
    }

    /** 한 브라우저로 이벤트를 보내고 끊긴 구독자는 제거한다. */
    private void send(SseEmitter listener, String eventName, JsonNode data) {
        try { listener.send(SseEmitter.event().name(eventName).data(data, MediaType.APPLICATION_JSON)); }
        catch (IOException | IllegalStateException exception) {
            listeners.remove(listener);
            LOGGER.debug("SSE 수신 연결 종료: {}", eventName);
        }
    }
}
