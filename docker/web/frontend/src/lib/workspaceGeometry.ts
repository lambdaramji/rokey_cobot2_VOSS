/**
 * VOSS 2D 관제의 위치·적재 순서를 계산한다.
 * 입력: 호스트 voss_config.yaml의 검증된 배치 스냅샷과 DB 구역별 개수.
 * 출력: 로봇 베이스를 원점으로 하는 화면 좌표 및 칸별 층수.
 * 관련: docs/interfaces/voss_config.md, sort_fsm.py Config.slot_at.
 */

export type ZoneId = 'TRUCK' | 'A' | 'B' | 'C' | 'RECHECK' | 'HOLD';

export interface ZoneLayout {
  readonly name: ZoneId;
  readonly xMm: number;
  readonly yMm: number;
  readonly columns: number;
  readonly rows: number;
  readonly layers: number;
  readonly pitchXMm: number;
  readonly pitchYMm: number;
  readonly offsetXMm: number;
  readonly order: readonly number[];
}

export interface OccupiedSlot {
  readonly slot: number;
  readonly layer: number;
  readonly column: number;
  readonly row: number;
}

// 2026-10-12 Nodes PC의 실제 설정 SHA 39bf41a1bbe9를 시각화한 읽기 전용 스냅샷.
// 실제 계약/배치가 바뀌면 프론트 좌표도 함께 검토해야 한다.
export const CONFIG_SHA_SHORT = '39bf41a1bbe9';
export const SORT_ORDER = [0, 1, 2, 3, 4, 5] as const; // 10/14 사용자: 왼쪽 위 0·1·2 → 왼쪽 아래 3·4·5 → 2층 6(칸 0 위)

export const ZONES: readonly ZoneLayout[] = [
  { name: 'TRUCK', xMm: -158.82, yMm: 251.05, columns: 4, rows: 2, layers: 2, pitchXMm: 50, pitchYMm: 60, offsetXMm: 0, order: [] },
  { name: 'A', xMm: 213.49, yMm: 165.23, columns: 3, rows: 2, layers: 2, pitchXMm: 60, pitchYMm: 60, offsetXMm: 0, order: SORT_ORDER },
  { name: 'B', xMm: 446.08, yMm: 160.78, columns: 3, rows: 2, layers: 2, pitchXMm: 60, pitchYMm: 60, offsetXMm: 0, order: SORT_ORDER },
  { name: 'C', xMm: 675.14, yMm: 158.69, columns: 3, rows: 2, layers: 2, pitchXMm: 50, pitchYMm: 60, offsetXMm: -30, order: SORT_ORDER },
  { name: 'RECHECK', xMm: 446.17, yMm: -69.04, columns: 2, rows: 1, layers: 1, pitchXMm: 60, pitchYMm: 60, offsetXMm: 0, order: [] },
  { name: 'HOLD', xMm: 674.12, yMm: -71.37, columns: 2, rows: 1, layers: 1, pitchXMm: 60, pitchYMm: 60, offsetXMm: 0, order: [] },
];

export const ROBOT_BASE_MM = { x: 0, y: 0 } as const;
export const OBSERVE_MM = { x: -11.51, y: -271.11 } as const;

const ORIGIN_PIXEL_X = 600;
const ORIGIN_PIXEL_Y = 540;
export const PIXELS_PER_MM = 1.04;

/** 베이스(mm) 좌표를 동일 축척의 SVG 화면 좌표로 바꾼다. */
export function toScreen(xMm: number, yMm: number): { x: number; y: number } {
  return {
    x: ORIGIN_PIXEL_X + xMm * PIXELS_PER_MM,
    y: ORIGIN_PIXEL_Y - yMm * PIXELS_PER_MM,
  };
}


export interface TrayShellHorizontalLayout {
  readonly centerX: number;
  readonly leftX: number;
  readonly widthPx: number;
}

/** 트레이 외곽 왼쪽 끝을 계산한다. SVG 트레이와 컨베이어가 동일 계산을 쓴다. */
export function getTrayShellHorizontalLayout(zone: ZoneLayout): TrayShellHorizontalLayout {
  const pitchX = zone.pitchXMm * PIXELS_PER_MM;
  const cellWidth = Math.min(52, pitchX - 9);
  const widthPx = (zone.columns - 1) * pitchX + cellWidth + 22;
  const centerX = toScreen(zone.xMm, zone.yMm).x + zone.offsetXMm * PIXELS_PER_MM;
  return {
    centerX,
    leftX: centerX - widthPx / 2,
    widthPx,
  };
}


// BRD v1.3 장비 외형: 전체 1,090 mm, 상부 벨트 1,040 mm, 벨트 폭 70 mm.
// TRUCK의 (-158.82, 251.05)는 트레이 적재 기준 pose이지 물리적 끝점 측정이 아니다.
// 컨베이어 왼쪽 끝은 2D TRUCK 트레이 테두리의 왼쪽 끝과 맞춘다.
// 이는 화면 정렬 규칙이며, 실제 물리적 TRUCK 끝점 좌표를 확정한 게 아니다.
// 벨트 Y 위치는 실측되지 않았다. 기본 화면은 DEMO 박스 경로(관측 자세 Y)에 맞춘 도식이다.
export const BELT_LENGTH_MM = 1090;
export const BELT_TOP_LENGTH_MM = 1040;
export const BELT_WIDTH_MM = 70;
export const BELT_Y_SCHEMATIC_MM = OBSERVE_MM.y;
export const BELT_DIRECTION_BASE = { x: 0.99992, y: -0.01292 } as const;

export interface BeltLayout {
  readonly leftX: number;
  readonly centerY: number;
  readonly lengthPx: number;
  readonly widthPx: number;
  readonly activeBeltInsetPx: number;
  readonly angleDegrees: number;
}

/** LIVE에서는 관측된 박스 Y를 중심선으로 사용하고, 그 외에는 DEMO 도식을 사용한다. */
export function getBeltLayout(boxYmm: number = BELT_Y_SCHEMATIC_MM): BeltLayout {
  const truck = ZONES.find((zone) => zone.name === 'TRUCK');
  if (!truck) {
    throw new Error('TRUCK 구역 설정이 없습니다.');
  }
  const truckShell = getTrayShellHorizontalLayout(truck);
  const beltY = toScreen(0, boxYmm);
  const angleRadians = Math.atan2(-BELT_DIRECTION_BASE.y, BELT_DIRECTION_BASE.x);
  return {
    leftX: truckShell.leftX,
    centerY: beltY.y,
    lengthPx: BELT_LENGTH_MM * PIXELS_PER_MM,
    widthPx: BELT_WIDTH_MM * PIXELS_PER_MM,
    activeBeltInsetPx: (BELT_LENGTH_MM - BELT_TOP_LENGTH_MM) * PIXELS_PER_MM / 2,
    angleDegrees: angleRadians * 180 / Math.PI,
  };
}

/** 순서 n이 실제 적재되는 slot ID를 구한다(sort_fsm.py와 같은 규칙). */
export function slotAt(zone: ZoneLayout, index: number): number {
  if (index < 0 || !Number.isInteger(index)) {
    throw new RangeError('적재 순번은 0 이상의 정수여야 합니다.');
  }
  if (index < zone.order.length) {
    return zone.order[index];
  }
  return index;
}

/** 구역별 확정 집계 건수로 채워진 칸·층을 계산한다. */
export function getOccupiedSlots(zone: ZoneLayout, count: number): OccupiedSlot[] {
  if (!Number.isFinite(count)) {
    return [];
  }
  const capacity = zone.columns * zone.rows * zone.layers;
  const safeCount = Math.max(0, Math.min(capacity, Math.floor(count)));
  const footprint = zone.columns * zone.rows;
  const occupied: OccupiedSlot[] = [];
  for (let index = 0; index < safeCount; index += 1) {
    const slot = slotAt(zone, index);
    const physicalIndex = slot % footprint;
    occupied.push({
      slot,
      layer: Math.floor(slot / footprint),
      column: physicalIndex % zone.columns,
      row: Math.floor(physicalIndex / zone.columns),
    });
  }
  return occupied;
}

/** 유효한 구역 이름만 통과시켜 원치 않는 위치 표시를 막는다. */
export function getZone(zoneName: string | undefined): ZoneLayout | undefined {
  return ZONES.find((zone) => zone.name === zoneName);
}

/** 화면 이동은 상태 기반 시각효과이지 실제 관절 위치가 아니다. */
export function armHeadingDegrees(state: string, resultZone?: ZoneId): number {
  if (resultZone) {
    const zone = ZONES.find((item) => item.name === resultZone);
    if (zone) {
      const target = toScreen(zone.xMm, zone.yMm);
      const base = toScreen(ROBOT_BASE_MM.x, ROBOT_BASE_MM.y);
      return (Math.atan2(target.y - base.y, target.x - base.x) * 180) / Math.PI;
    }
  }
  if (state === 'PICKING') {
    return 90;
  }
  if (state === 'RECHECK' || state === 'ASKING') {
    return -18;
  }
  return 92;
}
