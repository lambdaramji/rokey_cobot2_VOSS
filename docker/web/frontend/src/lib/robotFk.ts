/** M0609 URDF base_link → tool0 FK. SI units; no React or ROS dependency.
 * Source: dsr_description2/urdf/m0609.urdf included by the existing RViz2 scene.
 * URDF origin RPY uses Rz * Ry * Rx; every movable joint rotates about local +Z.
 */
export type Vec3 = readonly [number, number, number];
type Mat3 = readonly [number, number, number, number, number, number, number, number, number];

export const JOINT_NAMES = ['joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6'] as const;
export const JOINT_LIMITS_RAD = [
  [-6.2832, 6.2832], [-6.2832, 6.2832], [-2.618, 2.618],
  [-6.2832, 6.2832], [-6.2832, 6.2832], [-6.2832, 6.2832],
] as const;
const JOINT_ORIGINS: readonly { xyz: Vec3; rpy: Vec3 }[] = [
  { xyz: [0, 0, 0.1345], rpy: [0, 0, 0] },
  { xyz: [0, 0.0062, 0], rpy: [0, -1.571, -1.571] },
  { xyz: [0.411, 0, 0], rpy: [0, 0, 1.571] },
  { xyz: [0, -0.368, 0], rpy: [1.571, 0, 0] },
  { xyz: [0, 0, 0], rpy: [-1.571, 0, 0] },
  { xyz: [0, -0.121, 0], rpy: [1.571, 0, 0] },
];

const IDENTITY: Mat3 = [1, 0, 0, 0, 1, 0, 0, 0, 1];
function multiply(a: Mat3, b: Mat3): Mat3 {
  return [
    a[0]*b[0]+a[1]*b[3]+a[2]*b[6], a[0]*b[1]+a[1]*b[4]+a[2]*b[7], a[0]*b[2]+a[1]*b[5]+a[2]*b[8],
    a[3]*b[0]+a[4]*b[3]+a[5]*b[6], a[3]*b[1]+a[4]*b[4]+a[5]*b[7], a[3]*b[2]+a[4]*b[5]+a[5]*b[8],
    a[6]*b[0]+a[7]*b[3]+a[8]*b[6], a[6]*b[1]+a[7]*b[4]+a[8]*b[7], a[6]*b[2]+a[7]*b[5]+a[8]*b[8],
  ];
}
function rotate(matrix: Mat3, vector: Vec3): Vec3 {
  return [
    matrix[0]*vector[0]+matrix[1]*vector[1]+matrix[2]*vector[2],
    matrix[3]*vector[0]+matrix[4]*vector[1]+matrix[5]*vector[2],
    matrix[6]*vector[0]+matrix[7]*vector[1]+matrix[8]*vector[2],
  ];
}
function rotationX(angle: number): Mat3 {
  const c = Math.cos(angle), s = Math.sin(angle);
  return [1, 0, 0, 0, c, -s, 0, s, c];
}
function rotationY(angle: number): Mat3 {
  const c = Math.cos(angle), s = Math.sin(angle);
  return [c, 0, s, 0, 1, 0, -s, 0, c];
}
function rotationZ(angle: number): Mat3 {
  const c = Math.cos(angle), s = Math.sin(angle);
  return [c, -s, 0, s, c, 0, 0, 0, 1];
}

export interface FkResult {
  /** base_link origin followed by J1…J6 origins, in metres. */
  joints: readonly Vec3[];
  /** URDF tool0 origin, in metres. This is not the finger-tip TCP. */
  tool0: Vec3;
}

export function m0609Fk(anglesRad: readonly number[]): FkResult {
  if (anglesRad.length !== 6 || !anglesRad.every(Number.isFinite)) {
    throw new RangeError('M0609 FK requires six finite joint angles in radians');
  }
  let position: Vec3 = [0, 0, 0];
  let orientation: Mat3 = IDENTITY;
  const joints: Vec3[] = [position];
  for (let i = 0; i < 6; i += 1) {
    const { xyz, rpy } = JOINT_ORIGINS[i];
    const translated = rotate(orientation, xyz);
    position = [position[0] + translated[0], position[1] + translated[1], position[2] + translated[2]];
    joints.push(position);
    orientation = multiply(orientation, multiply(rotationZ(rpy[2]), multiply(rotationY(rpy[1]), rotationX(rpy[0]))));
    orientation = multiply(orientation, rotationZ(anglesRad[i]));
  }
  return { joints, tool0: position };
}
