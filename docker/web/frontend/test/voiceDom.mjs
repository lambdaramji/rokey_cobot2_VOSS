// 설치된 Chrome의 CDP를 사용한다. 별도 브라우저 라이브러리나 웹 모의 이벤트를 쓰지 않는다.
import assert from 'node:assert/strict';
const env = process.env;
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
const pages = await (await fetch(`http://127.0.0.1:${env.VOSS_TEST_CDP}/json/list`)).json();
const ws = new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl);
await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
let sequence=0;
const pending=new Map();
ws.addEventListener('message',event=>{
 const message=JSON.parse(event.data);
 if(message.id){const p=pending.get(message.id);pending.delete(message.id);message.error?p.reject(message.error):p.resolve(message.result);}
});
function cdp(method,params={}){
 return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
}
async function evaluate(expression){
 const result=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
 return result.result.value;
}
async function waitFor(expression,timeout=10000){
 const start=Date.now();
 while(Date.now()-start<timeout){if(await evaluate(expression))return;await delay(100);}
 throw new Error(`DOM timeout: ${expression}`);
}
async function control(path,data={}){
 const response=await fetch(`http://127.0.0.1:${env.VOSS_TEST_CONTROL}/${path}`,{method:'POST',body:JSON.stringify(data)});
 assert.equal(response.status,200);return response.json();
}
const color=c=>`Boolean(document.querySelector('.voss-ws__voice-button--${c}'))`;
const publish=(phase,utterance_id,event_id=`${utterance_id}-${phase}`)=>control('event',{phase,event_id,utterance_id});
const checks=[];
async function check(name,run){await run();checks.push(name);console.log(`PASS ${name}`);}
try {
 await cdp('Page.enable');
 await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
  window.__voiceTrace=[];
  const OriginalEventSource=window.EventSource;
  window.EventSource=class extends OriginalEventSource {
   constructor(...args){super(...args);for(const type of ['open','error','voice_status','link'])this.addEventListener(type,event=>window.__voiceTrace.push({type,data:event.data,time:Date.now()}));}
  };
 `});
 await cdp('Page.navigate',{url:`http://127.0.0.1:${env.VOSS_TEST_FRONTEND}/`});
 await waitFor("document.body.innerText.includes('MQTT UP')");
 await check('초기 초록',()=>waitFor(color('green')));
 await check('ROS 호출어 → MQTT → SSE → DOM 노랑',async()=>{await publish('WAKE_DETECTED','u1');await waitFor(color('yellow'));});
 await check('전사 수락 → 초록',async()=>{await publish('COMMAND_ACCEPTED','u1');await waitFor(color('green'));});
 await check('실패 → 빨강 + 안내',async()=>{
  await publish('WAKE_DETECTED','u2');await waitFor(color('yellow'));
  await publish('RECOGNITION_FAILED','u2');await waitFor(color('red'));
  assert.ok(await evaluate("document.querySelector('.voss-ws__voice-error').textContent.includes('음성을 인식하지 못했어요')"));
 });
 await check('클릭 → 초록 + 안내 제거',async()=>{
  await evaluate("document.querySelector('.voss-ws__voice-button').click()");await waitFor(color('green'));
  assert.equal(await evaluate("document.querySelector('.voss-ws__voice-error') === null"),true);
 });
 await check('이전 발화 결과·호출어·중복 무시',async()=>{
  await publish('WAKE_DETECTED','u3');await waitFor(color('yellow'));
  await publish('COMMAND_ACCEPTED','u2','late-result');await publish('WAKE_DETECTED','u2','late-wake');
  await publish('WAKE_DETECTED','u3');await delay(400);assert.ok(await evaluate(color('yellow')));
  await publish('COMMAND_ACCEPTED','u3');await waitFor(color('green'));
 });
 await check('결과 미수신 8초 → 빨강',async()=>{
  await publish('WAKE_DETECTED','u4');await waitFor(color('yellow'));
  await delay(6500);assert.ok(await evaluate(color('yellow')));
  await waitFor(color('red'),3000);
  assert.ok(await evaluate("document.querySelector('.voss-ws__voice-error').textContent.includes('시간이 지났어요')"));
 });
 await check('새로고침 시 지난 호출어 재생 없음',async()=>{
  await publish('WAKE_DETECTED','u5');await waitFor(color('yellow'));
  await cdp('Page.reload');await waitFor("document.body.innerText.includes('MQTT UP')");
  await waitFor(color('green'));await delay(300);assert.ok(await evaluate(color('green')));
 });
 await check('SSE 연결 끊김·복원 시 이전 발화 초기화',async()=>{
  await publish('WAKE_DETECTED','sse-offline');await waitFor(color('yellow'));
  await fetch(`http://127.0.0.1:${env.VOSS_TEST_FRONTEND}/__voice_test/drop-sse`);
  await waitFor("document.querySelector('.live-pill.disconnected') !== null");await waitFor(color('green'));
  await waitFor("document.querySelector('.live-pill.connected') !== null",15000);
  await waitFor(color('green'));
 });
 await check('retained 호출어 거부',async()=>{
  await control('retained',{phase:'WAKE_DETECTED',utterance_id:'retained',event_id:'retained'});
  // 기존 구독자의 live publish와 새 MQTT 구독자의 retained delivery를 구분한다.
  await delay(300);await control('backend-restart');
  await cdp('Page.reload');
  await waitFor("document.querySelector('.live-pill.connected') !== null",20000);
  await waitFor(color('green'));await delay(1000);assert.ok(await evaluate(color('green')));
 });
 await check('브로커 끊김·재연결에 오프라인 호출어 재생 없음',async()=>{
  await publish('WAKE_DETECTED','u6');await waitFor(color('yellow'));
  await control('broker-stop');await waitFor("document.body.innerText.includes('MQTT DOWN')");await waitFor(color('green'));
  await publish('WAKE_DETECTED','offline');await delay(300);
  await control('broker-start');await waitFor("document.body.innerText.includes('MQTT UP')",20000);
  await delay(500);assert.ok(await evaluate(color('green')));
  await publish('WAKE_DETECTED','u7');await waitFor(color('yellow'));
  await publish('TIMED_OUT','u7');await waitFor(color('red'));
 });
 await check('기존 state SSE 표시 유지',async()=>{
  await control('state');await waitFor("document.querySelector('.voss-ws__status').textContent.includes('PAUSED')");
 });
 console.log(JSON.stringify({checks:checks.length,passed:checks}));
} catch(error) {
 console.error(JSON.stringify(await evaluate('({trace:window.__voiceTrace, button:document.querySelector(".voss-ws__voice-button")?.className, live:document.querySelector(".live-pill")?.textContent})')));
 throw error;
} finally {ws.close();}
