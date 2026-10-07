"""transcript 한 건을 처리하는 흐름 (ROS 의존 없음, pytest 대상).

안전 규칙(intent_json.md): stop 은 **잠금 밖에서** 바로 발행한다. 앞 발화가 LLM(/ai/intent, 최대 3 s)이나
/api/stats(최대 2 s)를 기다리는 중이어도 "멈춰" 는 줄을 서지 않는다. LLM·REST 는 잠금으로 한 번에 하나씩.
잠금을 **기다리지 않는다**: 처리 중에 온 발화는 "처리 중" 으로 답하고 버린다. 기다리게 하면 그 콜백이
executor 스레드를 붙잡아, 쌓인 발화가 스레드 수(4)를 채우는 순간 "멈춰" 를 받을 스레드가 없어진다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from voss_voice.intent_logic import (
    SayDeduper,
    ZoneMapView,
    decide,
    is_stop,
    stats_sentence,
    stop_decision,
)

SAY_AI_DOWN = "음성 해석 서비스에 연결할 수 없습니다. 잠시 후 다시 말씀해 주세요."
SAY_BUSY = "앞 지시를 처리하고 있습니다. 잠시 후 다시 말씀해 주세요."


class TranscriptFlow:
    def __init__(
        self,
        post_intent: Callable[[str, dict], dict | None],
        get_stats: Callable[[dict], dict | None],
        publish: Callable[[dict], None],
        say: Callable[[str], None],
        allow_update_zone_map: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._post_intent = post_intent
        self._get_stats = get_stats
        self._publish = publish
        self._say_raw = say
        self.allow_update_zone_map = allow_update_zone_map
        self._clock = clock
        self._llm_lock = threading.Lock()  # LLM·REST 는 한 번에 하나, stop 은 잠금 밖
        self._dedup = SayDeduper()
        self.view: ZoneMapView | None = None
        self.state = ""
        self.box_id = ""

    def handle(self, text: str) -> tuple[str, float]:
        """(처리 결과 종류, 걸린 ms). 종류: stop | publish | query | say | busy | empty."""
        text = text.strip()
        if not text:
            return "empty", 0.0
        t0 = self._clock()
        state, box_id = self.state, self.box_id  # 발화 시점의 질문 상태 (늦은 답 방지)

        if is_stop(text):  # 안전: 잠금·LLM·zone_map 과 무관하게 즉시
            self._publish(stop_decision(text).intent)
            return "stop", 1000 * (self._clock() - t0)

        if not self._llm_lock.acquire(blocking=False):  # 기다리지 않는다 (위 모듈 설명)
            self._say(SAY_BUSY)
            return "busy", 1000 * (self._clock() - t0)
        try:
            view = self.view
            llm = None
            if view is not None:
                llm = self._post_intent(text, view.llm_allowed())
                if llm is None:  # FastAPI 꺼짐·timeout·오류 — 되묻기와 구분해서 알린다
                    self._say(SAY_AI_DOWN)
                    return "say", 1000 * (self._clock() - t0)
            d = decide(llm, text, view, state, box_id, self.allow_update_zone_map)
            if d.kind == "publish":
                self._publish(d.intent)
            elif d.kind == "query":
                self._say(stats_sentence(d.query, self._get_stats(d.query)))
            else:
                self._say(d.say)
            return d.kind, 1000 * (self._clock() - t0)
        finally:
            self._llm_lock.release()

    def _say(self, text: str) -> None:
        if text and self._dedup.allow(text, self._clock()):
            self._say_raw(text)
