package com.voss.web.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.voss.web.mqtt.MqttVoicePublisher;
import com.voss.web.service.TimeProvider;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 버튼 결과를 알리는 고정 문구만 Nodes PC TTS에 요청한다. */
@RestController
public class VoiceAnnouncementController {
    private static final Set<String> ACTIONS = Set.of(
            "start", "stop", "resume", "priority", "answer", "reset_zone", "palletize", "plan");
    private final MqttVoicePublisher publisher;
    private final TimeProvider clock;

    public VoiceAnnouncementController(MqttVoicePublisher publisher, TimeProvider clock) {
        this.publisher = publisher;
        this.clock = clock;
    }

    @PostMapping("/api/voice/announce")
    public ResponseEntity<Map<String, Object>> announce(@RequestBody JsonNode request,
                                                          HttpServletRequest servletRequest) {
        if (!"127.0.0.1".equals(servletRequest.getHeader("X-Real-IP"))
                && !"::1".equals(servletRequest.getHeader("X-Real-IP"))) {
            throw new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN_REMOTE",
                    "공용 PC 로컬에서만 음성 안내를 요청할 수 있습니다.");
        }
        if (!request.isObject() || request.size() != 1 || !request.path("action").isTextual()
                || !ACTIONS.contains(request.path("action").asText())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_VOICE_ACTION",
                    "허용된 버튼 동작만 음성 안내할 수 있습니다.");
        }
        String requestId = UUID.randomUUID().toString();
        publisher.publish(Map.of("request_id", requestId,
                "action", request.path("action").asText(), "sent_at", clock.now()));
        return ResponseEntity.accepted().body(Map.of("ok", true, "request_id", requestId));
    }
}
