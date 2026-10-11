// 웹 API 응답의 시각을 KST ISO-8601 오프셋으로 만든다.
// 입력: 시스템 시각. 출력: +09:00 표기 시각.
// 근거: docs/interfaces/web_api.md.
package com.voss.web.service;

import java.time.ZonedDateTime;
import java.time.ZoneId;
import org.springframework.stereotype.Component;

@Component
public class TimeProvider {
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    /** 조회가 완료된 현재 시각을 돌려준다. */
    public String now() { return ZonedDateTime.now(SEOUL).toOffsetDateTime().toString(); }
}
