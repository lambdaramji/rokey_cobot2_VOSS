// 브라우저의 실시간 SSE 스트림을 제공한다.
// 입력: GET /api/stream. 출력: 상태·결과·링크 JSON SSE.
// 근거: docs/interfaces/web_api.md.
package com.voss.web.api;

import com.voss.web.service.LiveEvents;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class StreamController {
    private final LiveEvents events;

    /** 실시간 이벤트 서비스를 연결한다. */
    public StreamController(LiveEvents events) { this.events = events; }

    /** 연결 직후 최신 스냅샷과 링크 상태를 전송한다. */
    @GetMapping(path = "/api/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() { return events.subscribe(); }

    /** 프록시의 유휴 연결 종료를 방지하기 위해 주기적으로 코멘트를 보낸다. */
    @Scheduled(fixedDelay = 15000)
    public void heartbeat() { events.heartbeat(); }
}
