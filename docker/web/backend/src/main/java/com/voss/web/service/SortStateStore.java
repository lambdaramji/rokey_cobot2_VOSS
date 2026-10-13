// T13 #22 MQTT에서 받은 최신 분류 상태를 메모리에 보관한다.
// 입력: voss/state를 변환한 SortStateMessage.
// 출력: 최신 상태와 메시지 신선도 판단 결과.
// 근거: docs/interfaces/mqtt.md, web_api.md.

package com.voss.web.service;

import com.voss.web.dto.SortStateMessage;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class SortStateStore {

    private static final Duration STATE_TIMEOUT = Duration.ofSeconds(3);

    private final AtomicReference<StateSnapshot> latestState =
            new AtomicReference<>();

    private final Clock clock;

    /**
     * 실제 운영 환경에서 사용할 시스템 시계를 설정한다.
     */
    public SortStateStore() {
        this(Clock.systemUTC());
    }

    /**
     * 시험에서 시계를 지정할 수 있도록 한다.
     */
    SortStateStore(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    /**
     * 새 MQTT 상태와 수신 시각을 함께 저장한다.
     */
    public void update(SortStateMessage message) {
        Objects.requireNonNull(message, "message");

        StateSnapshot snapshot = new StateSnapshot(
                message,
                Instant.now(clock)
        );

        latestState.set(snapshot);
    }

    /**
     * 가장 최근에 수신한 상태를 반환한다.
     * 아직 메시지를 받지 않았다면 빈 Optional을 반환한다.
     */
    public Optional<StateSnapshot> getLatestState() {
        return Optional.ofNullable(latestState.get());
    }

    /**
     * 상태가 없거나 마지막 수신 후 3초 이상 지났는지 확인한다.
     */
    public boolean isStale() {
        StateSnapshot snapshot = latestState.get();

        if (snapshot == null) {
            return true;
        }

        Duration elapsed = Duration.between(
                snapshot.receivedAt(),
                Instant.now(clock)
        );

        return elapsed.compareTo(STATE_TIMEOUT) >= 0;
    }

    /**
     * 최신 MQTT 상태와 수신 시각을 함께 보관한다.
     */
    public record StateSnapshot(
            SortStateMessage message,
            Instant receivedAt
    ) {
    }
}