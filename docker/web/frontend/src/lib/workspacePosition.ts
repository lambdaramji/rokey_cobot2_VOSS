/** MQTT→SSE 위치 샘플은 원본 좌표와 시각을 보존한다. */
import { JOINT_NAMES } from './robotFk';

export interface Point3 { x: number; y: number; z: number }
export interface Quaternion { x: number; y: number; z: number; w: number }
export interface BoxTrackSample {
  track_id: number;
  stamp: string;
  position_valid: boolean;
  position_base: Point3 | null;
  receivedAt: number;
}
export interface RobotPoseSample {
  stamp: string;
  frame_id: 'base_link';
  position: Point3;
  orientation: Quaternion | null;
  receivedAt: number;
}
export interface RobotJointSample {
  stamp: string;
  frame_id: 'base_link';
  position: readonly number[];
  receivedAt: number;
}
export interface BoxMotionSample {
  session_id: string;
  box_id: string;
  track_id: number;
  phase: 'GRASPED' | 'RELEASED';
  stamp: string;
  zone: string;
  receivedAt: number;
}

export const TRACK_STALE_MS = 700;
export const POSE_STALE_MS = 500;
export const JOINT_STALE_MS = 500;

function point(value: unknown): Point3 | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  if (![candidate.x, candidate.y, candidate.z].every((axis) => typeof axis === 'number' && Number.isFinite(axis))) return null;
  return { x: candidate.x as number, y: candidate.y as number, z: candidate.z as number };
}

function quaternion(value: unknown): Quaternion | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  if (![candidate.x, candidate.y, candidate.z, candidate.w].every((axis) => typeof axis === 'number' && Number.isFinite(axis))) return null;
  const q = candidate as unknown as Quaternion;
  const length = Math.hypot(q.x, q.y, q.z, q.w);
  if (length < 0.99 || length > 1.01) return null;
  return { x: q.x / length, y: q.y / length, z: q.z / length, w: q.w / length };
}

function freshStamp(value: unknown, now: number): value is string {
  if (typeof value !== 'string') return false;
  const capturedAt = Date.parse(value);
  return Number.isFinite(capturedAt) && capturedAt <= now + 1000 && now - capturedAt <= 1000;
}

export function parseBoxTrack(value: unknown, now = Date.now()): BoxTrackSample | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (!Number.isInteger(data.track_id) || (data.track_id as number) < 0 || !freshStamp(data.stamp, now)) return null;
  if (typeof data.position_valid !== 'boolean') return null;
  const position = data.position_valid ? point(data.position_base) : null;
  if (data.position_valid && !position) return null;
  return { track_id: data.track_id as number, stamp: data.stamp as string,
    position_valid: data.position_valid, position_base: position, receivedAt: now };
}

export function parseRobotPose(value: unknown, now = Date.now()): RobotPoseSample | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (data.frame_id !== 'base_link' || !freshStamp(data.stamp, now)) return null;
  const position = point(data.position);
  if (!position) return null;
  return { stamp: data.stamp as string, frame_id: 'base_link', position,
    orientation: quaternion(data.orientation), receivedAt: now };
}

export function parseRobotJoints(value: unknown, now = Date.now()): RobotJointSample | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  const names = data.name;
  const positions = data.position;
  if (data.frame_id !== 'base_link' || !freshStamp(data.stamp, now) ||
      !Array.isArray(names) || !Array.isArray(positions) ||
      names.length !== 6 || positions.length !== 6 ||
      !JOINT_NAMES.every((name, index) => names[index] === name) ||
      !positions.every((angle) => typeof angle === 'number' && Number.isFinite(angle))) return null;
  return { stamp: data.stamp as string, frame_id: 'base_link',
    position: [...positions] as number[], receivedAt: now };
}

export function parseBoxMotion(value: unknown, now = Date.now()): BoxMotionSample | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (typeof data.session_id !== 'string' || !data.session_id ||
      typeof data.box_id !== 'string' || !data.box_id ||
      !Number.isInteger(data.track_id) || (data.track_id as number) < 0 ||
      (data.phase !== 'GRASPED' && data.phase !== 'RELEASED') ||
      !freshStamp(data.stamp, now) || typeof data.zone !== 'string') return null;
  if (data.phase === 'GRASPED' && data.zone !== '') return null;
  if (data.phase === 'RELEASED' && !['A', 'B', 'C', 'RECHECK', 'HOLD'].includes(data.zone)) return null;
  return { session_id: data.session_id, box_id: data.box_id, track_id: data.track_id as number,
    phase: data.phase, stamp: data.stamp as string, zone: data.zone, receivedAt: now };
}

/** 검증된 TCP 좌표계 오프셋(m)을 base_link로 회전시킨다. */
export function boxTopFromTcp(pose: RobotPoseSample, offset: Point3): Point3 | null {
  const q = pose.orientation;
  if (!q) return null;
  const { x, y, z, w } = q;
  const ox = (1 - 2 * (y * y + z * z)) * offset.x + 2 * (x * y - z * w) * offset.y + 2 * (x * z + y * w) * offset.z;
  const oy = 2 * (x * y + z * w) * offset.x + (1 - 2 * (x * x + z * z)) * offset.y + 2 * (y * z - x * w) * offset.z;
  const oz = 2 * (x * z - y * w) * offset.x + 2 * (y * z + x * w) * offset.y + (1 - 2 * (x * x + y * y)) * offset.z;
  return { x: pose.position.x + ox, y: pose.position.y + oy, z: pose.position.z + oz };
}
