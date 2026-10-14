// Sprint 2 S2-T08 팔레트 화면 순수 계산 시험 (node --test, 추가 의존성 없음).
// 입력: fixtures/pallet_s1.json — 실제 pallet_fsm 이 만든 PalletState 열(S1 + slot 4 실패·#37 당겨 놓기). 화면 칸 번호 = slot + 1.
// 근거: BRD v1.5 10.4 표·TR-PAL-10, docs/interfaces/voss_msgs.md PalletState.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  boxShape, CAPACITY, cellSlot, deckShape, dongColor, drawOrder, emptyPallet, overflowWarning, palletKey,
  GENERAL_RESET_ZONES, parsePalletState, progress, resetPalletAllowed, resetPalletPrompt, routeFromPicks, routePreview, slotCell, summaryRows,
  topViewRows, VIEW_BOX,
} from '../src/pallet.ts';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/pallet_s1.json', import.meta.url), 'utf-8'));
const states = fixture.states.map((s:unknown)=>parsePalletState(s));
const planned = states.find((s:any)=>s.dongs.length > 0);
const final = states[states.length - 1];
const SHORT:Record<string,string> = { '청담동':'청담', '역삼동':'역삼', '대치동':'대치' };

test('slot ↔ 열·층·줄은 slot = (열−1)×4 + (층−1)×2 + (줄−1) 이다 (D2)', () => {
  assert.deepEqual(slotCell(0), {col:1, layer:1, lane:1});
  assert.deepEqual(slotCell(3), {col:1, layer:2, lane:2});
  assert.deepEqual(slotCell(6), {col:2, layer:2, lane:1});
  assert.deepEqual(slotCell(15), {col:4, layer:2, lane:2});
  for (let s = 0; s < CAPACITY; s++) assert.equal(cellSlot(slotCell(s)), s);
});

test('FSM 이 만든 PalletState 는 모두 계약 검사를 통과한다', () => {
  assert.ok(states.length >= 18);
  assert.ok(states.every((s:unknown)=>s !== null));
  assert.equal(states[0].run_id, '');  // 실행 전
});

test('어긋난 PalletState 는 버린다(이전 배치도 유지)', () => {
  const good = fixture.states[fixture.states.length - 1];
  assert.equal(parsePalletState({...good, slot_state: good.slot_state.slice(0, 15)}), null);
  assert.equal(parsePalletState({...good, slot_state: [...good.slot_state.slice(0, 15), 'LOST']}), null);
  assert.equal(parsePalletState({...good, load: [1]}), null);
  assert.equal(parsePalletState({...good, state: 'PALLETIZING'}), null);
  assert.equal(parsePalletState({...good, total: '16'}), null);
  assert.equal(parsePalletState(null), null);
  assert.deepEqual(parsePalletState(emptyPallet()), emptyPallet());
});

test('계획 직후 배치도는 BRD v1.5 10.4 시연 단계 9 표와 같다', () => {
  // 행: 2층 1줄 · 2층 2줄 · 1층 1줄 · 1층 2줄, 열 1(트럭 머리) → 4(문)
  const expected = [
    ['청담','역삼','역삼','대치'],
    ['청담','역삼','역삼','대치'],
    ['청담','청담','역삼','역삼'],
    ['청담','청담','역삼','대치'],
  ];
  const got = topViewRows().map(row=>row.slots.map(slot=>SHORT[planned.slot_dong[slot]]));
  assert.deepEqual(got, expected);
  assert.deepEqual(topViewRows().map(r=>r.label), ['2층 1줄','2층 2줄','1층 1줄','1층 2줄']);
  // 계획 직후 발행(첫 PICK 전 PublishPalletState)에서 이미 칸 0 박스가 지금 옮길 박스다
  assert.deepEqual(planned.slot_state, ['MOVING', ...Array(15).fill('PLANNED')]);
});

test('계획 직후 집계·경고: 대치 3 · 역삼 7 · 청담 6, 대치 3개 초과', () => {
  assert.deepEqual(summaryRows(planned).map(r=>[r.dong, r.order, r.load, r.overflow, r.excluded]), [
    ['대치동', 1, 3, 3, 0], ['역삼동', 2, 7, 0, 0], ['청담동', 3, 6, 0, 0],
  ]);
  assert.equal(overflowWarning(planned), '배송 물량 남음 — 초과로 못 싣는 박스 대치동 3개 (원래 구역에 그대로 둡니다)');
  assert.equal(progress(planned).text, '16개 중 0개 적재');
});

test('옮기는 중에는 MOVING 칸이 하나고 box_id 와 같은 박스다', () => {
  const moving = states.filter((s:any)=>s.box_id);
  assert.ok(moving.length >= 15);
  for (const s of moving) {
    const slots = s.slot_state.flatMap((v:string, i:number)=>v === 'MOVING' ? [i] : []);
    assert.equal(slots.length, 1);
    assert.equal(s.slot_box_id[slots[0]], s.box_id);
  }
});

test('끝: 15개 적재·1개 실패, slot 4 실패 박스 자리에 위층(slot 6) 박스를 당겨 놓았다 (#37)', () => {
  assert.equal(final.state, 'DONE');
  assert.equal(progress(final).text, '16개 중 15개 적재 · 실패 1');
  assert.equal(final.slot_box_id[4], fixture.pulled_down);
  assert.equal(final.slot_state[4], 'DONE');
  assert.equal(final.slot_state[6], 'EMPTY');
  assert.ok(!final.slot_box_id.includes(fixture.failed_box));
  const p = progress(final);
  assert.ok(p.donePct + p.failedPct <= 100);
});

test('진행률: 실행 없음 · 계획 중 · 진행 중', () => {
  assert.equal(progress(emptyPallet()).text, '실행 없음');
  const listing = states.find((s:any)=>s.run_id && s.dongs.length === 0);
  assert.equal(progress(listing).text, '대상 조회·계획 중');
});

test('3D 다각형은 모두 viewBox 안에 있고 그리기 순서는 16칸 전부·아래층 먼저다', () => {
  const [vx, vy, vw, vh] = VIEW_BOX.split(' ').map(Number);
  const pts = [...Array(CAPACITY).keys()].flatMap(s=>{const b = boxShape(s); return [b.front, b.top, b.right];});
  const d = deckShape();
  for (const poly of [...pts, d.top, d.front, d.right]) for (const pair of poly.split(' ')) {
    const [x, y] = pair.split(',').map(Number);
    assert.ok(x >= vx + 20 && x <= vx + vw - 30 && y >= vy && y <= vy + vh - 12, `${x},${y}`);
  }
  const order = drawOrder();
  assert.deepEqual([...order].sort((a,b)=>a-b), [...Array(CAPACITY).keys()]);
  const layers = order.map(s=>slotCell(s).layer);
  assert.deepEqual(layers, [...layers].sort());
  // 같은 층 안에서는 뒷줄 → 앞줄, 같은 줄 안에서는 왼쪽 → 오른쪽
  assert.deepEqual(order.slice(0, 8), [1, 5, 9, 13, 0, 4, 8, 12]);
});

test('동 색은 zone_map 순서로 고정, 모르는 동은 PalletState.dongs 순서', () => {
  const zm = ['역삼동','대치동','청담동'];
  assert.equal(dongColor('역삼동', zm, ['대치동','역삼동']), dongColor('역삼동', zm, ['역삼동']));
  assert.notEqual(dongColor('역삼동', zm, []), dongColor('대치동', zm, []));
  assert.notEqual(dongColor('신사동', zm, ['신사동']), dongColor('역삼동', zm, []));
});

test('경로 입력: 1~3곳, 앞에서부터, 중복·미등록 거부', () => {
  const zm = ['역삼동','대치동','청담동'];
  assert.deepEqual(routeFromPicks(['대치동','역삼동','청담동'], zm), {ok:true, route:['대치동','역삼동','청담동']});
  assert.deepEqual(routeFromPicks(['역삼동','',''], zm), {ok:true, route:['역삼동']});
  assert.equal(routeFromPicks(['','',''], zm).ok, false);
  assert.equal(routeFromPicks(['역삼동','','청담동'], zm).ok, false);
  assert.equal(routeFromPicks(['역삼동','역삼동',''], zm).ok, false);
  assert.equal(routeFromPicks(['신사동','',''], zm).ok, false);
  assert.equal(routePreview(['대치동','역삼동','청담동']), '대치동 → 역삼동 → 청담동 순서 · 첫 배송지 대치동은 오른쪽(문 쪽)');
});

test('지연 관측 키는 박스마다 바뀐다', () => {
  const keys = states.map(palletKey);
  for (let i = 1; i < keys.length; i++) assert.notEqual(keys[i], keys[i - 1]);
});

test('짐칸 비움 확인은 manager 와 같은 조건(분류 IDLE·PAUSED, 진행·멈춘 팔레타이징 없음)에서만 보낸다', () => {
  assert.equal(resetPalletAllowed('IDLE','').ok, true);
  assert.equal(resetPalletAllowed('PAUSED','DONE').ok, true);
  assert.equal(resetPalletAllowed('RUNNING','').ok, false);
  assert.equal(resetPalletAllowed('PALLETIZING','RUNNING').ok, false);
  assert.equal(resetPalletAllowed('PAUSED','PAUSED').ok, false);
  assert.equal(resetPalletAllowed('UNKNOWN','').ok, false);
});

test('비움 확인 문구는 실물 확인을 묻고 화면상 적재 수를 보여 준다', () => {
  const text = resetPalletPrompt(final);
  assert.match(text, /눈으로 확인/);
  assert.match(text, /화면상 적재 15개/);
  assert.match(text, /로봇은 움직이지 않습니다/);
  assert.doesNotMatch(resetPalletPrompt(emptyPallet()), /화면상 적재/);
});

test('일반 구역 초기화 메뉴에는 PALLET 이 없고, reset_zone PALLET 은 짐칸 비움 확인 버튼에서만 보낸다', () => {
  assert.deepEqual([...GENERAL_RESET_ZONES], ['A','B','C','RECHECK','HOLD']);
  const src = (name:string) => readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf-8');
  const app = src('App.tsx');
  assert.match(app, /const RESET_ZONES = GENERAL_RESET_ZONES;/);
  assert.doesNotMatch(app, /'PALLET'/);
  const panel = src('PalletPanel.tsx');
  const sends = panel.match(/onCommand\('reset_zone',\{zone:'PALLET'\}\)/g) ?? [];
  assert.equal(sends.length, 1);
  assert.match(panel, /window\.confirm\(resetPalletPrompt\(pallet\)\)\) onCommand\('reset_zone',\{zone:'PALLET'\}\)/);
});
