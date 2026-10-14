// T13 #22 React 웹 HMI의 관제 화면과 HMI 명령 입력.
// 입력: Spring Boot SSE 상태 및 REST 이력/명령.
// 출력: 실시간 상태·분류·로봇·보류·이력·현장 제어 화면.
// 근거: docs/interfaces/web_api.md, mqtt.md, ADR-0006. Sprint 2 S2-T08 팔레트 패널은 PalletPanel.tsx.
import { flushSync } from 'react-dom';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getResults, getSummary, issueCommand, putPlan, RequestFailure } from './api';
import type { CommandArgs } from './api';
import PalletPanel from './PalletPanel';
import { emptyPallet, GENERAL_RESET_ZONES, parsePalletState } from './pallet';
import type { CommandType, LinkStatus, PalletState, RobotState, SortResult, SortState, Summary, ZoneMap } from './types';
import { VossSortingWorkspace } from './components/VossSortingWorkspace';
import { parseBoxMotion, parseBoxTrack, parseRobotJoints, parseRobotPose, JOINT_STALE_MS, POSE_STALE_MS, TRACK_STALE_MS } from './lib/workspacePosition';
import type { BoxMotionSample, BoxTrackSample, RobotJointSample, RobotPoseSample } from './lib/workspacePosition';
import { UsbCameraPanel } from './components/UsbCameraPanel';
import { parseVoiceSignal } from './lib/voiceIndicator';
import type { VoiceSignal } from './lib/voiceIndicator';
type DisplayState = 'UNKNOWN'|string;
const ZONES = ['A','B','C','RECHECK','HOLD'];
const RESET_ZONES = GENERAL_RESET_ZONES;  // PALLET 은 팔레트 패널의 '트럭 짐칸 비움 확인'으로만
const LOCAL_HOSTS = new Set(['localhost','127.0.0.1','::1']);
const INITIAL_ERROR = '서버에서 데이터를 기다리는 중입니다.';
const TIMEOUT_MS = 3000;
/** ISO 시각을 한국어 시각으로 보여주되 없는 값은 표시하지 않는다. */
function displayTime(value:unknown):string {
  if (typeof value !== 'string' || !value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleTimeString('ko-KR',{hour12:false});
}
/** 네트워크/계약 오류 코드를 원문 그대로 사용자에게 보여 준다. */
function errorText(error:unknown):string {
  if (error instanceof RequestFailure) return `${error.code} — ${error.message}`;
  return 'UNKNOWN_ERROR — 요청 처리 중 오류가 발생했습니다.';
}
export default function App() {
  const [state,setState] = useState<SortState|null>(null);
  const [stateReceivedAt,setStateReceivedAt] = useState<number|null>(null);
  const [zoneMap,setZoneMap] = useState<ZoneMap|null>(null);
  const [robot,setRobot] = useState<RobotState|null>(null);
  const [robotReceivedAt,setRobotReceivedAt] = useState<number|null>(null);
  const [boxTracks,setBoxTracks] = useState<Record<number,BoxTrackSample>>({});
  const [robotPose,setRobotPose] = useState<RobotPoseSample|null>(null);
  const [robotJoints,setRobotJoints] = useState<RobotJointSample|null>(null);
  const [boxMotion,setBoxMotion] = useState<BoxMotionSample|null>(null);
  const completedTracks = useRef<Map<number,number>>(new Map());
  const [latestResult,setLatestResult] = useState<SortResult|null>(null);
  const [pallet,setPallet] = useState<PalletState>(emptyPallet);
  const [logStatus,setLogStatus] = useState('UNKNOWN');
  const [mqtt,setMqtt] = useState<LinkStatus>('DOWN');
  const [sseConnected,setSseConnected] = useState(false);
  const [summary,setSummary] = useState<Summary|null>(null);
  const [items,setItems] = useState<SortResult[]>([]);
  const [held,setHeld] = useState<SortResult[]>([]);
  const [activePage,setActivePage] = useState<'dashboard'|'cameras'>('dashboard');
  const [notice,setNotice] = useState(INITIAL_ERROR);
  const [error,setError] = useState('');
  const [plannedText,setPlannedText] = useState('10');
  const editingPlan = useRef(false);
  const [selectedDong,setSelectedDong] = useState('');
  const [selectedZone,setSelectedZone] = useState('A');
  const [answerDong,setAnswerDong] = useState('');
  const [answerHold,setAnswerHold] = useState(false);
  const [busy,setBusy] = useState(false);
  const [clock,setClock] = useState(Date.now());
  const [voiceSignal,setVoiceSignal] = useState<VoiceSignal|null>(null);
  const isLocal = LOCAL_HOSTS.has(location.hostname);
  const displayState:DisplayState = sseConnected && stateReceivedAt !== null && clock-stateReceivedAt < TIMEOUT_MS ? (state?.state ?? 'UNKNOWN') : 'UNKNOWN';
  const robotFresh = sseConnected && mqtt === 'UP' && robotReceivedAt !== null && clock-robotReceivedAt < TIMEOUT_MS;
  const displayRobot = robotFresh ? robot : null;
  const displayLogStatus = sseConnected ? logStatus : 'UNKNOWN';
  const displayMqtt = sseConnected ? mqtt : 'DOWN';
  const sessionId = state?.session_id ?? summary?.session_id ?? '';
  const dongs = useMemo(()=>zoneMap?.entries.map(entry=>entry.dong) ?? [],[zoneMap]);
  const controlEnabled = isLocal && mqtt === 'UP' && !busy;
  // stop은 busy·연결 표시와 무관하게 언제든 시도한다 (web_api.md).

  /** 공식 통계/이력은 항상 REST DB에서 다시 읽으며 메모리 MQTT 수치로 대체하지 않는다. */
  const refresh = useCallback(async () => {
    try {
      const latestSummary = await getSummary();
      setSummary(latestSummary);
      if (!editingPlan.current) setPlannedText(String(latestSummary.planned));
      if (!latestSummary.session_id) {
        setItems([]);
        setHeld([]);
      } else {
        const [allRows,heldRows] = await Promise.all([
          getResults(latestSummary.session_id),
          getResults(latestSummary.session_id,'HELD'),
        ]);
        setItems(allRows.items);
        setHeld(heldRows.items);
      }
      setError('');
    } catch (failure) {
      setError(errorText(failure));
      setSummary(null);
      setItems([]);
      setHeld([]);
    }
  },[]);
  /** SSE 수신 시 변경사항을 원본 계약 필드 그대로 갱신한다. */
  useEffect(()=>{
    const stream = new EventSource('/api/stream');
    let mqttUp = false;
    let streamUp = false;
    stream.onopen=()=>{ streamUp = true; setSseConnected(true); };
    stream.onerror=()=>{
      streamUp = false;
      mqttUp = false;
      setSseConnected(false);
      setMqtt('DOWN');
      setLogStatus('UNKNOWN');
      setRobotReceivedAt(null);
      setStateReceivedAt(null);
      setVoiceSignal(null);
    };
    stream.addEventListener('state',(event)=>{
      const data = JSON.parse((event as MessageEvent).data) as SortState;
      setState(data);
      setStateReceivedAt(Date.now());
    });
    stream.addEventListener('zone_map',(event)=>setZoneMap(JSON.parse((event as MessageEvent).data) as ZoneMap));
    stream.addEventListener('robot',(event)=>{
      setRobot(JSON.parse((event as MessageEvent).data) as RobotState);
      setRobotReceivedAt(Date.now());
    });
    stream.addEventListener('box_track',(event)=>{
      try {
        const sample=parseBoxTrack(JSON.parse((event as MessageEvent).data));
        if (!sample) return;
        if ((completedTracks.current.get(sample.track_id) ?? 0) > sample.receivedAt) return;
        setBoxTracks(current=>{
          const next:Record<number,BoxTrackSample>={};
          for (const track of Object.values(current)) {
            if (sample.receivedAt-track.receivedAt<TRACK_STALE_MS) next[track.track_id]=track;
          }
          if (sample.position_valid) next[sample.track_id]=sample;
          else delete next[sample.track_id];
          return next;
        });
      } catch (failure) {console.error('[VOSS HMI] box_track 파싱 실패',failure);}
    });
    stream.addEventListener('robot_pose',(event)=>{
      try {
        const sample=parseRobotPose(JSON.parse((event as MessageEvent).data));
        if (sample) setRobotPose(sample);
      } catch (failure) {console.error('[VOSS HMI] robot_pose 파싱 실패',failure);}
    });
    stream.addEventListener('robot_joints',(event)=>{
      try {
        const sample=parseRobotJoints(JSON.parse((event as MessageEvent).data));
        if (sample) setRobotJoints(sample);
      } catch (failure) {console.error('[VOSS HMI] robot_joints 파싱 실패',failure);}
    });
    stream.addEventListener('box_motion',(event)=>{
      try {
        const sample=parseBoxMotion(JSON.parse((event as MessageEvent).data));
        if (!sample) return;
        setBoxMotion(current=>{
          if (sample.phase==='RELEASED' && (!current || current.phase!=='GRASPED' ||
              current.session_id!==sample.session_id || current.box_id!==sample.box_id ||
              current.track_id!==sample.track_id)) return current;
          return sample;
        });
        if (sample.phase==='RELEASED') {
          completedTracks.current.set(sample.track_id,Date.now()+TRACK_STALE_MS);
          setBoxTracks(current=>{
            const next={...current};
            delete next[sample.track_id];
            return next;
          });
        }
      } catch (failure) {console.error('[VOSS HMI] box_motion 파싱 실패',failure);}
    });
    stream.addEventListener('result',(event)=>{
      const result=JSON.parse((event as MessageEvent).data) as SortResult;
      setLatestResult(result);
      setBoxMotion(current=>current && current.box_id===result.box_id && current.session_id===result.session_id ? null : current);
      if (typeof result.track_id==='number' && result.track_id>=0) {
        for (const [id,until] of completedTracks.current) {
          if (until<=Date.now()) completedTracks.current.delete(id);
        }
        completedTracks.current.set(result.track_id,Date.now()+TRACK_STALE_MS);
        setBoxTracks(current=>{
          const next={...current};
          delete next[result.track_id as number];
          return next;
        });
      }
      void refresh();
    });
    stream.addEventListener('pallet_state',(event)=>{
      // 계약에 어긋나면 이전 배치도를 유지한다 (web_api.md pallet_state).
      const parsed = parsePalletState(JSON.parse((event as MessageEvent).data));
      if (parsed) setPallet(parsed);
    });
    stream.addEventListener('log_status',(event)=>setLogStatus(JSON.parse((event as MessageEvent).data).status ?? 'UNKNOWN'));
    stream.addEventListener('link',(event)=>{
      mqttUp = JSON.parse((event as MessageEvent).data).mqtt === 'UP';
      setMqtt(mqttUp ? 'UP':'DOWN');
      if (!mqttUp) setVoiceSignal(null);
    });
    // 인터페이스 제안: Spring이 voice_status 이벤트를 보내기 전에는 표시등은 초록으로 유지된다.
    stream.addEventListener('voice_status',(event)=>{
      try {
        const signal=parseVoiceSignal(JSON.parse((event as MessageEvent).data));
        if (signal && mqttUp && streamUp) flushSync(() => setVoiceSignal(signal));
      } catch (failure) {
        console.error('[VOSS HMI] voice_status 파싱 실패',failure);
      }
    });
    stream.addEventListener('command_ack',(event)=>{
      const ack = JSON.parse((event as MessageEvent).data) as {command_id?:string;ok?:boolean;message?:string};
      setNotice(`명령 접수 확인: ${ack.ok ? '성공':'거부'} · ${ack.message ?? ack.command_id ?? '응답 없음'} (동작 완료와 별개)`);
      void refresh();
    });
    return ()=>stream.close();
  },[refresh]);
  /** 수신 지연 3초와 공식 DB 변화는 각기 다른 주기로 갱신한다. */
  useEffect(()=>{
    void refresh();
    const polling = window.setInterval(()=>void refresh(),5000);
    const ticking = window.setInterval(()=>setClock(Date.now()),250);
    return ()=>{window.clearInterval(polling);window.clearInterval(ticking);};
  },[refresh]);
  /** 안전 제한을 서버에서도 검사하며 202를 작업 완료로 표시하지 않는다. */
  async function command(type:CommandType,args:CommandArgs={}) {
    setBusy(true);setNotice('명령 전달을 요청하는 중입니다.');
    try {
      const accepted=await issueCommand(type,args);
      setNotice(`${type} · MQTT 전달 요청 수락(202) · ${accepted.command_id.slice(0,8)}… / 실제 접수·완료는 별도 확인`);
    } catch(failure) {setNotice(errorText(failure));}
    finally {setBusy(false);}
  }
  function stepPlan(delta: -1 | 1) {
    const current=Number(plannedText);
    const base=Number.isInteger(current)&&current>=1&&current<=100 ? current : summary?.planned ?? 10;
    setPlannedText(String(Math.max(1,Math.min(100,base+delta))));
    editingPlan.current=true;
  }
  /** UI에서 투입 수량 범위를 확인한 뒤 서버에 전달한다. */
  async function savePlan() {
    const parsed=Number(plannedText);
    if (!Number.isInteger(parsed)||parsed<1||parsed>100) {setNotice('planned는 1~100 정수여야 합니다.');return;}
    setBusy(true);
    try {const next=await putPlan(parsed);setSummary(next);editingPlan.current=false;setNotice(`투입 예정 수량을 ${parsed}개로 저장했습니다.`);}
    catch(failure) {setNotice(errorText(failure));}
    finally {setBusy(false);}
  }
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-symbol">V</div><div><strong>VOSS</strong><small>C-3 SORTING SYSTEM</small></div></div>
      <nav className="navigation" aria-label="주 메뉴"><button type="button" className={activePage==='dashboard'?'nav-on':''} aria-current={activePage==='dashboard'?'page':undefined} onClick={()=>{setVoiceSignal(null);setActivePage('dashboard');}}>▣   관제 대시보드</button><button type="button" className={activePage==='cameras'?'nav-on':''} aria-current={activePage==='cameras'?'page':undefined} onClick={()=>{setVoiceSignal(null);setActivePage('cameras');}}>▣   카메라</button></nav>
      <div className="sidebar-bottom"><span className="eyebrow">SYSTEM STATUS</span><p><span className={`status-led ${displayMqtt==='UP'?'is-up':''}`}/> MQTT {displayMqtt}</p><p><span className={`status-led ${sseConnected?'is-up':''}`}/> 실시간 SSE {sseConnected?'연결':'끊김'}</p><p><span className={`status-led ${displayLogStatus==='OK'?'is-up':''}`}/> DB Logger {displayLogStatus}</p><div className="muted tiny">공식 기록: PostgreSQL sort_log</div></div>
    </aside>
    <main className="workspace">
      <header className="top-bar"><div><div className="eyebrow">OPERATION CENTER / LIVE MONITORING</div><h1>{activePage==='cameras'?'카메라 모니터링':'물류 분류 관제'}</h1><p className="subhead">{activePage==='cameras'?'현장 카메라 영상을 확인하세요.':'로봇 동작, 박스 판독과 세션 기록을 한눈에 확인하세요.'}</p></div><div className="header-end"><span className="clock-label">{new Date(clock).toLocaleString('ko-KR')}</span><span className={`live-pill ${sseConnected?'connected':'disconnected'}`}>{sseConnected?'● LIVE':'● OFFLINE'}</span></div></header>
      {activePage==='cameras' ? <div className="camera-page"><UsbCameraPanel /></div> : <>
      <div className="monitoring-grid">
      {/* 읽기 전용 2D 작업공간: 기존 App의 SSE/REST 상태 재사용. */}
      <VossSortingWorkspace
        state={state}
        robot={robot}
        boxTracks={sseConnected && mqtt==='UP' ? Object.values(boxTracks).filter(track=>clock-track.receivedAt<TRACK_STALE_MS) : []}
        robotPose={robotPose}
        robotJoints={robotJoints}
        boxMotion={boxMotion}
        isPoseFresh={robotPose!==null && clock-robotPose.receivedAt<POSE_STALE_MS && sseConnected && mqtt==='UP'}
        isJointsFresh={robotJoints!==null && clock-robotJoints.receivedAt<JOINT_STALE_MS && sseConnected && mqtt==='UP'}
        lastResult={state?.session_id && latestResult?.session_id === state.session_id ? latestResult : null}
        zoneCounts={displayState !== 'UNKNOWN' && state?.session_id && summary?.session_id === state.session_id ? summary.by_zone : null}
        isStateFresh={displayState !== 'UNKNOWN' && sseConnected && mqtt === 'UP'}
        isRobotFresh={robotReceivedAt !== null && clock - robotReceivedAt < TIMEOUT_MS && sseConnected && mqtt === 'UP'}
        voiceSignal={voiceSignal}
        voiceConnected={sseConnected && mqtt==='UP'}
      />
      <section className="summary-grid">
        <section className="panel robot-status-panel"><div className="section-heading"><div><span className="eyebrow">ROBOT / TELEMETRY</span><h2>로봇 및 장비 상태</h2></div><span className={`chip ${displayRobot?.connected&&displayMqtt==='UP'?'':'warning'}`}>{displayRobot?.connected&&displayMqtt==='UP'?'CONNECTED':'NOT CONFIRMED'}</span></div><div className="operation-status"><span className="metric-info">운전 상태 <strong>{displayState}</strong> · {displayState==='UNKNOWN'?'3초 이상 상태 메시지 없음':`박스 ${state?.box_id || '대기'}`}</span></div><div className="robot-visual"><div className="robot-icon">◈</div><div><span className="eyebrow">ROBOT GATEWAY</span><strong>{displayRobot?.state??'UNKNOWN'}</strong><small>{displayRobot?.action??'상태 수신 대기'}</small></div></div><div className="key-values"><div><span>그리퍼 너비</span><strong>{typeof displayRobot?.gripper_width_mm==='number'?`${displayRobot.gripper_width_mm} mm`:'—'}</strong></div><div><span>오류 코드</span><strong>{displayRobot?.error_code||'—'}</strong></div><div><span>준비 여부</span><strong>{displayState==='UNKNOWN'?'UNKNOWN':state?.ready?'READY':`NOT READY (${state?.not_ready?.join(', ')||'원인 없음'})`}</strong></div><div><span>현재 트랙</span><strong>{displayState==='UNKNOWN'?'—':state?.track_id??'—'}</strong></div></div></section>
        <Metric label="완료된 적재" value={summary?String(summary.placed):'—'} suffix="건" info="PLACED · 공식 DB" tone="teal"/>
        <Metric label="보류 / 실패" value={summary?`${summary.held} / ${summary.failed}`:'—'} suffix="건" info="HELD / FAILED" tone="amber"/>
        <Metric label="남은 작업" value={summary?String(summary.remaining):'—'} suffix="건" info="PASSED 제외 · 공식 DB"/>
      </section>
      </div>
      <div className="main-grid">
        <div className="stack">
          <section className="panel"><div className="section-heading"><div><span className="eyebrow">01 / CONTROL</span><h2>운전 및 분류 제어</h2></div><span className="micro-note">시작·이동 명령은 공용 PC 로컬에서만</span></div>
            <div className="button-cluster"><button className="action primary" disabled={!controlEnabled} onClick={()=>void command('start')}>▶   시작</button><button className="action danger" onClick={()=>void command('stop')}>■   정지</button><button className="action subdued" disabled={!controlEnabled} onClick={()=>void command('resume')}>↻   재개</button></div>
            <div className="form-grid"><div className="field"><label htmlFor="planned">투입 예정 수량</label><div className="inline-input"><div className="plan-stepper"><button type="button" aria-label="투입 예정 수량 1개 줄이기" disabled={busy||Number(plannedText)<=1} onClick={()=>stepPlan(-1)}>−</button><input id="planned" type="number" min="1" max="100" step="1" value={plannedText} onChange={event=>{setPlannedText(event.target.value);editingPlan.current=true;}}/><button type="button" aria-label="투입 예정 수량 1개 늘리기" disabled={busy||Number(plannedText)>=100} onClick={()=>stepPlan(1)}>+</button></div><button disabled={busy} onClick={()=>void savePlan()}>저장</button></div></div><div className="field"><label htmlFor="priority">동별 우선 분류</label><div className="inline-input"><select id="priority" value={selectedDong} onChange={event=>setSelectedDong(event.target.value)}><option value="">동 선택</option>{dongs.map(dong=><option key={dong} value={dong}>{dong}</option>)}</select><button disabled={!controlEnabled||!selectedDong} onClick={()=>void command('priority',{dong:selectedDong})}>적용</button></div></div></div>
            <div className="form-grid"><div className="field"><label htmlFor="answer">작업자 답변 · 질문 박스 {state?.box_id||'없음'}</label><div className="inline-input"><select id="answer" value={answerDong} disabled={answerHold} onChange={event=>setAnswerDong(event.target.value)}><option value="">동 선택</option>{dongs.map(dong=><option key={dong} value={dong}>{dong}</option>)}</select><button disabled={!controlEnabled||displayState!=='ASKING'||!state?.box_id||(!answerHold&&!answerDong)} onClick={()=>void command('answer',answerHold?{box_id:state?.box_id??'',zone:'HOLD'}:{box_id:state?.box_id??'',dong:answerDong})}>답변</button></div><label className="checkbox"><input type="checkbox" checked={answerHold} onChange={event=>setAnswerHold(event.target.checked)}/> HOLD로 보류</label></div><div className="field"><label htmlFor="zone">구역 초기화</label><div className="inline-input"><select id="zone" value={selectedZone} onChange={event=>setSelectedZone(event.target.value)}>{RESET_ZONES.map(zone=><option key={zone}>{zone}</option>)}</select><button disabled={!controlEnabled} onClick={()=>void command('reset_zone',{zone:selectedZone})}>초기화</button></div></div></div>
            <p className="inline-notice" role="status">{notice}</p>
            {state?.pending_question&&<p className="question">질문 대기 · {state.pending_question}</p>}
          </section>
          <section className="panel"><div className="section-heading"><div><span className="eyebrow">02 / DISTRIBUTION</span><h2>구역별 적재 현황</h2></div><span className="micro-note">PostgreSQL 공식 집계</span></div><div className="zone-grid">{ZONES.map(zone=><div key={zone} className="zone-tile"><span className={`zone-symbol zone-${zone.toLowerCase()}`}>{zone==='RECHECK'?'R':zone==='HOLD'?'H':zone}</span><div><strong>{zone}</strong><small>{zone==='HOLD'?'보류 구역':zone==='RECHECK'?'재확인 구역':'기본 적재 구역'}</small></div><b>{summary?String(summary.by_zone[zone]??0):'—'}<small>건</small></b></div>)}</div></section>
          <section className="panel"><div className="section-heading"><div><span className="eyebrow">03 / HISTORY</span><h2>최근 분류 이력</h2></div><a className="text-link" href={`/api/export.csv?session_id=${encodeURIComponent(sessionId||'all')}`}>CSV 다운로드 ↗</a></div><div className="table-scroll"><table><thead><tr><th>박스 ID</th><th>동</th><th>분류</th><th>구역</th><th>시각</th></tr></thead><tbody>{items.length?items.map((item,index)=><tr key={`${item.box_id??'box'}-${index}`}><td>{item.box_id??'—'}</td><td>{item.dong??'—'}</td><td><span className={`chip ${item.result==='HELD'?'warning':''}`}>{String(item.result??item.outcome??'—')}</span></td><td>{item.zone??'—'}</td><td>{displayTime(item.finished_at)}</td></tr>):<tr><td colSpan={5} className="no-rows">{error ? "이력 조회 실패 — 서버 연결 확인 필요" : "표시할 이력이 없습니다."}</td></tr>}</tbody></table></div></section>
        </div>
        <div className="stack">
          <section className="panel"><div className="section-heading"><div><span className="eyebrow">OCR / LAST RESULT</span><h2>최근 판독 결과</h2></div><span className="micro-note">MQTT voss/result</span></div><div className="ocr-card"><small>최근 처리 박스</small><strong>{latestResult?.box_id??'아직 처리된 박스가 없습니다'}</strong><div className="ocr-line"><span>인식 동</span><b>{latestResult?.dong??'—'}</b></div><div className="ocr-line"><span>분류 구역</span><b>{latestResult?.zone??'—'}</b></div><div className="ocr-line"><span>분류 결과</span><b>{latestResult?.outcome??'—'}</b></div><div className="ocr-line"><span>인식 신뢰도</span><b>{typeof latestResult?.confidence==='number'?`${(latestResult.confidence*100).toFixed(1)}%`:'—'}</b></div><div className="ocr-line"><span>원문</span><b>{latestResult?.raw_text??'—'}</b></div></div></section>
          <section className="panel"><div className="section-heading"><div><span className="eyebrow">EXCEPTIONS / HOLD</span><h2>보류 목록</h2></div><span className="count-badge">{held.length}건 표시</span></div><div className="hold-list">{held.length?held.map((item,index)=><div className="hold-item" key={`${item.box_id??'held'}-${index}`}><div><strong>{item.box_id??'—'}</strong><small>{item.dong??item.reason??'동 판독 대기'}</small></div><span>{item.zone??'HOLD'}</span></div>):<p className="empty">{error ? "보류 목록 조회 실패 — 서버 연결 확인 필요" : "보류 중인 기록이 없습니다."}</p>}</div></section>
        </div>
      </div>
      <PalletPanel pallet={pallet} sortState={displayState} stale={!sseConnected||displayMqtt!=='UP'} dongs={dongs} controlEnabled={controlEnabled} onCommand={(type,args)=>void command(type,args)}/>
      {error&&<p className="error-banner" role="alert">DB / API 조회 실패: {error} — 정확하지 않은 합계는 표시하지 않습니다.</p>}
      </>}
      <footer className="footer"><span>VOSS C-3 · WEB HMI</span><span>세션: {sessionId||'NO_SESSION'}</span><span>조회 시각: {displayTime(summary?.as_of)}</span><span>{!isLocal?'원격 조회 모드 · STOP만 허용':'공용 PC 로컬 제어'}</span></footer>
    </main>
  </div>;
}
/** 서버 집계 숫자가 없으면 추정하지 않고 미확인 값으로 표시한다. */
function Metric({label,value,info,tone='default',suffix=''}:{label:string;value:string;info:string;tone?:string;suffix?:string}) {
  return <div className={`metric metric-${tone}`}><span className="metric-label">{label}</span><div className="metric-value">{value}<small>{suffix}</small></div><span className="metric-info">{info}</span></div>;
}
