// T13 #22 최신 MQTT 상태 저장과 3초 만료 규칙을 검증한다.
// 입력: 모의 SortState 메시지와 테스트용 시계.
// 출력: JUnit 테스트 통과 또는 실패.
// 근거: docs/interfaces/mqtt.md, web_api.md.

package com.voss.web.service;

import com.voss.web.dto.SortStateMessage;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SortStateStoreTest {

    private static final Instant TEST_TIME =
            Instant.parse("2026-10-10T00:00:00Z");

    /**
     * 아직 MQTT 상태를 받지 않았다면 만료 상태로 판단한다.
     */
    @Test
    void testStateIsStaleBeforeFirstMessage() {
        SortStateStore store = new SortStateStore(
                Clock.fixed(TEST_TIME, ZoneOffset.UTC)
        );

        assertTrue(store.getLatestState().isEmpty());
        assertTrue(store.isStale());
    }

    /**
     * 수신한 상태와 수신 시각이 정확하게 저장되는지 확인한다.
     */
    @Test
    void testReceivedMessageIsStoredWithTimestamp() {
        Clock clock = Clock.fixed(TEST_TIME, ZoneOffset.UTC);
        SortStateStore store = new SortStateStore(clock);

        SortStateMessage message = createTestMessage();
        store.update(message);

        SortStateStore.StateSnapshot snapshot =
                store.getLatestState().orElseThrow();

        assertEquals(message, snapshot.message());
        assertEquals(TEST_TIME, snapshot.receivedAt());
        assertFalse(store.isStale());
    }

    /**
     * 마지막 수신에서 3초가 지나기 전에는 정상 상태를 유지한다.
     */
    @Test
    void testStateIsFreshBeforeThreeSeconds() {
        Clock clock = mock(Clock.class);

        when(clock.instant()).thenReturn(
                TEST_TIME,
                TEST_TIME.plusMillis(2999)
        );

        SortStateStore store = new SortStateStore(clock);
        store.update(createTestMessage());

        assertFalse(store.isStale());
    }

    /**
     * 마지막 수신 후 정확히 3초가 지나면 만료로 판단한다.
     * 만료되더라도 기존 데이터를 임의로 삭제하지 않는다.
     */
    @Test
    void testStateBecomesStaleAtThreeSeconds() {
        Clock clock = mock(Clock.class);

        when(clock.instant()).thenReturn(
                TEST_TIME,
                TEST_TIME.plusSeconds(3)
        );

        SortStateStore store = new SortStateStore(clock);
        store.update(createTestMessage());

        assertTrue(store.isStale());
        assertTrue(store.getLatestState().isPresent());
    }

    /**
     * 테스트에 사용할 분류 상태 메시지를 만든다.
     */
    private SortStateMessage createTestMessage() {
        return new SortStateMessage(
                "RUNNING",
                "BOX-001",
                "",
                7,
                true,
                List.of(),
                "20261010T143012-a3f9"
        );
    }
}