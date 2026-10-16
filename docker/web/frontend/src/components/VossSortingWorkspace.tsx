/**
 * VOSS Sorting Workspace: 기존 React HMI 안에 들어가는 읽기 전용 2D 시각화.
 * 입력: /api/stream(state/result/robot) 및 /api/sessions/current 집계.
 * 출력: 실제 구역 기준점과 DB 수량. 로봇 그림은 상태 이벤트에 반응하는 표현용 애니메이션.
 * 관련: docs/interfaces/web_api.md #68, mqtt.md #20, voss_config.md.
 */
import { useEffect, useReducer, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  PIXELS_PER_MM,
  getBeltLayout,
  getTrayShellHorizontalLayout,
  OBSERVE_MM,
  ROBOT_BASE_MM,
  ZONES,
  getZone,
  toScreen,
} from '../lib/workspaceGeometry';
import type { ZoneId, ZoneLayout } from '../lib/workspaceGeometry';
import { INITIAL_INDICATOR, VOICE_COMMAND_TIMEOUT_MS, VOICE_FAILURE_DISPLAY_MS, reduceVoiceIndicator } from '../lib/voiceIndicator';
import type { VoiceSignal } from '../lib/voiceIndicator';
import type { ZoneMap } from '../types';
import type { BoxMotionSample, BoxTrackSample, Point3, RobotPoseSample } from '../lib/workspacePosition';
import { boxTopFromTcp, parseBoxMotion, parseBoxTrack, parseRobotPose, POSE_STALE_MS, TRACK_STALE_MS } from '../lib/workspacePosition';
import './VossSortingWorkspace.css';

const STATE_TIMEOUT_MS = 3000;
const STATS_REFRESH_MS = 2000;
const DEMO_ZONES = ['A', 'B', 'C', 'RECHECK', 'HOLD'] as const;
type DemoPhase = 'RUNNING' | 'PICKING' | 'PLACING' | 'RETURNING';
type IllustrationPhase = DemoPhase | 'CARRYING';
const DEMO_PHASE_MS: Record<DemoPhase, number> = { RUNNING: 5000, PICKING: 1000, PLACING: 3000, RETURNING: 1000 };
const BOX_WIDTH = 34;
const BOX_HEIGHT = 36;
const ARM_UPPER_PX = 180;
const ARM_FOREARM_PX = 170;
const ARM_MAX_REACH_PX = 320;
const ARM_MIN_REACH_PX = 80;
type ScreenPoint = { x: number; y: number };
function illustrationTarget(phase: IllustrationPhase, zone: ZoneId | undefined): ScreenPoint {
  if (phase === 'PICKING') return toScreen(60, -285);
  if (phase === 'CARRYING') return toScreen(180, -20);
  if (phase === 'PLACING') {
    const target = getZone(zone);
    if (target) return toScreen(target.xMm, target.yMm);
  }
  return toScreen(OBSERVE_MM.x, OBSERVE_MM.y);
}
const DEMO_PICKUP_POINT = illustrationTarget('PICKING', undefined);
function configuredBoxOffset(): Point3 | null {
  if (import.meta.env.VITE_VOSS_BOX_OFFSET_VERIFIED !== 'true') return null;
  const values = String(import.meta.env.VITE_VOSS_TCP_BOX_TOP_OFFSET_MM ?? '').split(',').map(Number);
  if (values.length !== 3 || !values.every(Number.isFinite)) return null;
  return { x: values[0] / 1000, y: values[1] / 1000, z: values[2] / 1000 };
}
const VERIFIED_BOX_OFFSET = configuredBoxOffset();
const workspaceBelt = getBeltLayout();
const WORKSPACE_VIEWBOX_LEFT = workspaceBelt.leftX - 32;
const WORKSPACE_VIEWBOX_WIDTH = workspaceBelt.lengthPx + 64;
const WORKSPACE_VIEWBOX_TOP = 140;
const WORKSPACE_VIEWBOX_HEIGHT = 815;
const truckShell = getTrayShellHorizontalLayout(getZone('TRUCK')!);
const zoneCShell = getTrayShellHorizontalLayout(getZone('C')!);
const holdShell = getTrayShellHorizontalLayout(getZone('HOLD')!);
// 각 구역의 표시 테두리는 동일 크기다. 실제 구역 좌표와 적재 용량은 바꾸지 않는다.
const TRAY_DISPLAY_WIDTH_PX = getTrayShellHorizontalLayout(getZone('A')!).widthPx;
const TRAY_DISPLAY_HEIGHT_PX = getZone('A')!.pitchYMm * PIXELS_PER_MM + 49 + 24;
const SECTOR_C_EDGE_OFFSET_PX = holdShell.centerX - zoneCShell.centerX;
const headerAlignment: CSSProperties = {
  marginLeft: `${((truckShell.leftX - WORKSPACE_VIEWBOX_LEFT) / WORKSPACE_VIEWBOX_WIDTH) * 100}%`,
  marginRight: `${((WORKSPACE_VIEWBOX_LEFT + WORKSPACE_VIEWBOX_WIDTH - holdShell.centerX - TRAY_DISPLAY_WIDTH_PX / 2) / WORKSPACE_VIEWBOX_WIDTH) * 100}%`,
};

type ZoneCounts = Partial<Record<ZoneId, number>>;

export interface SortStateSnapshot {
  state?: string;
  box_id?: string;
  track_id?: number;
  ready?: boolean;
  session_id?: string;
}

export interface SortResultSnapshot {
  box_id?: string;
  session_id?: string;
  track_id?: number;
  zone?: string;
  outcome?: string;
}

export interface RobotStateSnapshot {
  state?: string;
  connected?: boolean;
}

export interface WorkspaceViewData {
  state: SortStateSnapshot | null;
  robot: RobotStateSnapshot | null;
  boxTracks?: BoxTrackSample[];
  robotPose?: RobotPoseSample | null;
  boxMotion?: BoxMotionSample | null;
  isPoseFresh?: boolean;
  lastResult: SortResultSnapshot | null;
  zoneCounts: ZoneCounts | null;
  zoneNames?: Record<string, string>;
  isStateFresh: boolean;
  isRobotFresh?: boolean;
  isDemo?: boolean;
  voiceSignal?: VoiceSignal | null;
  voiceConnected?: boolean;
  /** 트레이 '비움' 버튼. 없으면 읽기 전용. 팔레트 패널의 '트럭 짐칸 비움 확인'과 같은 reset_zone 명령이다. */
  controlEnabled?: boolean;
  onResetZone?: (zone: ZoneId) => void;
}

interface SessionApiResponse {
  ok?: boolean;
  session_id?: string;
  by_zone?: Record<string, number>;
  available_by_zone?: Record<string, number>;
}

interface TrayProps {
  zone: ZoneLayout;
  count: number | undefined;
  zoneName?: string;
  /** '비움' 버튼 — reset_zone 은 PAUSED 에서만 접수된다. undefined 면 버튼을 그리지 않는다. */
  onReset?: () => void;
  resetEnabled?: boolean;
  resetReason?: string;
}

const TRAY_COLORS: Record<ZoneId, string> = {
  TRUCK: '#68b1d3',
  A: '#59d9cd',
  B: '#59d9cd',
  C: '#59d9cd',
  RECHECK: '#87b5d1',
  HOLD: '#87b5d1',
};

/** DB에 없는 트럭 적재량은 임의의 0으로 표시하지 않는다. */
function normalizeCounts(byZone: Record<string, number> | undefined): ZoneCounts | null {
  if (!byZone) {
    return null;
  }
  const counts: ZoneCounts = {};
  for (const zone of ZONES) {
    const value = byZone[zone.name];
    if (Number.isFinite(value) && value >= 0) {
      counts[zone.name] = Math.floor(value);
    }
  }
  return counts;
}

/** 비움 확인 대화상자 — 칸 기록만 0 으로 되돌리므로 실물 비움은 작업자가 눈으로 확인한다 (팔레트 패널과 같은 규칙). */
function confirmResetZone(zone: ZoneId, count: number | undefined, onResetZone: (zone: ZoneId) => void): void {
  const shown = count ? ` (화면상 ${count}개)` : '';
  const ok = window.confirm(
    `${zone} 구역에 박스가 하나도 남아 있지 않은 것을 눈으로 확인했나요?\n`
    + `확인하면 ${zone} 구역 칸 기록을 비웁니다${shown}. 로봇은 움직이지 않습니다.\n`
    + '박스가 남아 있으면 \'취소\' 후 먼저 내리세요 — 남은 채 비우면 다음 적재가 그 칸에 겹쳐 놓습니다.',
  );
  if (ok) onResetZone(zone);
}

/** 기존 적재함 윤곽 안에 현재 세션의 공식 처리 수량만 표시한다. TRUCK 은 팔레트 적재 칸(DONE) 수. */
function Tray({ zone, count, zoneName, onReset, resetEnabled = false, resetReason = '' }: TrayProps) {
  const { y } = toScreen(zone.xMm, zone.yMm);
  const trayShell = getTrayShellHorizontalLayout(zone);
  const visualOffsetX = zone.name === 'C' ? SECTOR_C_EDGE_OFFSET_PX
    : zone.name === 'TRUCK' ? truckShell.leftX + TRAY_DISPLAY_WIDTH_PX / 2 - trayShell.centerX : 0;
  const trayCenterX = trayShell.centerX + visualOffsetX;
  const countText = count === undefined ? '—' : `${count} BOX`;
  const color = TRAY_COLORS[zone.name];

  return (
    <g className="voss-ws__tray">
      <text x={trayCenterX} y={y - TRAY_DISPLAY_HEIGHT_PX / 2 - 22} textAnchor="middle" className="voss-ws__zone-title">
        {['A', 'B', 'C'].includes(zone.name) ? `${zone.name}: ${zoneName ?? '—'}` : zone.name === 'TRUCK' ? 'TRUCK' : zone.name}
      </text>
      <rect
        x={trayCenterX - TRAY_DISPLAY_WIDTH_PX / 2}
        y={y - TRAY_DISPLAY_HEIGHT_PX / 2}
        width={TRAY_DISPLAY_WIDTH_PX}
        height={TRAY_DISPLAY_HEIGHT_PX}
        rx="16"
        className="voss-ws__tray-shell"
        stroke={color}
      />
      <text x={trayCenterX} y={y + 10} textAnchor="middle" className="voss-ws__zone-count">
        {countText}
      </text>
      {zone.name !== 'TRUCK' && onReset ? (
        <foreignObject x={trayCenterX - 60} y={y + TRAY_DISPLAY_HEIGHT_PX / 2 - 44} width="120" height="36">
          <button type="button" className="voss-ws__tray-reset" disabled={!resetEnabled}
            title={resetEnabled ? '실물을 비운 뒤 칸 기록을 0 으로 되돌린다 (로봇 동작 없음)' : resetReason}
            onClick={onReset}>비움</button>
        </foreignObject>
      ) : null}
    </g>
  );
}

/** 표현용 2링크 팔. 끝점은 회전각과 반경을 보간하므로 상태 변경 시 원호를 따라 움직인다. */
function Robot({ phase, zone, pose, poseFresh, picking }: {
  phase: IllustrationPhase; zone: ZoneId | undefined;
  pose?: RobotPoseSample | null; poseFresh: boolean; picking: boolean;
}) {
  const center = toScreen(ROBOT_BASE_MM.x, ROBOT_BASE_MM.y);
  // 실제 TCP 가 신선하면 팔이 TCP 점을 향한다. 도달 범위 안이면 팔 끝이 점에 겹치고,
  // 범위 밖(먼 적재함)이면 아래 반경 클램프로 그 방향에 최대한 뻗는 모션만 취한다 (10/15 현장 요청).
  // 포즈가 없거나 끊기면 상태 기반 표현 목표.
  const tcp = pose ? toScreen(pose.position.x * 1000, pose.position.y * 1000) : null;
  const target: ScreenPoint = tcp && poseFresh ? tcp : illustrationTarget(phase, zone);
  const dx = target.x - center.x;
  const dy = target.y - center.y;
  const targetAngle = Math.atan2(dy, dx);
  const targetRadius = Math.max(ARM_MIN_REACH_PX, Math.min(ARM_MAX_REACH_PX, Math.hypot(dx, dy)));
  const [shown, setShown] = useState({ angle: targetAngle, radius: targetRadius });
  const shownRef = useRef(shown);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const next = { angle: targetAngle, radius: targetRadius };
      shownRef.current = next;
      setShown(next);
      return;
    }
    let frame = 0;
    let previous = performance.now();
    function step(now: number) {
      const current = shownRef.current;
      const fraction = Math.min(1, (now - previous) / 190);
      previous = now;
      const angleDelta = Math.atan2(Math.sin(targetAngle - current.angle), Math.cos(targetAngle - current.angle));
      const radiusDelta = targetRadius - current.radius;
      const next = {
        angle: current.angle + angleDelta * fraction,
        radius: current.radius + radiusDelta * fraction,
      };
      shownRef.current = next;
      setShown(next);
      if (Math.abs(angleDelta) > .002 || Math.abs(radiusDelta) > .4) frame = requestAnimationFrame(step);
    }
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [targetAngle, targetRadius]);

  const reach = shown.radius;
  const elbowOffset = Math.acos(Math.max(-1, Math.min(1,
    (ARM_UPPER_PX ** 2 + reach ** 2 - ARM_FOREARM_PX ** 2) / (2 * ARM_UPPER_PX * reach))));
  const elbow = {
    x: center.x + ARM_UPPER_PX * Math.cos(shown.angle + elbowOffset),
    y: center.y + ARM_UPPER_PX * Math.sin(shown.angle + elbowOffset),
  };
  const tip = {
    x: center.x + reach * Math.cos(shown.angle),
    y: center.y + reach * Math.sin(shown.angle),
  };
  const gripperAngle = Math.atan2(tip.y - elbow.y, tip.x - elbow.x) * 180 / Math.PI;
  const links = [[center, elbow], [elbow, tip]];

  return (
    <g className="voss-ws__robot">
      <defs>
        <linearGradient id="vossRobotShell" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f1f9fc" />
          <stop offset=".45" stopColor="#a5c4cf" />
          <stop offset="1" stopColor="#537d91" />
        </linearGradient>
        <radialGradient id="vossRobotJoint">
          <stop offset="0" stopColor="#284c62" />
          <stop offset=".72" stopColor="#17354a" />
          <stop offset="1" stopColor="#0a2032" />
        </radialGradient>
      </defs>
      <circle cx={center.x} cy={center.y} r="57" className="voss-ws__robot-area" />
      <circle cx={center.x} cy={center.y} r="48" className="voss-ws__robot-base-rim" />
      <circle cx={center.x} cy={center.y} r="34" className="voss-ws__robot-base" />
      {links.map(([from, to], index) => <g key={index}>
        <line x1={from.x} y1={from.y + 7} x2={to.x} y2={to.y + 7} className="voss-ws__arm-shadow" />
        <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="voss-ws__arm-outline" />
        <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="voss-ws__arm-link" />
        <line x1={from.x} y1={from.y - 3} x2={to.x} y2={to.y - 3} className="voss-ws__arm-highlight" />
      </g>)}
      <circle cx={elbow.x} cy={elbow.y} r="13" className="voss-ws__arm-joint" />
      <circle cx={elbow.x} cy={elbow.y} r="6" className="voss-ws__arm-joint-core" />
      <circle cx={tip.x} cy={tip.y} r="11" className="voss-ws__arm-joint" />
      <circle cx={tip.x} cy={tip.y} r="5" className="voss-ws__arm-joint-core" />
      <g className="voss-ws__gripper" transform={`translate(${tip.x} ${tip.y}) rotate(${gripperAngle})`}>
        <rect x="-3" y="-12" width="19" height="24" rx="5" className="voss-ws__gripper-body" />
        <path d="M 15 -9 H 30 V -4 M 15 9 H 30 V 4" className="voss-ws__gripper-fingers" />
        <circle cx="5" cy="0" r="2.8" className="voss-ws__gripper-pin" />
      </g>
      {picking ? <rect x={tip.x - 12} y={tip.y - 12} width="24" height="24" rx="4" className="voss-ws__grip-preview" /> : null}
      {tcp ? <circle cx={tcp.x} cy={tcp.y} r="5" className={`voss-ws__tcp-point ${poseFresh ? '' : 'voss-ws__tcp-point--stale'}`}>
        <title>실제 TCP 위치 — 표현용 팔과 별도 좌표</title>
      </circle> : null}
      <circle cx={center.x} cy={center.y} r="17" className="voss-ws__robot-hub" />
      <circle cx={center.x} cy={center.y} r="5" className="voss-ws__robot-hub-core" />
      <text x={center.x} y={center.y - 80} textAnchor="middle" className="voss-ws__robot-title">M0609</text>
      {pose ? <text x={center.x} y={center.y + 103} textAnchor="middle" className="voss-ws__robot-z">TCP Z {Math.round(pose.position.z * 1000)} mm{poseFresh ? '' : ' · 갱신 중단'}</text> : null}
    </g>
  );
}

/** 순수 SVG이므로 브라우저에서만 표시되며 ROS나 MQTT 명령을 전송하지 않는다. */
export function VossSortingWorkspace({ state, boxTracks = [], robotPose = null, boxMotion = null, isPoseFresh = false, zoneCounts, zoneNames = {}, isStateFresh, isDemo = false, voiceSignal = null, voiceConnected = true, lastResult, controlEnabled = false, onResetZone }: WorkspaceViewData) {
  const [flashZone, setFlashZone] = useState<ZoneId | undefined>(undefined);
  const [flightBoxId, setFlightBoxId] = useState('');
  const [demoActive, setDemoActive] = useState(false);
  const [demoPhase, setDemoPhase] = useState<DemoPhase>('RUNNING');
  const [demoIndex, setDemoIndex] = useState(0);
  const [demoCounts, setDemoCounts] = useState<ZoneCounts | null>(null);
  const [recentPlacement, setRecentPlacement] = useState<ZoneId | undefined>();
  const [voiceIndicator, dispatchVoice] = useReducer(reduceVoiceIndicator, INITIAL_INDICATOR);
  const micTest = new URLSearchParams(window.location.search).get('micTest') === '1';
  const demoEnabled = ['localhost', '127.0.0.1'].includes(window.location.hostname)
    && new URLSearchParams(window.location.search).get('workspaceDemo') === '1';
  function stopDemo() {
    setDemoActive(false);
    setDemoCounts(null);
    setFlashZone(undefined);
    setFlightBoxId('');
  }
  function startDemo() {
    setDemoCounts({ A: 0, B: 0, C: 0, RECHECK: 0, HOLD: 0 });
    setDemoIndex(0);
    setDemoPhase('RUNNING');
    setDemoActive(true);
  }

  useEffect(() => {
    if (!demoActive) return;
    const delay = DEMO_PHASE_MS[demoPhase];
    const timer = window.setTimeout(() => {
      const zone = DEMO_ZONES[demoIndex % DEMO_ZONES.length];
      if (demoPhase === 'RUNNING') {
        setDemoPhase('PICKING');
      } else if (demoPhase === 'PICKING') {
        const boxId = `demo-${demoIndex}`;
        setFlashZone(zone);
        setFlightBoxId(boxId);
        setDemoPhase('PLACING');
      } else if (demoPhase === 'PLACING') {
        setDemoCounts((counts) => ({ ...counts, [zone]: (counts?.[zone] ?? 0) + 1 }));
        setFlashZone(undefined);
        setFlightBoxId('');
        setDemoPhase('RETURNING');
      } else {
        setDemoIndex((index) => index + 1);
        setDemoPhase('RUNNING');
      }
    }, delay);
    return () => window.clearTimeout(timer);
  }, [demoActive, demoPhase, demoIndex]);

  useEffect(() => {
    if (boxMotion?.phase !== 'RELEASED' || boxMotion.session_id !== state?.session_id) return;
    const zone = getZone(boxMotion.zone);
    if (!zone || zone.name === 'TRUCK') return;
    setRecentPlacement(zone.name);
    const timer = window.setTimeout(() => setRecentPlacement(undefined), 1800);
    return () => window.clearTimeout(timer);
  }, [boxMotion, state?.session_id]);

  useEffect(() => {
    if (!lastResult || lastResult.session_id !== state?.session_id
      || !['PLACED', 'HELD'].includes(lastResult.outcome ?? '')) return;
    const zone = getZone(lastResult.zone);
    if (!zone || zone.name === 'TRUCK') return;
    setRecentPlacement(zone.name);
    const timer = window.setTimeout(() => setRecentPlacement(undefined), 1800);
    return () => window.clearTimeout(timer);
  }, [lastResult, state?.session_id]);
  function testMicColor(color: 'green' | 'yellow' | 'red') {
    dispatchVoice({ type: 'RESET' });
    if (color === 'green') return;
    const id = crypto.randomUUID();
    dispatchVoice({ type: 'VOICE_EVENT', signal: { phase: 'WAKE_DETECTED', event_id: `${id}-wake`, utterance_id: id } });
    if (color === 'red') {
      dispatchVoice({ type: 'VOICE_EVENT', signal: { phase: 'RECOGNITION_FAILED', event_id: `${id}-fail`, utterance_id: id } });
    }
  }

  useEffect(() => {
    if (!voiceConnected) dispatchVoice({ type: 'RESET' });
  }, [voiceConnected]);

  // 호출어 감지/성공/실패는 음성 노드에서 온 제안 SSE 이벤트로만 갱신한다.
  useEffect(() => {
    if (voiceSignal) {
      dispatchVoice({ type: 'VOICE_EVENT', signal: voiceSignal });
    }
  }, [voiceSignal]);

  // 별도의 응답이 없다면 안내만 표시한다. ROS voice_listener를 중단하지 않는다.
  useEffect(() => {
    if (voiceIndicator.color !== 'yellow') {
      return;
    }
    const activeId = voiceIndicator.activeUtteranceId;
    const timeout = window.setTimeout(() => {
      dispatchVoice({ type: 'UI_TIMEOUT', utteranceId: activeId });
    }, VOICE_COMMAND_TIMEOUT_MS);
    return () => window.clearTimeout(timeout);
  }, [voiceIndicator.color, voiceIndicator.activeUtteranceId]);

  useEffect(() => {
    if (voiceIndicator.color !== 'red') return;
    const activeId = voiceIndicator.activeUtteranceId;
    const timer = window.setTimeout(() => {
      dispatchVoice({ type: 'UI_RECOVER', utteranceId: activeId });
    }, VOICE_FAILURE_DISPLAY_MS);
    return () => window.clearTimeout(timer);
  }, [voiceIndicator.color, voiceIndicator.activeUtteranceId]);

  const rawState = demoActive ? demoPhase : isStateFresh ? (state?.state ?? 'UNKNOWN') : 'UNKNOWN';
  // SortState.track_id는 좌표가 아니다. 위치 스트림 승인 전 LIVE 박스를 추정 생성하지 않는다.
  const previewBox = demoActive && rawState === 'RUNNING';
  const grasped = !demoActive && boxMotion?.phase === 'GRASPED'
    && boxMotion.session_id === state?.session_id && Boolean(state?.session_id);
  const illustrationPhase: IllustrationPhase = demoActive ? demoPhase
    : recentPlacement ? 'PLACING' : grasped ? 'CARRYING' : rawState === 'PICKING' ? 'PICKING' : 'RUNNING';
  const illustrationZone = demoActive ? flashZone : recentPlacement;
  const observedBox = demoActive ? null : boxTracks.find((track) => track.position_valid && track.position_base);
  const belt = getBeltLayout(observedBox?.position_base ? observedBox.position_base.y * 1000 : undefined);
  const beltCenterX = belt.leftX + belt.lengthPx / 2;
  const carriedTop = grasped && robotPose && VERIFIED_BOX_OFFSET
    ? boxTopFromTcp(robotPose, VERIFIED_BOX_OFFSET) : null;
  const placementZone = demoActive && flightBoxId ? getZone(flashZone) : undefined;
  // sort_manager 는 reset_zone 을 PAUSED 에서만 받는다 (voss_msgs.md Command).
  const resetZoneEnabled = controlEnabled && !demoActive && rawState === 'PAUSED';
  const robotCenter = toScreen(ROBOT_BASE_MM.x, ROBOT_BASE_MM.y);
  const voiceWidgetLeft = `${((belt.leftX - WORKSPACE_VIEWBOX_LEFT) / WORKSPACE_VIEWBOX_WIDTH) * 100}%`;
  const voiceWidgetTop = `${((robotCenter.y - WORKSPACE_VIEWBOX_TOP) / WORKSPACE_VIEWBOX_HEIGHT) * 100}%`;
  const targetCenter = placementZone ? toScreen(placementZone.xMm, placementZone.yMm) : null;
  if (targetCenter && placementZone?.name === 'C') targetCenter.x += SECTOR_C_EDGE_OFFSET_PX;
  const packageStartX = DEMO_PICKUP_POINT.x;
  const packageStartY = DEMO_PICKUP_POINT.y;
  const demoBoxStartX = belt.leftX + belt.activeBeltInsetPx + 8;
  const demoTravelPx = Math.max(0, packageStartX - BOX_WIDTH / 2 - demoBoxStartX);
  const packageMotion = targetCenter ? {
    '--drop-dx': `${targetCenter.x - packageStartX}px`,
    '--drop-dy': `${targetCenter.y - packageStartY}px`,
  } as CSSProperties : undefined;

  return (
    <section className="voss-ws" aria-label="VOSS Sorting Workspace 2D">
      {micTest && <div className="voss-ws__mic-test">
        <span>마이크 로고 테스트</span>
        <button type="button" onClick={() => testMicColor('green')}>초록 · 대기</button>
        <button type="button" onClick={() => testMicColor('yellow')}>노랑 · 듣는 중</button>
        <button type="button" onClick={() => testMicColor('red')}>빨강 · 실패</button>
      </div>}
      <header className="voss-ws__header" style={headerAlignment}>
        <div>
          <h2>VOSS Sorting Workspace</h2>
        </div>
        <div className="voss-ws__header-right">
          {demoEnabled ? <button type="button" className="voss-ws__demo-button" onClick={demoActive ? stopDemo : startDemo}>
            {demoActive ? 'DEMO MODE 종료' : 'DEMO MODE 시작'}
          </button> : null}
          {demoActive || isDemo ? <span className="voss-ws__status">
            {demoActive ? 'DEMO / MOCK DATA' : 'DEMO'}
          </span> : null}
        </div>
      </header>
      <div className="voss-ws__canvas">
        <svg viewBox={`${WORKSPACE_VIEWBOX_LEFT} ${WORKSPACE_VIEWBOX_TOP} ${WORKSPACE_VIEWBOX_WIDTH} ${WORKSPACE_VIEWBOX_HEIGHT}`} role="img" aria-label="로봇 베이스 기준 실제 X/Y 위치에 배치된 TRUCK, A, B, C, RECHECK, HOLD, 컨베이어 평면도" preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="vossWsGrid" width="52" height="52" patternUnits="userSpaceOnUse">
            <path d="M 52 0 L 0 0 0 52" fill="none" stroke="#19384c" strokeWidth="1" opacity=".40" />
          </pattern>
        </defs>
        <rect width="1550" height="1035" rx="20" fill="#0b1928" />
        <rect width="1550" height="1035" rx="20" fill="url(#vossWsGrid)" />
        {/* 제어 패널에서 mm의 동일 축척을 사용한다. 실제 벨트 외곽 좌표는 미계측이다. */}
        {ZONES.map((zone) => (
          <Tray key={zone.name} zone={zone} count={demoActive ? demoCounts?.[zone.name] : zoneCounts?.[zone.name]} zoneName={zoneNames[zone.name]}
            onReset={onResetZone && !demoActive ? () => confirmResetZone(zone.name, zoneCounts?.[zone.name], onResetZone) : undefined}
            resetEnabled={resetZoneEnabled}
            resetReason={!controlEnabled ? '공용 PC 로컬 · MQTT 연결 중에만' : rawState !== 'PAUSED' ? '정지(PAUSED) 상태에서만 비울 수 있습니다' : ''} />
        ))}
        {/* 벨트 외곽 실측값은 없으므로 LIVE 중심선만 현재 관측 박스의 Y에 맞춘다. */}
        <g>
          <rect
            x={belt.leftX}
            y={belt.centerY - belt.widthPx / 2}
            width={belt.lengthPx}
            height={belt.widthPx}
            rx="17"
            className="voss-ws__belt"
          />
          {Array.from({ length: 20 }, (_, index) => {
            const pitch = belt.lengthPx / 20;
            const tickX = belt.leftX + pitch * index + pitch / 2;
            return (
              <path
                key={index}
                d={`M ${tickX} ${belt.centerY - belt.widthPx / 2 + 11} v ${belt.widthPx - 22}`}
                className="voss-ws__belt-line"
              />
            );
          })}
        </g>
        {!demoActive && boxTracks.map((track) => {
          if (grasped && track.track_id === boxMotion?.track_id) return null;
          if (!track.position_base) return null;
          const point = toScreen(track.position_base.x * 1000, track.position_base.y * 1000);
          return <g key={track.track_id} className="voss-ws__tracked-box" style={{ transform: `translate(${point.x}px, ${point.y}px)` }}>
            <rect x={-BOX_WIDTH / 2} y={-BOX_HEIGHT / 2} width={BOX_WIDTH} height={BOX_HEIGHT} rx="7" />
            <title>{`비전 트랙 ${track.track_id}, 베이스 좌표 ${track.position_base.x}, ${track.position_base.y}, ${track.position_base.z} m`}</title>
          </g>;
        })}
        {carriedTop ? (() => {
          const point = toScreen(carriedTop.x * 1000, carriedTop.y * 1000);
          return <g className="voss-ws__tracked-box" style={{ transform: `translate(${point.x}px, ${point.y}px)` }}>
            <rect x={-BOX_WIDTH / 2} y={-BOX_HEIGHT / 2} width={BOX_WIDTH} height={BOX_HEIGHT} rx="7" />
            <title>{`파지 확인 ${boxMotion?.box_id}; 검증된 TCP→박스 오프셋 적용`}</title>
          </g>;
        })() : null}
        <Robot phase={illustrationPhase} zone={illustrationZone}
          picking={demoActive && rawState === 'PICKING'}
          pose={demoActive ? null : robotPose} poseFresh={isPoseFresh} />
        {targetCenter && packageMotion ? (
          <rect
            key={flightBoxId}
            x={packageStartX - BOX_WIDTH / 2}
            y={packageStartY - BOX_HEIGHT / 2}
            width={BOX_WIDTH}
            height={BOX_HEIGHT}
            rx="6"
            className="voss-ws__drop-preview"
            style={packageMotion}
          >
            <title>PLACED 결과 수신 후 구역까지 이동을 재생한 개념 모션</title>
          </rect>
        ) : null}
        {previewBox ? (
            <rect
              key={demoIndex}
              x={demoBoxStartX}
              y={belt.centerY - BOX_HEIGHT / 2}
              width={BOX_WIDTH}
              height={BOX_HEIGHT}
              rx="7"
              className="voss-ws__belt-box voss-ws__belt-box--moving"
              style={{ '--belt-travel-px': `${demoTravelPx}px` } as CSSProperties}
            />
          ) : null}
        <text x={beltCenterX} y="920" textAnchor="middle" className="voss-ws__robot-title">CONVEYOR</text>
      </svg>
      <div className="voss-ws__voice-widget" style={{ left: voiceWidgetLeft, top: voiceWidgetTop }}>
        <button
          type="button"
          className={`voss-ws__voice-button voss-ws__voice-button--${voiceIndicator.color}`}
          aria-label={voiceIndicator.color === 'green' ? '음성 대기 표시, 초기화' : voiceIndicator.color === 'yellow' ? '호출어 인식됨, 명령 대기 중' : '음성 인식 실패, 눌러서 표시 초기화'}
          title={voiceIndicator.color === 'green' ? '음성 대기 표시' : voiceIndicator.color === 'yellow' ? '명령을 말씀하세요' : '눌러서 표시 초기화'}
          onClick={() => dispatchVoice({ type: 'RESET' })}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="12" rx="3" />
            <path d="M5.5 11v1a6.5 6.5 0 0 0 13 0v-1M12 18.5V22M8 22h8" />
          </svg>
        </button>
        {voiceIndicator.color === 'red' ? (
          <div className="voss-ws__voice-error" role="alert">
            {voiceIndicator.failure === 'timeout'
              ? '시간이 지났어요. 다시 “헬로 로키”라고 말해 주세요.'
              : '음성을 인식하지 못했어요. 다시 “헬로 로키”라고 말해 주세요.'}
            <span>3초 후 대기 상태로 돌아갑니다.</span>
          </div>
        ) : null}
      </div>
      </div>
    </section>
  );
}

/** 기존 Spring SSE/REST를 구독하는 독립 화면 어댑터. */
export function VossSortingWorkspaceLive() {
  const [state, setState] = useState<SortStateSnapshot | null>(null);
  const [robot, setRobot] = useState<RobotStateSnapshot | null>(null);
  const [boxTracks, setBoxTracks] = useState<Record<number, BoxTrackSample>>({});
  const [robotPose, setRobotPose] = useState<RobotPoseSample | null>(null);
  const [boxMotion, setBoxMotion] = useState<BoxMotionSample | null>(null);
  const [lastResult, setLastResult] = useState<SortResultSnapshot | null>(null);
  const [zoneCounts, setZoneCounts] = useState<ZoneCounts | null>(null);
  const [zoneNames, setZoneNames] = useState<Record<string, string>>({});
  const [lastStateAt, setLastStateAt] = useState(0);
  const [lastRobotAt, setLastRobotAt] = useState(0);
  const [dbSessionId, setDbSessionId] = useState('');
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let isMounted = true;

    async function refreshCounts(): Promise<void> {
      try {
        const response = await fetch('/api/sessions/current', { cache: 'no-store' });
        if (!response.ok) {
          if (isMounted) {
            setDbSessionId('');
            setZoneCounts(null);
          }
          return;
        }
        const data = await response.json() as SessionApiResponse;
        if (isMounted) {
          setDbSessionId(data.ok ? data.session_id ?? '' : '');
          setZoneCounts(data.ok ? normalizeCounts(data.available_by_zone ?? data.by_zone) : null);
        }
      } catch (error) {
        // DB/네트워크 일시 실패는 정상 개수 0으로 위장하지 않는다.
        console.error('[VOSS Workspace] 세션 집계 조회 실패', error);
        if (isMounted) {
          setDbSessionId('');
          setZoneCounts(null);
        }
      }
    }

    const source = new EventSource('/api/stream');
    source.addEventListener('zone_map', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as ZoneMap;
        if (isMounted && Array.isArray(data.entries)) {
          setZoneNames(Object.fromEntries(data.entries.map(entry => [entry.zone, entry.dong])));
        }
      } catch (error) { console.error('[VOSS Workspace] zone_map JSON 파싱 실패', error); }
    });
    source.addEventListener('state', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as SortStateSnapshot;
        if (!isMounted) {
          return;
        }
        setState(data);
        setLastStateAt(Date.now());
      } catch (error) {
        console.error('[VOSS Workspace] state JSON 파싱 실패', error);
      }
    });
    source.addEventListener('robot', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as RobotStateSnapshot;
        if (isMounted) {
          setRobot(data);
          setLastRobotAt(Date.now());
        }
      } catch (error) {
        console.error('[VOSS Workspace] robot JSON 파싱 실패', error);
      }
    });
    source.addEventListener('box_track', (event) => {
      try {
        const sample = parseBoxTrack(JSON.parse((event as MessageEvent).data));
        if (!isMounted || !sample) return;
        setBoxTracks((current) => {
          const next: Record<number, BoxTrackSample> = {};
          for (const track of Object.values(current)) {
            if (sample.receivedAt - track.receivedAt < TRACK_STALE_MS) next[track.track_id] = track;
          }
          if (sample.position_valid) next[sample.track_id] = sample;
          else delete next[sample.track_id];
          return next;
        });
      } catch (error) { console.error('[VOSS Workspace] box_track JSON 파싱 실패', error); }
    });
    source.addEventListener('robot_pose', (event) => {
      try {
        const sample = parseRobotPose(JSON.parse((event as MessageEvent).data));
        if (isMounted && sample) setRobotPose(sample);
      } catch (error) { console.error('[VOSS Workspace] robot_pose JSON 파싱 실패', error); }
    });
    source.addEventListener('box_motion', (event) => {
      try {
        const sample = parseBoxMotion(JSON.parse((event as MessageEvent).data));
        if (!isMounted || !sample) return;
        setBoxMotion((current) => {
          if (sample.phase === 'RELEASED' && (!current || current.phase !== 'GRASPED'
              || current.session_id !== sample.session_id || current.box_id !== sample.box_id
              || current.track_id !== sample.track_id)) return current;
          return sample;
        });
        if (sample.phase === 'RELEASED') {
          setBoxTracks((current) => {
            const next = { ...current };
            delete next[sample.track_id];
            return next;
          });
        }
      } catch (error) { console.error('[VOSS Workspace] box_motion JSON 파싱 실패', error); }
    });
    source.addEventListener('result', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as SortResultSnapshot;
        if (isMounted) {
          setLastResult(data);
          setBoxMotion((current) => current && current.box_id === data.box_id && current.session_id === data.session_id ? null : current);
          if (typeof data.track_id === 'number' && data.track_id >= 0) {
            setBoxTracks((current) => {
              const next = { ...current };
              delete next[data.track_id as number];
              return next;
            });
          }
          void refreshCounts();
        }
      } catch (error) {
        console.error('[VOSS Workspace] result JSON 파싱 실패', error);
      }
    });

    void refreshCounts();
    const statsTimer = window.setInterval(() => void refreshCounts(), STATS_REFRESH_MS);
    const freshnessTimer = window.setInterval(() => setNow(Date.now()), 500);
    return () => {
      isMounted = false;
      source.close();
      window.clearInterval(statsTimer);
      window.clearInterval(freshnessTimer);
    };
  }, []);

  // 서로 다른 세션의 DB 집계를 실제 로봇 세션 화면에 섞어 표시하지 않는다.
  const sessionMatches = Boolean(state?.session_id) && state?.session_id === dbSessionId;
  const matchingResult = lastResult?.session_id === state?.session_id ? lastResult : null;

  return (
    <VossSortingWorkspace
      state={state}
      robot={robot}
      boxTracks={Object.values(boxTracks).filter((track) => now - track.receivedAt < TRACK_STALE_MS)}
      robotPose={robotPose}
      boxMotion={boxMotion}
      isPoseFresh={robotPose !== null && now - robotPose.receivedAt < POSE_STALE_MS}
      lastResult={matchingResult}
      zoneCounts={sessionMatches ? zoneCounts : null}
      zoneNames={zoneNames}
      isRobotFresh={lastRobotAt > 0 && now - lastRobotAt < STATE_TIMEOUT_MS}
      isStateFresh={lastStateAt > 0 && now - lastStateAt < STATE_TIMEOUT_MS}
    />
  );
}
