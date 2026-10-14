// T13 #22 MQTT voss/state 메시지의 데이터를 표현한다.
// 입력: hmi_bridge가 발행한 SortState JSON.
// 출력: Spring Boot에서 사용할 상태 데이터.
// 근거: docs/interfaces/mqtt.md, voss_msgs.md.

package com.voss.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * MQTT voss/state의 필드와 타입을 표현한다.
 * 메시지 수신과 전송은 별도 서비스에서 처리한다.
 */
public record SortStateMessage(
        String state,
        @JsonProperty("box_id") String boxId,
        @JsonProperty("pending_question") String pendingQuestion,
        @JsonProperty("track_id") int trackId,
        boolean ready,
        @JsonProperty("not_ready") List<String> notReady,
        @JsonProperty("session_id") String sessionId
) {
}