// 분류 통계와 이력, CSV 내보내기를 PostgreSQL sort_log에서 제공한다.
// 입력: REST query_kind·동·세션·결과 필터. 출력: 계약 JSON과 CSV.
// 근거: docs/interfaces/web_api.md (#52 MC-021·022, #54 MC-030).
package com.voss.web.api;

import com.voss.web.db.HistoryRepository;
import com.voss.web.db.PlanRepository;
import com.voss.web.mqtt.MqttEventRouter;
import com.voss.web.service.CurrentSession;
import com.voss.web.service.TimeProvider;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HistoryController {
    private static final Set<String> OUTCOMES = Set.of("PLACED", "HELD", "FAILED", "PASSED");
    private final HistoryRepository history;
    private final MqttEventRouter mqttRouter;
    private final PlanRepository plans;
    private final CurrentSession sessions;
    private final TimeProvider clock;

    /** 조회 대상과 현재 세션·시계 서비스를 연결한다. */
    public HistoryController(HistoryRepository history, PlanRepository plans,
                             CurrentSession sessions, TimeProvider clock, MqttEventRouter mqttRouter) {
        this.history = history;
        this.mqttRouter = mqttRouter;
        this.plans = plans;
        this.sessions = sessions;
        this.clock = clock;
    }

    /** 지정한 분류 유형을 공식 DB에서 계산한다. */
    @GetMapping("/api/stats")
    public Map<String,Object> stats(@RequestParam("query_kind") String queryKind,
                                    @RequestParam(required = false) String dong,
                                    @RequestParam(name = "session_id", required = false) String sessionId) {
        String selected = sessions.resolve(sessionId);
        long count;
        if ("count_by_dong".equals(queryKind)) {
            if (dong == null || dong.isBlank()) { throw invalid("dong이 필요합니다."); }
            if (!mqttRouter.isCanonicalDong(dong)) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "UNKNOWN_DONG", "zone_map의 정식 동 이름이 아닙니다.");
            }
            count = history.placedByDong(selected, dong);
        } else if ("held_count".equals(queryKind)) {
            count = history.held(selected);
        } else if ("remaining_count".equals(queryKind)) {
            // 현재 세션 계획 수량이 공식 남은 수 계산의 기준이다.
            if ("all".equals(selected)) { throw invalid("remaining_count에는 실제 세션이 필요합니다."); }
            count = Math.max(plans.planned(selected) - history.completed(selected), 0);
        } else {
            throw invalid("허용되지 않은 query_kind입니다.");
        }
        Map<String,Object> body = new LinkedHashMap<>();
        body.put("ok", true);
        body.put("query_kind", queryKind);
        if (dong != null && "count_by_dong".equals(queryKind)) { body.put("dong", dong); }
        body.put("session_id", selected);
        body.put("count", count);
        body.put("as_of", clock.now());
        return body;
    }

    /** 세션과 결과 유형으로 공식 이력을 검색한다. */
    @GetMapping("/api/results")
    public Map<String,Object> results(@RequestParam(name = "session_id", required = false) String sessionId,
                                      @RequestParam(required = false) String result,
                                      @RequestParam(defaultValue = "50") int limit) {
        if (limit < 1 || limit > 500) { throw invalid("limit은 1~500입니다."); }
        String selected = sessions.resolve(sessionId);
        List<String> outcomes = parseOutcomes(result);
        return Map.of("ok", true, "items", history.results(selected, outcomes, limit), "as_of", clock.now());
    }

    /** sort_log 전체 컬럼과 cycle_s를 CSV로 다운로드한다. */
    @GetMapping(value = "/api/export.csv", produces = "text/csv")
    public ResponseEntity<byte[]> export(@RequestParam(name = "session_id", required = false) String sessionId) {
        String selected = sessions.resolve(sessionId);
        String csv = toCsv(history.exportRows(selected));
        byte[] content = ("\uFEFF" + csv).getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=sort_log.csv")
                .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
                .body(content);
    }

    /** 허용된 분류 결과만 SQL 조건에 전달한다. */
    private List<String> parseOutcomes(String text) {
        if (text == null || text.isBlank()) { return List.of(); }
        List<String> outcomes = new ArrayList<>();
        for (String token : text.split(",", -1)) {
            if (!OUTCOMES.contains(token)) { throw invalid("허용되지 않은 result입니다."); }
            outcomes.add(token);
        }
        return outcomes;
    }

    /** CSV에서 쉼표·따옴표·개행을 안전하게 이스케이프한다. */
    private String csvCell(Object value) {
        if (value == null) { return ""; }
        String text = String.valueOf(value);
        // OCR 문자열을 CSV 수식으로 실행하지 않도록 스프레드시트 위험 문자를 막는다.
        if (!text.isEmpty() && "=+-@\t\r".indexOf(text.charAt(0)) >= 0) {
            text = "'" + text;
        }
        return "\"" + text.replace("\"", "\"\"") + "\"";
    }

    /** 컬럼 순서를 유지하며 전체 이력을 CSV 문자열로 만든다. */
    private String toCsv(List<Map<String,Object>> rows) {
        if (rows.isEmpty()) { return ""; }
        StringBuilder csv = new StringBuilder();
        csv.append(String.join(",", rows.get(0).keySet())).append("\r\n");
        for (Map<String,Object> row : rows) {
            List<String> cells = new ArrayList<>();
            for (Object value : row.values()) { cells.add(csvCell(value)); }
            csv.append(String.join(",", cells)).append("\r\n");
        }
        return csv.toString();
    }

    /** 허용되지 않은 조회 인자를 계약 오류로 반환한다. */
    private ApiException invalid(String reason) {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_QUERY", reason);
    }
}
