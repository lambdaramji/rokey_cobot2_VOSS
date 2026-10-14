// 현재 분류 세션을 MQTT SortState.session_id로 판정한다.
// 입력: 최신 상태 저장소. 출력: 계약상 현재 세션 ID.
// 근거: docs/interfaces/web_api.md, #78.
package com.voss.web.service;

import com.voss.web.api.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class CurrentSession {
    private final SortStateStore states;

    /** 상태 저장소를 연결한다. */
    public CurrentSession(SortStateStore states) { this.states = states; }

    /** 처음 시작하기 전에는 빈 문자열을 반환한다. */
    public String currentId() {
        return states.getLatestState()
                .map(snapshot -> snapshot.message().sessionId())
                .orElse("");
    }

    /** 명시적 세션은 허용하고 생략 시 현재 세션을 요구한다. */
    public String resolve(String requested) {
        if (requested != null && !requested.isBlank()) { return requested; }
        String current = currentId();
        if (current.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "NO_SESSION", "현재 세션이 없습니다.");
        }
        return current;
    }
}
