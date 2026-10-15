// Sprint 2 S2-T08 팔레트 3D 화면의 순수 계산(React·DOM 없음, node --test 로 시험).
// 입력: voss/pallet/state JSON(PalletState). 출력: 칸 좌표·사선 투영 다각형·집계·진행률·경로 검사.
// 근거: BRD v1.5 10.4·TR-PAL-10, docs/interfaces/voss_msgs.md PalletState, web_api.md pallet_state.
import type { PalletPlacements, PalletState } from './types';

export const COLS = 4;
export const LANES = 2;
export const LAYERS = 2;
export const CAPACITY = COLS * LANES * LAYERS;
export const MAX_ROUTE = 3;
export const SLOT_STATES = ['EMPTY','PLANNED','MOVING','DONE','FAILED'] as const;
export type SlotState = typeof SLOT_STATES[number];
export type Cell = { col:number; layer:number; lane:number };

/** slot = (열−1)×4 + (층−1)×2 + (줄−1) (결정 D2) → 열·층·줄 (1부터). */
export function slotCell(slot:number):Cell {
  return { col: Math.floor(slot / 4) + 1, layer: Math.floor((slot % 4) / 2) + 1, lane: (slot % 2) + 1 };
}

export function cellSlot(c:Cell):number { return (c.col - 1) * 4 + (c.layer - 1) * 2 + (c.lane - 1); }

const EMPTY_STATE:PalletState = {
  run_id:'', state:'', route:[], dongs:[], load:[], overflow:[], excluded:[], overflow_warning:false,
  total:0, done:0, failed:0, box_id:'',
  slot_state:Array(CAPACITY).fill('EMPTY'), slot_box_id:Array(CAPACITY).fill(''), slot_dong:Array(CAPACITY).fill(''),
};

export function emptyPallet():PalletState { return structuredClone(EMPTY_STATE); }

/** pallet_state 가 아직 없는 Web PC에서 공식 pallet_log의 확정 결과로 배치도를 채운다. */
export function palletFromPlacements(snapshot:PalletPlacements):PalletState {
  const state = emptyPallet();
  if (!snapshot.run_id) return state;
  state.run_id = snapshot.run_id;
  state.state = 'DONE'; // 회차 종료 여부는 DB에 없으므로 패널에서 별도 출처 문구로 표시한다.
  const routeOrder = new Map<string,number>();
  for (const item of snapshot.items) {
    if (!item.dong) continue;
    const order = typeof item.route_index === 'number' ? item.route_index : MAX_ROUTE;
    routeOrder.set(item.dong, Math.min(routeOrder.get(item.dong) ?? order, order));
  }
  state.dongs = [...routeOrder.keys()].sort((a,b)=>(routeOrder.get(a)??MAX_ROUTE)-(routeOrder.get(b)??MAX_ROUTE));
  state.route = state.dongs.filter(dong=>(routeOrder.get(dong)??MAX_ROUTE)<MAX_ROUTE);
  state.load = state.dongs.map(dong=>snapshot.items.filter(item=>item.dong===dong && item.result==='DONE').length);
  state.overflow = state.dongs.map(dong=>snapshot.items.filter(item=>item.dong===dong && item.result==='OVERFLOW').length);
  state.excluded = state.dongs.map(dong=>snapshot.items.filter(item=>item.dong===dong && item.result==='EXCLUDED').length);
  state.overflow_warning = state.overflow.some(count=>count>0);
  for (const item of snapshot.items) {
    const slot = item.pallet_slot;
    if (slot === null || !Number.isInteger(slot) || slot < 0 || slot >= CAPACITY) continue;
    if (item.result !== 'DONE' && item.result !== 'FAILED') continue;
    state.slot_state[slot] = item.result;
    state.slot_box_id[slot] = item.box_id;
    state.slot_dong[slot] = item.dong;
  }
  state.done = state.slot_state.filter(slot=>slot==='DONE').length;
  state.failed = state.slot_state.filter(slot=>slot==='FAILED').length;
  state.total = CAPACITY;
  return state;
}

const isText = (v:unknown):v is string => typeof v === 'string';
const isInt = (v:unknown):v is number => typeof v === 'number' && Number.isInteger(v);
const textList = (v:unknown, n?:number):v is string[] => Array.isArray(v) && v.every(isText) && (n === undefined || v.length === n);
const intList = (v:unknown, n:number):v is number[] => Array.isArray(v) && v.every(isInt) && v.length === n;

/** 계약(voss_msgs.md)에 맞는 PalletState 만 받는다. 어긋나면 null — 화면은 이전 배치도를 유지한다. */
export function parsePalletState(raw:unknown):PalletState|null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string,unknown>;
  if (!isText(r.run_id) || !isText(r.state) || !['','RUNNING','PAUSED','DONE'].includes(r.state)) return null;
  if (!textList(r.route) || r.route.length > MAX_ROUTE || !textList(r.dongs)) return null;
  const n = r.dongs.length;
  if (!intList(r.load,n) || !intList(r.overflow,n) || !intList(r.excluded,n)) return null;
  if (typeof r.overflow_warning !== 'boolean' || !isInt(r.total) || !isInt(r.done) || !isInt(r.failed) || !isText(r.box_id)) return null;
  if (!textList(r.slot_state,CAPACITY) || !textList(r.slot_box_id,CAPACITY) || !textList(r.slot_dong,CAPACITY)) return null;
  if (!r.slot_state.every(s=>(SLOT_STATES as readonly string[]).includes(s))) return null;
  return {
    run_id:r.run_id, state:r.state, route:[...r.route], dongs:[...r.dongs], load:[...r.load], overflow:[...r.overflow],
    excluded:[...r.excluded], overflow_warning:r.overflow_warning, total:r.total, done:r.done, failed:r.failed, box_id:r.box_id,
    slot_state:[...r.slot_state], slot_box_id:[...r.slot_box_id], slot_dong:[...r.slot_dong],
  };
}

// ---------------------------------------------------------------- 사선 투영 (mm, 박스 실제 비율)
// 46 mm 변 = X(열 방향, ADR-0009), 31 mm = Y(줄), 27 mm = Z(층). 층 사이를 벌려 아래층 윗면도 보이게 한다.
export const BOX = { x:46, y:31, z:27 };
const GAP = { x:8, y:8, z:14 };
const DEPTH = { dx:0.49, dy:-0.38 };  // Y 1 mm 가 화면에서 오른쪽 위로 가는 양 (사선 투영)
// 앞줄 = 1줄 (줄 순서 D6·실제 교시 방향이 정해지면 이 값만 바꾼다)
export const FRONT_LANE = 1;

type Point = [number,number];
export type BoxShape = { slot:number; cell:Cell; front:string; top:string; right:string; label:Point };

function project(x:number, y:number, z:number):Point {
  return [round(x + y * DEPTH.dx), round(-z + y * DEPTH.dy)];
}
const round = (v:number) => Math.round(v * 10) / 10;
const points = (ps:Point[]) => ps.map(p=>p.join(',')).join(' ');

/** 박스 하나의 앞·윗·오른쪽 면(화면 좌표). 원점 = 1열 1층 앞줄의 앞-아래-왼쪽 모서리. */
export function boxShape(slot:number):BoxShape {
  const cell = slotCell(slot);
  const x0 = (cell.col - 1) * (BOX.x + GAP.x);
  const y0 = (cell.lane === FRONT_LANE ? 0 : 1) * (BOX.y + GAP.y);
  const z0 = (cell.layer - 1) * (BOX.z + GAP.z);
  const [x1,y1,z1] = [x0 + BOX.x, y0 + BOX.y, z0 + BOX.z];
  return {
    slot, cell,
    front: points([project(x0,y0,z0), project(x1,y0,z0), project(x1,y0,z1), project(x0,y0,z1)]),
    top: points([project(x0,y0,z1), project(x1,y0,z1), project(x1,y1,z1), project(x0,y1,z1)]),
    right: points([project(x1,y0,z0), project(x1,y1,z0), project(x1,y1,z1), project(x1,y0,z1)]),
    label: project(x0 + BOX.x / 2, y0, z0 + BOX.z / 2),
  };
}

/** 화가 알고리즘 순서: 아래층 → 위층, 뒷줄 → 앞줄, 왼쪽 열 → 오른쪽 열. */
export function drawOrder():number[] {
  const slots = Array.from({length:CAPACITY},(_,s)=>s);
  const key = (s:number) => { const c = slotCell(s); return [c.layer, c.lane === FRONT_LANE ? 1 : 0, c.col]; };
  return slots.sort((a,b)=>{ const [ka,kb] = [key(a),key(b)]; return ka[0]-kb[0] || ka[1]-kb[1] || ka[2]-kb[2]; });
}

/** 팔레트 바닥판(1층 아래 6 mm)의 윗·앞·오른쪽 면. */
export function deckShape():{top:string;front:string;right:string} {
  const [x0,x1] = [-6, COLS * BOX.x + (COLS - 1) * GAP.x + 6];
  const [y0,y1] = [-6, LANES * BOX.y + GAP.y + 6];
  const [z0,z1] = [-6, 0];
  return {
    top: points([project(x0,y0,z1), project(x1,y0,z1), project(x1,y1,z1), project(x0,y1,z1)]),
    front: points([project(x0,y0,z0), project(x1,y0,z0), project(x1,y0,z1), project(x0,y0,z1)]),
    right: points([project(x1,y0,z0), project(x1,y1,z0), project(x1,y1,z1), project(x1,y0,z1)]),
  };
}

/** 열 번호 글자 위치(바닥판 앞 모서리 아래). */
export function columnLabel(col:number):Point {
  return project((col - 1) * (BOX.x + GAP.x) + BOX.x / 2, -6, -16);
}

export const VIEW_BOX = '-58 -112 352 136';

// ---------------------------------------------------------------- 색·집계·진행률

export const DONG_COLORS = ['#3fc1c9','#f5a65b','#9b8cf2','#7bd389','#f27b9b','#e8d36a'];

/** 동 색은 zone_map 순서로 고정한다(실행마다 경로가 달라도 같은 동은 같은 색). 없으면 PalletState.dongs 순서. */
export function dongColor(dong:string, zoneMapDongs:string[], palletDongs:string[]):string {
  if (!dong) return '#5b6f80';
  let i = zoneMapDongs.indexOf(dong);
  if (i < 0) { const j = palletDongs.indexOf(dong); i = zoneMapDongs.length + Math.max(j,0); }
  return DONG_COLORS[i % DONG_COLORS.length];
}

/** #rrggbb 를 factor 배 밝게(>1)·어둡게(<1). 면 음영용. */
export function shade(hex:string, factor:number):string {
  const n = parseInt(hex.slice(1),16);
  const ch = [(n>>16)&255,(n>>8)&255,n&255].map(v=>Math.max(0,Math.min(255,Math.round(v*factor))));
  return '#' + ch.map(v=>v.toString(16).padStart(2,'0')).join('');
}

export type SummaryRow = { dong:string; order:number; load:number; overflow:number; excluded:number };

/** 구역별 실을 수 / 초과 / 경로 제외 (TR-PAL-10 ①). order = 배송 순번(1부터), 경로 밖 = 0. */
export function summaryRows(st:PalletState):SummaryRow[] {
  return st.dongs.map((dong,i)=>({ dong, order: st.route.indexOf(dong) + 1, load: st.load[i], overflow: st.overflow[i], excluded: st.excluded[i] }));
}

/** "배송 물량 남음" 경고 문구. 경고가 없으면 "". */
export function overflowWarning(st:PalletState):string {
  if (!st.overflow_warning) return '';
  const parts = summaryRows(st).filter(r=>r.overflow > 0).map(r=>`${r.dong} ${r.overflow}개`);
  return `배송 물량 남음 — 초과로 못 싣는 박스 ${parts.join(', ')} (원래 구역에 그대로 둡니다)`;
}

export type Progress = { total:number; done:number; failed:number; text:string; donePct:number; failedPct:number };

/** 진행률 "n개 중 m개" (TR-PAL-10 ④). */
export function progress(st:PalletState):Progress {
  const { total, done, failed } = st;
  if (!st.run_id) return { total, done, failed, text:'실행 없음', donePct:0, failedPct:0 };
  if (st.dongs.length === 0) return { total, done, failed, text:'대상 조회·계획 중', donePct:0, failedPct:0 };
  const pct = (v:number) => total > 0 ? Math.min(100, v / total * 100) : 0;  // 반올림하면 합이 100 을 넘는다
  const tail = failed > 0 ? ` · 실패 ${failed}` : '';
  return { total, done, failed, text:`${total}개 중 ${done}개 적재${tail}`, donePct:pct(done), failedPct:pct(failed) };
}

export const RUN_STATE_TEXT:Record<string,string> = { '':'실행 없음', RUNNING:'적재 중', PAUSED:'멈춤 — 재개하면 다음 칸부터', DONE:'완료' };

/** 일반 '구역 초기화' 메뉴의 구역. PALLET 은 넣지 않는다 — 팔레트 초기화는 PalletPanel 의 '트럭 짐칸 비움 확인'
 *  (실물 확인 대화상자)으로만 보낸다(정의석 #47 재리뷰). REST/MQTT 의 reset_zone PALLET 계약은 그대로다. */
export const GENERAL_RESET_ZONES = ['A','B','C','RECHECK','HOLD'] as const;

/** PR #176 PL 안전 결정: 실물 비움은 분류가 멈춘 IDLE·PAUSED 에서만 확인한다. */
export function resetPalletAllowed(sortState:string, palletRunState:string):{ok:boolean; reason:string} {
  if (palletRunState === 'RUNNING') return { ok:false, reason:'팔레타이징 중' };
  if (palletRunState === 'PAUSED') return { ok:false, reason:'멈춘 팔레타이징이 있음 — 재개해서 끝낸 뒤' };
  if (sortState === 'RUNNING') return { ok:false, reason:'분류를 멈춘 뒤 비워 주세요' };
  if (!['IDLE','PAUSED'].includes(sortState)) return { ok:false, reason:'분류 IDLE·PAUSED 에서만' };
  return { ok:true, reason:'' };
}

/** 비움 확인 대화상자 문구. 카운터만 0 으로 되돌리므로 작업자가 실물 비움을 눈으로 확인해야 한다. */
export function resetPalletPrompt(st:PalletState):string {
  const placed = st.slot_state.filter(s => s === 'DONE').length;
  return `트럭 짐칸(팔레트)에 박스가 하나도 남아 있지 않은 것을 눈으로 확인했나요?\n`
    + `확인하면 팔레트 칸 기록을 비웁니다${placed ? ` (화면상 적재 ${placed}개)` : ''}. 로봇은 움직이지 않습니다.\n`
    + `박스가 남아 있으면 '취소' 후 먼저 내리세요 — 남은 채 비우면 다음 적재가 그 칸에 겹쳐 놓습니다.`;
}

/** 위에서 본 칸 표 (BRD v1.5 10.4 표와 같은 행 순서: 2층 1줄 · 2층 2줄 · 1층 1줄 · 1층 2줄, 열 1 → 4). */
export function topViewRows():{label:string; slots:number[]}[] {
  const rows:{label:string; slots:number[]}[] = [];
  for (const layer of [2,1]) for (const lane of [1,2]) {
    rows.push({ label:`${layer}층 ${lane}줄`, slots: Array.from({length:COLS},(_,i)=>cellSlot({col:i+1,layer,lane})) });
  }
  return rows;
}

/** DOM 지연 관측용 키 (scripts/integration/s2_pallet_replay.py 와 같은 형식). 칸 상태 첫 글자까지 넣는다 —
 *  당겨 놓을 박스는 옮기는 중에 칸만 바뀐다 (pending #37). */
export function palletKey(st:PalletState):string {
  return [st.run_id, st.state, st.done, st.failed, st.box_id, st.slot_state.map(s=>s[0]).join('')].join('|');
}

// ---------------------------------------------------------------- 경로 입력 (TR-PAL-01 HMI 쪽)

export type RouteCheck = { ok:true; route:string[] } | { ok:false; message:string };

/** 1·2·3번째 배송지 선택 → route. 빈 칸은 뒤에서만 허용, 중복·미등록 거부(서버·manager 도 다시 본다). */
export function routeFromPicks(picks:string[], canonical:string[]):RouteCheck {
  const last = picks.reduce((at,p,i)=>p ? i : at, -1);
  if (last < 0) return { ok:false, message:'첫 배송지를 고르세요.' };
  const route = picks.slice(0, last + 1);
  if (route.some(p=>!p)) return { ok:false, message:'배송지를 앞에서부터 차례로 고르세요.' };
  if (route.length > MAX_ROUTE) return { ok:false, message:`배송지는 ${MAX_ROUTE}곳까지입니다.` };
  if (new Set(route).size !== route.length) return { ok:false, message:'같은 동을 두 번 고를 수 없습니다.' };
  const unknown = route.find(p=>!canonical.includes(p));
  if (unknown) return { ok:false, message:`등록되지 않은 동입니다: ${unknown}` };
  return { ok:true, route };
}

/** 시작 전 되읽기 문구(음성 안내와 같은 뜻). */
export function routePreview(route:string[]):string {
  if (route.length === 0) return '';
  if (route.length === 1) return `${route[0]} 박스를 팔레트에 싣습니다.`;
  return `${route.join(' → ')} 순서 · 첫 배송지 ${route[0]}은 오른쪽(문 쪽)`;
}
