/**
 * 마이크 표시등의 화면 상태만 계산한다 (로봇/마이크 제어 없음).
 * 입력: 신규 음성 상태 이벤트, 화면 시간 초과, 아이콘 초기화.
 * 출력: 대기/듣는 중/실패 화면 상태.
 * 관련: docs/interfaces/voice_status.md (현재 인터페이스 제안).
 */
export const VOICE_COMMAND_TIMEOUT_MS = 8000; // UI 제안값: 팀 합의 필요

export type VoicePhase = 'WAKE_DETECTED' | 'COMMAND_ACCEPTED' | 'RECOGNITION_FAILED' | 'TIMED_OUT';
export type IndicatorColor = 'green' | 'yellow' | 'red';
export type VoiceFailure = 'recognition' | 'timeout' | null;

export interface VoiceSignal {
  phase: VoicePhase;
  event_id: string;
  utterance_id: string;
}

export interface IndicatorState {
  color: IndicatorColor;
  activeUtteranceId: string;
  ignoredUtteranceId: string;
  lastEventId: string;
  failure: VoiceFailure;
  seenEventIds: string[];
  seenUtteranceIds: string[];
}

export type IndicatorAction =
  | { type: 'VOICE_EVENT'; signal: VoiceSignal }
  | { type: 'UI_TIMEOUT'; utteranceId: string }
  | { type: 'RESET' };

export const INITIAL_INDICATOR: IndicatorState = {
  color: 'green',
  activeUtteranceId: '',
  ignoredUtteranceId: '',
  lastEventId: '',
  failure: null,
  seenEventIds: [],
  seenUtteranceIds: [],
};

const HISTORY_LIMIT = 128;

/** 최근 ID만 기억해 메모리 사용을 제한한다. */
function remember(ids: string[], id: string): string[] {
  return [...ids, id].slice(-HISTORY_LIMIT);
}

/** 호출어를 실제로 받은 발화만 처리하며 종료된 발화는 다시 열지 않는다. */
export function reduceVoiceIndicator(state: IndicatorState, action: IndicatorAction): IndicatorState {
  if (action.type === 'RESET') {
    return { ...state, color: 'green', activeUtteranceId: '', failure: null,
      ignoredUtteranceId: state.activeUtteranceId || state.ignoredUtteranceId };
  }
  if (action.type === 'UI_TIMEOUT') {
    if (state.color !== 'yellow' || state.activeUtteranceId !== action.utteranceId) return state;
    return { ...state, color: 'red', failure: 'timeout' };
  }
  const signal = parseVoiceSignal(action.signal);
  if (!signal || state.seenEventIds.includes(signal.event_id)) return state;
  const next = { ...state, lastEventId: signal.event_id,
    seenEventIds: remember(state.seenEventIds, signal.event_id) };
  if (signal.phase === 'WAKE_DETECTED') {
    if (state.seenUtteranceIds.includes(signal.utterance_id)) return next;
    return { ...next, color: 'yellow', activeUtteranceId: signal.utterance_id,
      failure: null, ignoredUtteranceId: '',
      seenUtteranceIds: remember(state.seenUtteranceIds, signal.utterance_id) };
  }
  if (signal.utterance_id !== state.activeUtteranceId || state.color !== 'yellow') return next;
  if (signal.phase === 'COMMAND_ACCEPTED') {
    return { ...next, color: 'green', activeUtteranceId: '', failure: null };
  }
  return { ...next, color: 'red', failure: signal.phase === 'TIMED_OUT' ? 'timeout' : 'recognition' };
}

/** SSE 입력이 실제 제안 계약과 맞는지 확인한다. */
export function parseVoiceSignal(value: unknown): VoiceSignal | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const data = value as Record<string, unknown>;
  const phases: string[] = ['WAKE_DETECTED', 'COMMAND_ACCEPTED', 'RECOGNITION_FAILED', 'TIMED_OUT'];
  if (typeof data.phase !== 'string' || !phases.includes(data.phase)) {
    return null;
  }
  if (typeof data.event_id !== 'string' || typeof data.utterance_id !== 'string') {
    return null;
  }
  if ([data.event_id, data.utterance_id].some(id => !id.trim() || id !== id.trim() || id.length > 128)) {
    return null;
  }
  return { phase: data.phase as VoicePhase, event_id: data.event_id, utterance_id: data.utterance_id };
}
