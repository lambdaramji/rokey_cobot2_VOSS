package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.LongSupplier;

/** 음성 표시 이벤트만 검증하고 최근 중복을 제한된 메모리에서 제거한다. */
final class VoiceStatusFilter {
    private static final Set<String> PHASES = Set.of(
            "WAKE_DETECTED", "COMMAND_ACCEPTED", "RECOGNITION_FAILED", "TIMED_OUT");
    private static final long TTL_NS = 600_000_000_000L;
    private static final int MAX_IDS = 1024;
    private final Map<String, Long> seen = new LinkedHashMap<>();
    private final LongSupplier clock;

    VoiceStatusFilter() { this(System::nanoTime); }
    VoiceStatusFilter(LongSupplier clock) { this.clock = clock; }

    /** retained 메시지는 과거 호출어일 수 있으므로 처음 보는 ID라도 받지 않는다. */
    synchronized boolean accept(JsonNode data, boolean retained) {
        if (retained || !valid(data)) return false;
        long now = clock.getAsLong();
        seen.entrySet().removeIf(entry -> now - entry.getValue() > TTL_NS);
        String eventKey = "event:" + data.path("event_id").asText();
        String wakeKey = "wake:" + data.path("utterance_id").asText();
        boolean wake = "WAKE_DETECTED".equals(data.path("phase").asText());
        if (seen.containsKey(eventKey) || (wake && seen.containsKey(wakeKey))) return false;
        seen.put(eventKey, now);
        if (wake) seen.put(wakeKey, now);
        while (seen.size() > MAX_IDS) seen.remove(seen.keySet().iterator().next());
        return true;
    }

    private boolean valid(JsonNode data) {
        return data != null && data.isObject() && data.path("phase").isTextual()
                && PHASES.contains(data.path("phase").asText())
                && validId(data.path("event_id")) && validId(data.path("utterance_id"));
    }

    private boolean validId(JsonNode value) {
        if (!value.isTextual()) return false;
        String id = value.asText();
        return !id.isBlank() && id.length() <= 128 && id.equals(id.strip());
    }
}
