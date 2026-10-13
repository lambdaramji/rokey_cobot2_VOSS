import test from 'node:test';
import assert from 'node:assert/strict';
import { m0609Fk, JOINT_LIMITS_RAD } from '../src/lib/robotFk.ts';

const radians = (degrees) => degrees.map((value) => value * Math.PI / 180);
const measured = radians([-93.87, -13.24, 97.51, 0, 95.73, -185]);

test('M0609 FK matches existing RViz2 expanded URDF calculation', () => {
  // Reference: scripts/rviz_scene/robot_visualizer.py fk(arm_chain(xacro scene), q).
  const expected = [-0.01216416680667842, -0.27181136677329376, 0.4502421228562064];
  const result = m0609Fk(measured);
  assert.equal(result.joints.length, 7);
  result.tool0.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9));
  const pick = [...measured];
  pick[1] += 5 * Math.PI / 180;
  pick[2] += 10 * Math.PI / 180;
  const pickExpected = [-0.012244031039654713, -0.2727320412485214, 0.3650323400398247];
  m0609Fk(pick).tool0.forEach((value, index) => assert.ok(Math.abs(value - pickExpected[index]) < 1e-9));
  assert.notDeepEqual(m0609Fk(pick).joints[3], result.joints[3]);
});

test('joint units, order, and DEMO ranges are explicit', () => {
  assert.throws(() => m0609Fk([0, 0, 0]));
  assert.throws(() => m0609Fk([0, 0, 0, 0, 0, Number.NaN]));
  measured.forEach((value, index) => assert.ok(value >= JOINT_LIMITS_RAD[index][0] && value <= JOINT_LIMITS_RAD[index][1]));
  assert.deepEqual(m0609Fk([0, 0, 0, 0, 0, 0]).joints[0], [0, 0, 0]);
  assert.equal(m0609Fk([0, 0, 0, 0, 0, 0]).joints[1][2], 0.1345);
});
