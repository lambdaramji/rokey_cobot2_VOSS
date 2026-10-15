import test from 'node:test';
import assert from 'node:assert/strict';
import { INITIAL_INDICATOR, reduceVoiceIndicator as reduce, parseVoiceSignal, VOICE_COMMAND_TIMEOUT_MS, VOICE_FAILURE_DISPLAY_MS } from '../src/lib/voiceIndicator.ts';
const event = (phase, utterance_id='u1', event_id=`${utterance_id}-${phase}`) => ({ type:'VOICE_EVENT', signal:{phase, utterance_id, event_id} });
const wake = () => reduce(INITIAL_INDICATOR, event('WAKE_DETECTED'));
test('호출어 수신 → 노랑',()=>assert.equal(wake().color,'yellow'));
test('전사 수락 → 초록',()=>assert.equal(reduce(wake(),event('COMMAND_ACCEPTED')).color,'green'));
test('실패 → 빨강 및 인식 실패 안내 상태',()=>assert.deepEqual([reduce(wake(),event('RECOGNITION_FAILED')).color,reduce(wake(),event('RECOGNITION_FAILED')).failure],['red','recognition']));
test('시간 초과 → 빨강 및 시간 초과 안내 상태',()=>{
 assert.equal(VOICE_COMMAND_TIMEOUT_MS,13000);
 assert.equal(reduce(wake(),{type:'UI_TIMEOUT',utteranceId:'u1'}).failure,'timeout');
 assert.equal(reduce(wake(),event('TIMED_OUT')).color,'red');
});
test('빨강은 3초 뒤 초록으로 복귀하고 지난 발화 이벤트를 무시',()=>{
 assert.equal(VOICE_FAILURE_DISPLAY_MS,3000);
 let state=reduce(wake(),event('RECOGNITION_FAILED'));
 state=reduce(state,{type:'UI_RECOVER',utteranceId:'u1'});
 assert.equal(state.color,'green'); assert.equal(state.failure,null);
 assert.equal(reduce(state,event('WAKE_DETECTED','u1','retry-wake')).color,'green');
 const next=reduce(state,event('WAKE_DETECTED','u2'));
 assert.strictEqual(reduce(next,{type:'UI_RECOVER',utteranceId:'u1'}),next);
});
test('아이콘 초기화 뒤 늦은 결과·재호출어는 무시',()=>{
 let state=reduce(wake(),{type:'RESET'});
 state=reduce(state,event('RECOGNITION_FAILED'));
 state=reduce(state,event('WAKE_DETECTED','u1','retry-wake'));
 assert.equal(state.color,'green'); assert.equal(state.failure,null);
});
test('새 발화 뒤 이전 발화 결과와 호출어는 무시',()=>{
 let state=reduce(wake(),event('WAKE_DETECTED','u2'));
 for(const phase of ['COMMAND_ACCEPTED','RECOGNITION_FAILED','WAKE_DETECTED']) state=reduce(state,event(phase,'u1',`late-${phase}`));
 assert.equal(state.activeUtteranceId,'u2'); assert.equal(state.color,'yellow');
});
test('다른 이벤트 사이에 온 중복도 무시',()=>{
 const first=wake(); const next=reduce(first,event('WAKE_DETECTED','u2'));
 assert.strictEqual(reduce(next,event('WAKE_DETECTED')),next);
});
test('완료된 발화를 재개하지 않음',()=>{
 const done=reduce(wake(),event('COMMAND_ACCEPTED'));
 assert.equal(reduce(done,event('WAKE_DETECTED','u1','new-id')).color,'green');
});
test('연결 초기화 뒤 새 호출어만 수락',()=>{
 const reset=reduce(wake(),{type:'RESET'});
 assert.equal(reduce(reset,event('COMMAND_ACCEPTED')).color,'green');
 assert.equal(reduce(reset,event('WAKE_DETECTED','u2')).color,'yellow');
});
test('호출어 없는 결과 및 이전 타이머로 노랑을 만들지 않음',()=>{
 assert.equal(reduce(INITIAL_INDICATOR,event('COMMAND_ACCEPTED')).color,'green');
 const state=reduce(wake(),event('WAKE_DETECTED','u2'));
 assert.strictEqual(reduce(state,{type:'UI_TIMEOUT',utteranceId:'u1'}),state);
});
test('잘못된 JSON 필드는 거부',()=>{
 for(const value of [null,[],{}, {phase:'NEW',event_id:'e',utterance_id:'u'}, {phase:'WAKE_DETECTED',event_id:' ',utterance_id:'u'}, {phase:'WAKE_DETECTED',event_id:'x'.repeat(129),utterance_id:'u'}]) assert.equal(parseVoiceSignal(value),null);
});
test('ID 이력 크기 제한',()=>{
 let state=INITIAL_INDICATOR;
 for(let i=0;i<300;i++) state=reduce(state,event('WAKE_DETECTED',`u${i}`));
 assert.equal(state.seenEventIds.length,128);assert.equal(state.seenUtteranceIds.length,128);
});
