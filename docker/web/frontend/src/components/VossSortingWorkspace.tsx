/**
 * VOSS Sorting Workspace: 기존 React HMI 안에 들어가는 읽기 전용 2D 시각화.
 * 입력: /api/stream(state/result/robot) 및 /api/sessions/current 집계.
 * 출력: 실제 구역 기준점과 DB 수량. DEMO에서만 가상 로봇·박스 애니메이션.
 * 관련: docs/interfaces/web_api.md #68, mqtt.md #20, voss_config.md.
 */
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  PIXELS_PER_MM,
  getBeltLayout,
  getTrayShellHorizontalLayout,
  ROBOT_BASE_MM,
  ZONES,
  getZone,
  toScreen,
} from '../lib/workspaceGeometry';
import type { ZoneId, ZoneLayout } from '../lib/workspaceGeometry';
import { JOINT_LIMITS_RAD, m0609Fk } from '../lib/robotFk';
import { INITIAL_INDICATOR, VOICE_COMMAND_TIMEOUT_MS, reduceVoiceIndicator } from '../lib/voiceIndicator';
import type { VoiceSignal } from '../lib/voiceIndicator';
import type { BoxMotionSample, BoxTrackSample, Point3, RobotJointSample, RobotPoseSample } from '../lib/workspacePosition';
import { boxTopFromTcp, parseBoxMotion, parseBoxTrack, parseRobotJoints, parseRobotPose, JOINT_STALE_MS, POSE_STALE_MS, TRACK_STALE_MS } from '../lib/workspacePosition';
import './VossSortingWorkspace.css';

const STATE_TIMEOUT_MS = 3000;
const STATS_REFRESH_MS = 2000;
const DEMO_ZONES = ['A', 'B', 'C', 'RECHECK', 'HOLD'] as const;
type DemoPhase = 'RUNNING' | 'PICKING' | 'PLACING' | 'RETURNING';
const DEMO_PHASE_MS: Record<DemoPhase, number> = { RUNNING: 5000, PICKING: 1000, PLACING: 3000, RETURNING: 1000 };
const BOX_WIDTH = 34;
const BOX_HEIGHT = 36;
// RViz2 robot_visualizer.py의 2026-10-12 실측 관절 자세. 아래 변형은 DEMO 전용이다.
const DEMO_OBSERVE_RAD = [-93.87, -13.24, 97.51, 0, 95.73, -185].map((angle) => angle * Math.PI / 180);
const DEMO_ZONE_J1_DEG: Record<(typeof DEMO_ZONES)[number], number> = {
  A: -38.87, B: -8.87, C: 21.13, RECHECK: -118.87, HOLD: -138.87,
};
function demoJoints(phase: DemoPhase, zone: ZoneId | undefined): readonly number[] {
  const values = [...DEMO_OBSERVE_RAD];
  if (phase === 'PICKING') {
    values[1] += 5 * Math.PI / 180;
    values[2] += 10 * Math.PI / 180;
  } else if (phase === 'PLACING' && zone && zone in DEMO_ZONE_J1_DEG) {
    values[0] = DEMO_ZONE_J1_DEG[zone as (typeof DEMO_ZONES)[number]] * Math.PI / 180;
    values[1] -= 18 * Math.PI / 180;
    values[2] -= 25 * Math.PI / 180;
  }
  return values.map((value, index) => Math.max(JOINT_LIMITS_RAD[index][0], Math.min(JOINT_LIMITS_RAD[index][1], value)));
}
const DEMO_PICKUP_TOOL0 = m0609Fk(demoJoints('PICKING', undefined)).tool0;
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
const WORKSPACE_VIEWBOX_HEIGHT = 1035;
const truckShell = getTrayShellHorizontalLayout(getZone('TRUCK')!);
const zoneCShell = getTrayShellHorizontalLayout(getZone('C')!);
const headerAlignment: CSSProperties = {
  marginLeft: `${((truckShell.leftX - WORKSPACE_VIEWBOX_LEFT) / WORKSPACE_VIEWBOX_WIDTH) * 100}%`,
  marginRight: `${((WORKSPACE_VIEWBOX_LEFT + WORKSPACE_VIEWBOX_WIDTH - zoneCShell.leftX - zoneCShell.widthPx) / WORKSPACE_VIEWBOX_WIDTH) * 100}%`,
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
  robotJoints?: RobotJointSample | null;
  boxMotion?: BoxMotionSample | null;
  isPoseFresh?: boolean;
  isJointsFresh?: boolean;
  lastResult: SortResultSnapshot | null;
  zoneCounts: ZoneCounts | null;
  isStateFresh: boolean;
  isRobotFresh?: boolean;
  isDemo?: boolean;
  voiceSignal?: VoiceSignal | null;
  voiceConnected?: boolean;
}

interface SessionApiResponse {
  ok?: boolean;
  session_id?: string;
  by_zone?: Record<string, number>;
}

interface TrayProps {
  zone: ZoneLayout;
  count: number | undefined;
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

/** 기존 적재함 윤곽 안에 현재 세션의 공식 처리 수량만 표시한다. */
function Tray({ zone, count }: TrayProps) {
  const { y } = toScreen(zone.xMm, zone.yMm);
  const pitchY = zone.pitchYMm * PIXELS_PER_MM;
  const cellHeight = zone.rows === 1 ? 44 : 49;
  const trayShell = getTrayShellHorizontalLayout(zone);
  const trayCenterX = trayShell.centerX;
  const outerHeight = (zone.rows - 1) * pitchY + cellHeight + 24;
  const countText = count === undefined ? '—' : `${count} BOX`;
  const color = TRAY_COLORS[zone.name];

  return (
    <g className="voss-ws__tray">
      <text x={trayCenterX} y={y - outerHeight / 2 - 22} textAnchor="middle" className="voss-ws__zone-title">
        {['A', 'B', 'C'].includes(zone.name) ? `TRUCK ${zone.name}` : zone.name}
      </text>
      <rect
        x={trayShell.leftX}
        y={y - outerHeight / 2}
        width={trayShell.widthPx}
        height={outerHeight}
        rx="16"
        className="voss-ws__tray-shell"
        stroke={color}
      />
      {zone.name !== 'TRUCK' ? (
        <text x={trayCenterX} y={y + 10} textAnchor="middle" className="voss-ws__zone-count">
          {countText}
        </text>
      ) : null}
    </g>
  );
}

/** URDF FK 결과만 팔 관절로 그린다. TCP는 별도 실측 스트림의 독립 마커다. */
function Robot({ joints, jointsFresh, pose, poseFresh, isDemo, picking }: {
  joints: readonly number[] | null; jointsFresh: boolean;
  pose?: RobotPoseSample | null; poseFresh: boolean; isDemo: boolean; picking: boolean;
}) {
  const [shown, setShown] = useState<readonly number[] | null>(null);
  const shownRef = useRef<readonly number[] | null>(null);
  const modeRef = useRef(isDemo);
  useEffect(() => {
    const modeChanged = modeRef.current !== isDemo;
    modeRef.current = isDemo;
    if (!joints) {
      shownRef.current = null;
      setShown(null);
      return;
    }
    if (!shownRef.current || modeChanged) {
      shownRef.current = joints;
      setShown(joints);
      return;
    }
    let frame = 0;
    let previous = performance.now();
    function step(now: number) {
      const current = shownRef.current;
      if (!current || !joints) return;
      const fraction = Math.min(1, (now - previous) / 140);
      previous = now;
      const next = current.map((angle, index) => angle + (joints[index] - angle) * fraction);
      shownRef.current = next;
      setShown(next);
      if (next.some((angle, index) => Math.abs(angle - joints[index]) > 0.0002)) {
        frame = requestAnimationFrame(step);
      }
    }
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [joints, isDemo]);

  const center = toScreen(ROBOT_BASE_MM.x, ROBOT_BASE_MM.y);
  const fk = shown ? m0609Fk(shown) : null;
  const points = fk?.joints.map(([x, y]) => toScreen(x * 1000, y * 1000));
  const tcp = pose ? toScreen(pose.position.x * 1000, pose.position.y * 1000) : null;
  const tool0 = points?.[6];
  return (
    <g>
      <circle cx={center.x} cy={center.y} r="57" className="voss-ws__robot-area" />
      <circle cx={center.x} cy={center.y} r="34" className="voss-ws__robot-base" />
      {points ? <g className={!isDemo && !jointsFresh ? 'voss-ws__robot-arm--stopped' : ''}>
        {points.slice(1).map((point, index) => <g key={index}>
          <line x1={points[index].x} y1={points[index].y + 8} x2={point.x} y2={point.y + 8} className="voss-ws__arm-shadow" />
          <line x1={points[index].x} y1={points[index].y} x2={point.x} y2={point.y} className="voss-ws__arm-link" />
          <circle cx={point.x} cy={point.y} r={index === 5 ? 7 : 9} className="voss-ws__arm-joint" />
        </g>)}
        {picking && tool0 ? <rect x={tool0.x - 12} y={tool0.y - 12} width="24" height="24" rx="4" className="voss-ws__grip-preview" /> : null}
      </g> : null}
      {tcp ? <circle cx={tcp.x} cy={tcp.y} r="5" className={`voss-ws__tcp-point ${poseFresh ? '' : 'voss-ws__tcp-point--stale'}`}>
        <title>실제 TCP 위치 — FK tool0와 별도 좌표</title>
      </circle> : null}
      <circle cx={center.x} cy={center.y} r="12" className="voss-ws__robot-hub" />
      <text x={center.x} y={center.y - 80} textAnchor="middle" className="voss-ws__robot-title">
        {fk ? `M0609 · ${isDemo ? 'DEMO FK' : jointsFresh ? '6축 FK' : '관절 갱신 중단'}` : 'M0609 · 관절 위치 미수신'}
      </text>
      {fk && tool0 ? <text x={tool0.x + 12} y={tool0.y - 12} className="voss-ws__robot-z">tool0 Z {Math.round(fk.tool0[2] * 1000)} mm</text> : null}
      {pose ? <text x={center.x} y={center.y + 103} textAnchor="middle" className="voss-ws__robot-z">TCP Z {Math.round(pose.position.z * 1000)} mm{poseFresh ? '' : ' · 갱신 중단'}</text> : null}
    </g>
  );
}

/** 순수 SVG이므로 브라우저에서만 표시되며 ROS나 MQTT 명령을 전송하지 않는다. */
export function VossSortingWorkspace({ state, robot, boxTracks = [], robotPose = null, robotJoints = null, boxMotion = null, isPoseFresh = false, isJointsFresh = false, zoneCounts, isStateFresh, isRobotFresh = false, isDemo = false, voiceSignal = null, voiceConnected = true }: WorkspaceViewData) {
  const [flashZone, setFlashZone] = useState<ZoneId | undefined>(undefined);
  const [flightBoxId, setFlightBoxId] = useState('');
  const [demoActive, setDemoActive] = useState(false);
  const [demoPhase, setDemoPhase] = useState<DemoPhase>('RUNNING');
  const [demoIndex, setDemoIndex] = useState(0);
  const [demoCounts, setDemoCounts] = useState<ZoneCounts | null>(null);
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

  const rawState = demoActive ? demoPhase : isStateFresh ? (state?.state ?? 'UNKNOWN') : 'UNKNOWN';
  // SortState.track_id는 좌표가 아니다. 위치 스트림 승인 전 LIVE 박스를 추정 생성하지 않는다.
  const previewBox = demoActive && rawState === 'RUNNING';
  const demoJointPosition = useMemo(() => demoActive ? demoJoints(demoPhase, flashZone) : null, [demoActive, demoPhase, flashZone]);
  const observedBox = demoActive ? null : boxTracks.find((track) => track.position_valid && track.position_base);
  const belt = getBeltLayout(observedBox?.position_base ? observedBox.position_base.y * 1000 : undefined);
  const beltCenterX = belt.leftX + belt.lengthPx / 2;
  const robotIsConnected = demoActive || (isRobotFresh && robot?.connected === true);
  const poseStatus = isPoseFresh ? 'TCP 실시간(근사)' : robotPose ? 'TCP 갱신 중단' : 'TCP 위치 미수신';
  const grasped = !demoActive && boxMotion?.phase === 'GRASPED'
    && boxMotion.session_id === state?.session_id && Boolean(state?.session_id);
  const carriedTop = grasped && robotPose && VERIFIED_BOX_OFFSET
    ? boxTopFromTcp(robotPose, VERIFIED_BOX_OFFSET) : null;
  const jointsStatus = isJointsFresh ? '6축 관절 실시간' : robotJoints ? '관절 갱신 중단' : '관절 미수신';
  const caption = `${rawState} · ${robotIsConnected ? '로봇 연결' : '로봇 미확인'} · ${poseStatus} · ${jointsStatus}`;
  const placementZone = demoActive && flightBoxId ? getZone(flashZone) : undefined;
  const robotCenter = toScreen(ROBOT_BASE_MM.x, ROBOT_BASE_MM.y);
  const voiceWidgetLeft = `${((belt.leftX - WORKSPACE_VIEWBOX_LEFT) / WORKSPACE_VIEWBOX_WIDTH) * 100}%`;
  const voiceWidgetTop = `${(robotCenter.y / WORKSPACE_VIEWBOX_HEIGHT) * 100}%`;
  const targetCenter = placementZone ? toScreen(placementZone.xMm, placementZone.yMm) : null;
  const demoPickupPoint = toScreen(DEMO_PICKUP_TOOL0[0] * 1000, DEMO_PICKUP_TOOL0[1] * 1000);
  const packageStartX = demoPickupPoint.x;
  const packageStartY = demoPickupPoint.y;
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
          <span className={`voss-ws__status ${!demoActive && isStateFresh ? 'voss-ws__status--live' : ''}`}>
            {demoActive ? 'DEMO / MOCK DATA' : isDemo ? 'DEMO' : caption}
          </span>
        </div>
      </header>
      <div className="voss-ws__canvas">
        <svg viewBox={`${WORKSPACE_VIEWBOX_LEFT} 0 ${WORKSPACE_VIEWBOX_WIDTH} ${WORKSPACE_VIEWBOX_HEIGHT}`} role="img" aria-label="로봇 베이스 기준 실제 X/Y 위치에 배치된 TRUCK, A, B, C, RECHECK, HOLD, 컨베이어 평면도" preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="vossWsGrid" width="52" height="52" patternUnits="userSpaceOnUse">
            <path d="M 52 0 L 0 0 0 52" fill="none" stroke="#19384c" strokeWidth="1" opacity=".40" />
          </pattern>
        </defs>
        <rect width="1550" height="1035" rx="20" fill="#0b1928" />
        <rect width="1550" height="1035" rx="20" fill="url(#vossWsGrid)" />
        {/* 제어 패널에서 mm의 동일 축척을 사용한다. 실제 벨트 외곽 좌표는 미계측이다. */}
        {ZONES.map((zone) => (
          <Tray key={zone.name} zone={zone} count={demoActive ? demoCounts?.[zone.name] : zoneCounts?.[zone.name]} />
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
        <Robot joints={demoActive ? demoJointPosition : robotJoints?.position ?? null}
          jointsFresh={demoActive || isJointsFresh} isDemo={demoActive}
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
            <span>아이콘을 누르면 초록색으로 초기화됩니다.</span>
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
  const [robotJoints, setRobotJoints] = useState<RobotJointSample | null>(null);
  const [boxMotion, setBoxMotion] = useState<BoxMotionSample | null>(null);
  const [lastResult, setLastResult] = useState<SortResultSnapshot | null>(null);
  const [zoneCounts, setZoneCounts] = useState<ZoneCounts | null>(null);
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
          setZoneCounts(data.ok ? normalizeCounts(data.by_zone) : null);
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
    source.addEventListener('robot_joints', (event) => {
      try {
        const sample = parseRobotJoints(JSON.parse((event as MessageEvent).data));
        if (isMounted && sample) setRobotJoints(sample);
      } catch (error) { console.error('[VOSS Workspace] robot_joints JSON 파싱 실패', error); }
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
      robotJoints={robotJoints}
      boxMotion={boxMotion}
      isPoseFresh={robotPose !== null && now - robotPose.receivedAt < POSE_STALE_MS}
      isJointsFresh={robotJoints !== null && now - robotJoints.receivedAt < JOINT_STALE_MS}
      lastResult={matchingResult}
      zoneCounts={sessionMatches ? zoneCounts : null}
      isRobotFresh={lastRobotAt > 0 && now - lastRobotAt < STATE_TIMEOUT_MS}
      isStateFresh={lastStateAt > 0 && now - lastStateAt < STATE_TIMEOUT_MS}
    />
  );
}
