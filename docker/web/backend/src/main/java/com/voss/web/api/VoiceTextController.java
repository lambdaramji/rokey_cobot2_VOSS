package com.voss.web.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.voss.web.mqtt.MqttTextPublisher;
import com.voss.web.service.TimeProvider;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 타이핑한 문장을 기존 ROS intent_parser에만 전달한다. */
@RestController
public class VoiceTextController {
    private final MqttTextPublisher publisher;
    private final TimeProvider clock;

    public VoiceTextController(MqttTextPublisher publisher, TimeProvider clock) {
        this.publisher = publisher;
        this.clock = clock;
    }

    @PostMapping("/api/voice/text")
    public ResponseEntity<Map<String, Object>> submit(@RequestBody JsonNode request,
                                                        HttpServletRequest servletRequest) {
        String realIp = servletRequest.getHeader("X-Real-IP");
        String peerIp = servletRequest.getRemoteAddr();
        if ((!"127.0.0.1".equals(realIp) && !"::1".equals(realIp))
                || (!"127.0.0.1".equals(peerIp) && !"::1".equals(peerIp))) {
            throw new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN_REMOTE",
                    "Web PC 로컬에서만 텍스트 명령을 입력할 수 있습니다.");
        }
        if (!request.isObject() || request.size() != 2 || !request.path("text").isTextual()
                || !request.path("request_id").isTextual()) {
            throw invalid();
        }
        String requestId = request.path("request_id").asText();
        try {
            if (!UUID.fromString(requestId).toString().equals(requestId)) { throw invalid(); }
        } catch (IllegalArgumentException exception) {
            throw invalid();
        }
        String text = request.path("text").asText().trim();
        if (text.isEmpty() || text.length() > 240 || text.chars().anyMatch(c -> c < 32 && c != '\t')) {
            throw invalid();
        }
        publisher.publish(Map.of("request_id", requestId, "text", text, "sent_at", clock.now()));
        return ResponseEntity.accepted().body(Map.of("ok", true, "request_id", requestId));
    }

    private ApiException invalid() {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_TEXT", "1~240자의 명령을 입력하세요.");
    }
}
