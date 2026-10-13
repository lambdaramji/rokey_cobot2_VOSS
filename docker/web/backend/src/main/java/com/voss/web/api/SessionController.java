// 현재 세션 요약 및 투입 예정 수량을 REST로 제공한다.
// 입력: SortState.session_id, sort_log, session_plan. 출력: 요약 JSON.
// 근거: docs/interfaces/web_api.md (#68, #78).
package com.voss.web.api;

import com.voss.web.db.HistoryRepository;
import com.voss.web.db.PlanRepository;
import com.voss.web.service.CurrentSession;
import com.voss.web.service.TimeProvider;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {
    private final CurrentSession sessions;
    private final PlanRepository plans;
    private final HistoryRepository history;
    private final TimeProvider clock;

    /** 현재 세션 ID 및 공식 DB 통계를 연결한다. */
    public SessionController(CurrentSession sessions, PlanRepository plans,
                             HistoryRepository history, TimeProvider clock) {
        this.sessions = sessions;
        this.plans = plans;
        this.history = history;
        this.clock = clock;
    }

    /** 현재 세션 요약을 반환하며 첫 start 이전에는 통계를 0으로 표시한다. */
    @GetMapping("/api/sessions/current")
    public Map<String,Object> current() {
        String session = sessions.currentId();
        int planned = plans.planned(session);
        Map<String,Object> response = new LinkedHashMap<>();
        response.put("ok", true);
        response.put("session_id", session);
        response.put("planned", planned);
        if (session.isEmpty()) {
            for (String field : List.of("placed", "held", "failed", "passed")) { response.put(field, 0); }
            response.put("remaining", 0);
            response.put("by_zone", Map.of("A", 0, "B", 0, "C", 0, "RECHECK", 0, "HOLD", 0));
        } else {
            response.put("placed", history.outcome(session, "PLACED"));
            response.put("held", history.outcome(session, "HELD"));
            response.put("failed", history.outcome(session, "FAILED"));
            response.put("passed", history.outcome(session, "PASSED"));
            response.put("remaining", Math.max(planned - history.completed(session), 0));
            response.put("by_zone", history.zones(session));
        }
        response.put("as_of", clock.now());
        return response;
    }

    /** 1~100 범위의 예정 수량만 session_plan에 저장한다. */
    @PutMapping("/api/sessions/current/plan")
    public Map<String,Object> updatePlan(@RequestBody Map<String,Object> request) {
        Object value = request.get("planned");
        if (!(value instanceof Integer planned) || planned < 1 || planned > 100) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_QUERY", "planned는 1~100 정수여야 합니다.");
        }
        plans.save(sessions.currentId(), (Integer) value);
        return current();
    }
}
