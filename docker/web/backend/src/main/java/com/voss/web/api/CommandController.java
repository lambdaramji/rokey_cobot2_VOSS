// HMI 명령을 검증·로컬 접근 제한 후 MQTT voss/command에 발행한다.
// 입력: POST /api/commands JSON 및 Nginx X-Real-IP. 출력: 202 command_id.
// 근거: docs/interfaces/web_api.md, mqtt.md (stop 원격 허용).
package com.voss.web.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.voss.web.mqtt.MqttCommandPublisher;
import com.voss.web.mqtt.MqttEventRouter;
import com.voss.web.service.SortStateStore;
import com.voss.web.service.TimeProvider;
import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CommandController {
    private static final Set<String> COMMAND_TYPES =
            Set.of("start", "stop", "resume", "priority", "answer", "reset_zone");
    private static final Set<String> RESET_ZONES = Set.of("A", "B", "C", "RECHECK", "HOLD");
    private final MqttCommandPublisher publisher;
    private final MqttEventRouter router;
    private final SortStateStore states;
    private final TimeProvider clock;

    // 2대 PC 시험 중에는 웹 PC의 localhost를 공용 PC로 오인하지 않는다.
    // 비-stop 명령은 별도 현장 승인 후에만 열 수 있다 (deployment_two_pc_trial.md).
    @Value("${VOSS_NONSTOP_COMMANDS_ENABLED:false}")
    private boolean nonstopCommandsEnabled;

    @Value("${VOSS_OPERATOR_IP:127.0.0.1}")
    private String operatorIp = "127.0.0.1";

    /** 명령 발행과 zone_map·현재 질문 정보를 연결한다. */
    public CommandController(MqttCommandPublisher publisher, MqttEventRouter router,
                             SortStateStore states, TimeProvider clock) {
        this.publisher = publisher;
        this.router = router;
        this.states = states;
        this.clock = clock;
    }

    /** stop 외의 명령은 로컬에서만 받아 검증 후 202를 반환한다. */
    @PostMapping("/api/commands")
    public ResponseEntity<Map<String,Object>> command(@RequestBody JsonNode request,
                                                        HttpServletRequest servletRequest) {
        if (!request.isObject() || !request.path("type").isTextual()) { throw invalid(); }
        String type = request.path("type").asText();
        if (!COMMAND_TYPES.contains(type)) { throw invalid(); }
        if (!"stop".equals(type) && (!nonstopCommandsEnabled || !isOperator(servletRequest))) {
            throw new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN_REMOTE", "공용 PC에서만 제어할 수 있습니다.");
        }
        JsonNode args = request.get("args");
        if (args == null || !args.isObject()) { throw invalid(); }
        validate(type, args);
        JsonNode raw = request.path("raw_text");
        if (!raw.isMissingNode() && !raw.isTextual()) { throw invalid(); }
        String rawText = raw.isTextual() ? raw.asText() : "HMI 버튼";
        String commandId = UUID.randomUUID().toString();
        Map<String,Object> command = new LinkedHashMap<>();
        command.put("command_id", commandId);
        command.put("type", type);
        command.put("args", args);
        command.put("raw_text", rawText);
        command.put("sent_at", clock.now());
        publisher.publish(command);
        return ResponseEntity.accepted().body(Map.of("ok", true, "command_id", commandId));
    }

    /** Nginx가 덮어쓴 X-Real-IP와 지정된 운영자 PC만 비교한다. IP는 강한 인증이 아니다. */
    private boolean isOperator(HttpServletRequest request) {
        String realIp = request.getHeader("X-Real-IP");
        if (operatorIp.equals(realIp)) { return true; }
        return "127.0.0.1".equals(operatorIp) && "::1".equals(realIp);
    }

    /** 명령별 허용 인자 외에는 ROS로 전달하지 않는다. */
    private void validate(String type, JsonNode args) {
        if (Set.of("start", "stop", "resume").contains(type)) {
            if (args.size() != 0) { throw invalid(); }
            return;
        }
        if ("priority".equals(type)) {
            if (!hasOnlyText(args, "dong") || !router.isCanonicalDong(args.path("dong").asText())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "UNKNOWN_DONG", "zone_map의 정식 동 이름을 지정하세요.");
            }
            return;
        }
        if ("reset_zone".equals(type)) {
            if (!hasOnlyText(args, "zone") || !RESET_ZONES.contains(args.path("zone").asText())) {
                throw invalid();
            }
            return;
        }
        validateAnswer(args);
    }

    /** answer는 box_id와 dong/zone 중 하나만 허용한다. */
    private void validateAnswer(JsonNode args) {
        if (!args.path("box_id").isTextual() || args.path("box_id").asText().isBlank()) { throw invalid(); }
        String askingBox = states.getLatestState().map(snapshot -> snapshot.message().boxId()).orElse("");
        if (!args.path("box_id").asText().equals(askingBox) || askingBox.isEmpty()) { throw invalid(); }
        boolean hasDong = args.has("dong");
        boolean hasZone = args.has("zone");
        if (hasDong == hasZone || args.size() != 2) { throw invalid(); }
        if (hasDong && (!args.path("dong").isTextual()
                || !router.isCanonicalDong(args.path("dong").asText()))) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "UNKNOWN_DONG", "정식 동 이름을 지정하세요.");
        }
        if (hasZone && !"HOLD".equals(args.path("zone").asText())) { throw invalid(); }
    }

    /** 인자가 정확히 하나의 텍스트 필드인지 검사한다. */
    private boolean hasOnlyText(JsonNode args, String key) {
        return args.size() == 1 && args.path(key).isTextual() && !args.path(key).asText().isBlank();
    }

    /** 잘못된 명령을 실제 MQTT로 발행하지 않는다. */
    private ApiException invalid() { return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_QUERY", "명령 인자 형식이 올바르지 않습니다."); }
}
