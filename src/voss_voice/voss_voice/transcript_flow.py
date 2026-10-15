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

from voss_voice.http_client import IntentParseError
from voss_voice.intent_logic import (
    SAY_PALLET_ORDER,
    SAY_RETRY,
    SAY_ROUTE_COUNT,
    SAY_ROUTE_DUP,
    SAY_ROUTE_RETRY,
    SAY_ROUTE_UNKNOWN,
    SayDeduper,
    ZoneMapView,
    command_acknowledgement,
    decide,
    decide_bare_dong,
    decide_destination_answer,
    decide_hold_answer,
    decide_pallet_route_answer,
    decide_palletize,
    decide_recheck_start,
    is_stop,
    stats_sentence,
    stop_decision,
)

SAY_AI_DOWN = "음성 해석 서비스에 연결할 수 없습니다. 잠시 후 다시 말씀해 주세요."
SAY_BUSY = "앞 지시를 처리하고 있습니다. 잠시 후 다시 말씀해 주세요."
SAY_COMMAND_UNCONFIRMED = "명령 접수를 확인하지 못했습니다. 관제 화면의 상태를 확인해 주세요."
PALLET_ROUTE_REPLY_WINDOW_S = 60.0
PALLET_ROUTE_PROMPTS = {
    SAY_PALLET_ORDER, SAY_ROUTE_RETRY, SAY_ROUTE_COUNT, SAY_ROUTE_DUP, SAY_ROUTE_UNKNOWN
}


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
        self._pallet_route_until = 0.0

    def handle(self, text: str, report: Callable[[str], None] | None = None) -> tuple[str, float]:
        """음성 문장 하나를 처리하고 결과 종류와 처리 시간을 반환한다."""
        text = text.strip()

        if not text:
            return "empty", 0.0

        t0 = self._clock()
        def say(message: str) -> None:
            if report is not None and message:
                report(message)
            self._say(message)

        # 발화 당시 로봇 상태와 박스 ID를 저장한다.
        state = self.state
        box_id = self.box_id

        # 1. 정지 명령은 LLM이나 잠금을 기다리지 않는다.
        if is_stop(text):
            self._pallet_route_until = 0.0
            intent = stop_decision(text).intent
            try:
                self._publish(intent)
            except CommandDeliveryError:
                say(SAY_COMMAND_UNCONFIRMED)
                return "delivery_error", 1000 * (self._clock() - t0)
            say(command_acknowledgement(intent))
            return "stop", 1000 * (self._clock() - t0)

        # 2. 다른 지시를 처리 중이면 기다리지 않고 안내한다.
        if not self._llm_lock.acquire(blocking=False):
            say(SAY_BUSY)
            return "busy", 1000 * (self._clock() - t0)

        try:
            view = self.view

            # 팔레타이징 순서를 되물은 뒤에는 동 이름 목록만으로 답할 수 있다.
            # 로봇이 ASKING 중이면 박스의 답변이 우선한다.
            d = (decide_pallet_route_answer(text, view)
                 if state != "ASKING" and t0 <= self._pallet_route_until else None)

            # 3. 등록된 동 이름만 말했는지 확인한다.
            if d is None:
                d = decide_bare_dong(text, view, state, box_id)

            # 4. "역삼으로 보내"처럼 목적지를 답했는지 확인한다.
            if d is None:
                d = decide_destination_answer(text, view, state, box_id)

            # 4-1. "송장 확인 불가"·"보류" 답은 보류로 (LLM 없이)
            if d is None:
                d = decide_hold_answer(text, state, box_id)

            # 4-2. "재확인 시작" → 보관 중인 재확인 칸 박스 처리 (LLM 없이)
            if d is None:
                d = decide_recheck_start(text)

            # 4-3. "대치, 역삼, 청담 순서로 실어줘" → 팔레타이징 (LLM 없이, 말한 순서 = 배송 순서)
            if d is None:
                d = decide_palletize(text, view)

            # 5. 단독 동 이름이 아니라면 기존 GPT-4o 경로를 사용한다.
            if d is None:
                llm = None

                try:
                    llm = self._post_intent(
                        text,
                        view.llm_allowed() if view is not None else {"dongs": [], "aliases": {}, "zones": []},
                    )
                except IntentParseError:
                    # 계약: 파싱 실패 시 명령을 실행하지 않고 되묻는다.
                    say(SAY_RETRY)
                    return "say", 1000 * (self._clock() - t0)

                if llm is None:
                    say(SAY_AI_DOWN)
                    return "say", 1000 * (self._clock() - t0)

                d = decide(
                    llm,
                    text,
                    view,
                    state,
                    box_id,
                    self.allow_update_zone_map,
                )

            # 6. 최종 판단 결과에 따라 발행하거나 답한다.
            if d.kind == "publish":
                self._pallet_route_until = 0.0
                try:
                    self._publish(d.intent)
                except CommandDeliveryError:
                    say(SAY_COMMAND_UNCONFIRMED)
                    return "delivery_error", 1000 * (self._clock() - t0)
                say(command_acknowledgement(d.intent))

            elif d.kind == "query":
                self._pallet_route_until = 0.0
                say(
                    stats_sentence(
                        d.query,
                        self._get_stats(d.query),
                    )
                )

            else:
                self._pallet_route_until = (t0 + PALLET_ROUTE_REPLY_WINDOW_S
                                            if d.say in PALLET_ROUTE_PROMPTS else 0.0)
                say(d.say)

            return d.kind, 1000 * (self._clock() - t0)

        finally:
            # 오류가 발생해도 잠금은 반드시 해제한다.
            self._llm_lock.release()

    def _say(self, text: str) -> None:
        if text and self._dedup.allow(text, self._clock()):
            self._say_raw(text)


class CommandDeliveryError(Exception):
    """명령 API가 접수를 확인하지 못했다."""
