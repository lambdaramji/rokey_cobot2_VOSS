// Sprint 2 S2-T08 팔레타이징 패널: 경로 입력, 3D 팔레트(4×2×2), 위에서 본 칸 표, 실을 수·초과·경로 제외, 경고, 진행률.
// 입력: SSE pallet_state(PalletState), zone_map 정식 동. 출력: POST /api/commands palletize·reset_zone PALLET.
// 근거: BRD v1.5 10.4·TR-PAL-01·10, docs/interfaces/web_api.md (S2-T08), voss_msgs.md PalletState.
import { useState } from 'react';
import type { CommandArgs } from './api';
import type { CommandType, PalletState } from './types';
import {
  boxShape, columnLabel, COLS, deckShape, dongColor, drawOrder, MAX_ROUTE, overflowWarning, palletKey,
  progress, routeFromPicks, routePreview, RUN_STATE_TEXT, shade, slotCell, summaryRows, topViewRows, VIEW_BOX,
} from './pallet';

type Props = {
  pallet:PalletState;
  stale:boolean;
  dongs:string[];
  controlEnabled:boolean;
  onCommand:(type:CommandType,args?:CommandArgs)=>void;
};

const STATE_TEXT:Record<string,string> = { EMPTY:'빈 칸', PLANNED:'계획', MOVING:'옮기는 중', DONE:'적재', FAILED:'실패' };

export default function PalletPanel({pallet,stale,dongs,controlEnabled,onCommand}:Props) {
  const [picks,setPicks] = useState<string[]>(Array(MAX_ROUTE).fill(''));
  const check = routeFromPicks(picks,dongs);
  const prog = progress(pallet);
  const warning = overflowWarning(pallet);
  const rows = summaryRows(pallet);
  const color = (dong:string) => dongColor(dong,dongs,pallet.dongs);
  const running = pallet.state === 'RUNNING';

  return <section className="panel pallet-panel" data-testid="pallet-panel" data-pallet-key={palletKey(pallet)}>
    <div className="section-heading"><div><span className="eyebrow">04 / PALLETIZING</span><h2>팔레트 적재 (트럭 짐칸)</h2></div>
      <span className={`chip ${stale||pallet.state==='PAUSED'?'warning':''}`}>{stale?'갱신 안 됨 · 마지막 배치도':RUN_STATE_TEXT[pallet.state] ?? pallet.state}</span></div>

    <div className="route-picker">
      {picks.map((pick,i)=><div className="field" key={i}><label htmlFor={`route-${i}`}>{i+1}번째 배송지{i===0?' (문 쪽)':''}</label>
        <div className="inline-input"><select id={`route-${i}`} value={pick} onChange={event=>setPicks(picks.map((p,j)=>j===i?event.target.value:p))}>
          <option value="">{i===0?'동 선택':'없음'}</option>{dongs.map(dong=><option key={dong} value={dong}>{dong}</option>)}</select></div></div>)}
    </div>
    <div className="route-actions">
      <span className="route-preview">{check.ok?routePreview(check.route):check.message}</span>
      <button className="action primary" disabled={!controlEnabled||!check.ok||running} onClick={()=>check.ok&&onCommand('palletize',{route:check.route})}>▶ &nbsp; 팔레타이징 시작</button>
      <button className="action subdued" disabled={!controlEnabled||running} onClick={()=>onCommand('reset_zone',{zone:'PALLET'})}>팔레트 비움</button>
    </div>

    {warning&&<p className="pallet-warning" role="alert">⚠ {warning}</p>}

    <div className="pallet-progress" data-testid="pallet-progress"><div className="progress-text"><strong>{prog.text}</strong>{pallet.box_id&&<small>옮기는 박스 {pallet.box_id}</small>}</div>
      <div className="progress-bar"><span className="progress-done" style={{width:`${prog.donePct}%`}}/><span className="progress-failed" style={{width:`${prog.failedPct}%`}}/></div></div>

    <svg className="pallet-3d" viewBox={VIEW_BOX} role="img" aria-label={`팔레트 3D 배치도 — ${prog.text}`}>
      <Deck/>
      {drawOrder().map(slot=><Box key={slot} slot={slot} state={pallet.slot_state[slot]} dong={pallet.slot_dong[slot]} boxId={pallet.slot_box_id[slot]} color={color(pallet.slot_dong[slot])}/>)}
      {Array.from({length:COLS},(_,i)=>{const [x,y]=columnLabel(i+1);return <text key={i} x={x} y={y} className="axis-label" textAnchor="middle">{i+1}열</text>;})}
      <text x={-22} y={-28} className="axis-label" textAnchor="end">◀ 트럭 머리</text>
      <text x={-22} y={-20} className="axis-note" textAnchor="end">(안쪽)</text>
      <text x={262} y={-4} className="axis-label">문 ▶</text>
      <text x={262} y={4} className="axis-note">(먼저 내림)</text>
      <text x={-6} y={-52} className="axis-note" textAnchor="end">2층</text>
      <text x={-6} y={-11} className="axis-note" textAnchor="end">1층</text>
      <text x={258} y={-44} className="axis-note">2줄(뒤)</text>
      <text x={258} y={-33} className="axis-note">↙ 1줄(앞)</text>
    </svg>

    <div className="pallet-legend">{rows.filter(r=>r.order>0||r.excluded>0).map(r=><span key={r.dong}><i style={{background:color(r.dong)}}/>{r.dong}</span>)}
      <span className="legend-state"><i className="legend-planned"/>계획</span><span className="legend-state"><i className="legend-done"/>적재</span><span className="legend-state"><i className="legend-failed"/>실패</span></div>

    <div className="pallet-tables">
      <div className="table-scroll"><table className="top-view"><caption>위에서 본 칸 (칸 번호 = 적재 순서)</caption>
        <thead><tr><th/>{Array.from({length:COLS},(_,i)=><th key={i}>{i+1}열{i===0?' (트럭 머리)':i===COLS-1?' (문)':''}</th>)}</tr></thead>
        <tbody>{topViewRows().map(row=><tr key={row.label}><th>{row.label}</th>{row.slots.map(slot=>{const st=pallet.slot_state[slot];const dong=pallet.slot_dong[slot];
          return <td key={slot} className={`slot-cell slot-${st.toLowerCase()}`} style={dong?{borderLeftColor:color(dong)}:undefined} title={pallet.slot_box_id[slot]||undefined}>
            <b>{slot+1}</b> {dong||'—'}<small>{STATE_TEXT[st]??st}</small></td>;})}</tr>)}</tbody></table></div>
      <div className="table-scroll"><table><caption>구역별 실을 수 · 초과 · 경로 제외</caption>
        <thead><tr><th>동</th><th>배송 순번</th><th>실을 수</th><th>초과</th><th>경로 제외</th></tr></thead>
        <tbody>{rows.length?rows.map(r=><tr key={r.dong}><td><i className="dong-dot" style={{background:color(r.dong)}}/>{r.dong}</td><td>{r.order>0?`${r.order}번째`:'경로 밖'}</td><td>{r.load}</td><td className={r.overflow>0?'warn-text':''}>{r.overflow}</td><td>{r.excluded}</td></tr>)
          :<tr><td colSpan={5} className="no-rows">{pallet.run_id?'대상 조회·계획 중입니다.':'팔레타이징 실행이 없습니다.'}</td></tr>}</tbody></table></div>
    </div>
    <p className="micro-note pallet-note">시작·비움은 공용 PC 로컬에서만. 줄 앞뒤 방향은 결정 D6·교시(S2-T02) 전 임시. 공식 기록: PostgreSQL pallet_log.</p>
  </section>;
}

function Deck() {
  const d = deckShape();
  return <g className="deck"><polygon points={d.top}/><polygon points={d.front}/><polygon points={d.right}/></g>;
}

/** 칸 하나: 빈 칸은 점선 윤곽, 계획은 옅은 동 색, 옮기는 중은 깜빡임, 적재는 진한 동 색, 실패는 붉은색. */
function Box({slot,state,dong,boxId,color}:{slot:number;state:string;dong:string;boxId:string;color:string}) {
  const shape = boxShape(slot);
  const c = slotCell(slot);
  const base = state === 'FAILED' ? '#c2525c' : color;
  const fills = { front: base, top: shade(base,1.25), right: shade(base,0.72) };
  const title = `칸 ${slot+1} · ${c.col}열 ${c.layer}층 ${c.lane}줄 · ${dong||'계획 없음'} · ${STATE_TEXT[state]??state}${boxId?` · ${boxId}`:''}`;
  return <g className={`box box-${state.toLowerCase()}`} data-slot={slot}>
    <title>{title}</title>
    <polygon points={shape.front} fill={fills.front}/><polygon points={shape.top} fill={fills.top}/><polygon points={shape.right} fill={fills.right}/>
    {state==='FAILED'&&<text x={shape.label[0]} y={shape.label[1]+3} className="box-mark" textAnchor="middle">✕</text>}
  </g>;
}
