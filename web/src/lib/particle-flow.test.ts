import test from 'node:test';
import assert from 'node:assert/strict';
import { particleFlowPoint } from './particle-flow.ts';

test('particle positions are deterministic and remain inside desktop and mobile fields', () => {
  for (const [width, height, count] of [[1180,760,84],[375,680,36]]) {
    for (const seconds of [0,5,50,109.9,110,1000]) {
      for (let i=0;i<count;i++) {
        const point=particleFlowPoint(i,seconds,width,height);
        assert.deepEqual(point,particleFlowPoint(i,seconds,width,height));
        assert.ok(point.x>=0 && point.x<width);
        assert.ok(point.y>=0 && point.y<height);
        assert.ok(point.opacity>=0 && point.opacity<=.4);
        assert.ok(point.radius>=.75 && point.radius<=1.47);
      }
    }
  }
});
test('every particle travels in the same horizontal direction with gentle vertical motion', () => {
  for(let i=0;i<84;i++) {
    const a=particleFlowPoint(i,20,1180,760);
    const b=particleFlowPoint(i,20.1,1180,760);
    if(b.x>a.x) assert.ok(Math.abs(b.x-a.x-1180*.1/110)<.00001);
    else assert.ok(a.opacity<.01 && b.opacity<.01);
    assert.ok(Math.abs(b.y-a.y)<1);
  }
});
test('a particle fades to zero at the wrap seam instead of popping between edges', () => {
  const before=particleFlowPoint(0,109.999,1180,760);
  const after=particleFlowPoint(0,110.001,1180,760);
  assert.ok(before.opacity<.0001 && after.opacity<.0001);
});
