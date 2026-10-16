package com.voss.web.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class VoiceStatusFilterTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private JsonNode event(String id, String utterance, String phase) {
        return mapper.createObjectNode().put("event_id", id).put("utterance_id", utterance).put("phase", phase);
    }

    @Test void retainedWakeIsNeverAccepted() {
        assertFalse(new VoiceStatusFilter().accept(event("e", "u", "WAKE_DETECTED"), true));
    }

    @Test void audioActivityIsAcceptedOnlyLive() {
        VoiceStatusFilter filter = new VoiceStatusFilter();
        assertTrue(filter.accept(event("audio-start", "audio", "AUDIO_DETECTED"), false));
        assertTrue(filter.accept(event("audio-end", "audio", "AUDIO_REJECTED"), false));
        assertFalse(filter.accept(event("old-audio", "old", "AUDIO_DETECTED"), true));
    }

    @Test void repeatedEventAndRepeatedWakeAreRejected() {
        VoiceStatusFilter filter = new VoiceStatusFilter();
        assertTrue(filter.accept(event("e1", "u1", "WAKE_DETECTED"), false));
        assertTrue(filter.accept(event("e2", "u2", "WAKE_DETECTED"), false));
        assertFalse(filter.accept(event("e1", "u1", "WAKE_DETECTED"), false));
        assertFalse(filter.accept(event("e3", "u1", "WAKE_DETECTED"), false));
        assertTrue(filter.accept(event("e4", "u2", "COMMAND_ACCEPTED"), false));
    }

    @Test void invalidIdsAndPhasesAreRejected() {
        VoiceStatusFilter filter = new VoiceStatusFilter();
        assertFalse(filter.accept(event(" ", "u", "WAKE_DETECTED"), false));
        assertFalse(filter.accept(event("e", " u", "WAKE_DETECTED"), false));
        assertFalse(filter.accept(event("e".repeat(129), "u", "WAKE_DETECTED"), false));
        assertFalse(filter.accept(event("e", "u", "NEW_PHASE"), false));
    }

    @Test void deduplicationMemoryExpiresAndIsBounded() {
        AtomicLong now = new AtomicLong();
        VoiceStatusFilter filter = new VoiceStatusFilter(now::get);
        JsonNode first = event("e", "u", "WAKE_DETECTED");
        assertTrue(filter.accept(first, false));
        now.set(601_000_000_000L);
        assertTrue(filter.accept(first, false));
        for (int i = 0; i < 1100; i++) assertTrue(filter.accept(event("e"+i, "u"+i, "WAKE_DETECTED"), false));
        assertTrue(filter.accept(first, false));
    }
}
