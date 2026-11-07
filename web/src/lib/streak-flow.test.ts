import test from 'node:test';
import assert from 'node:assert/strict';
import { streakStar, streakTrail } from './streak-flow.ts';

test('stars are deterministic and stay inside narrow and wide drawers', () => {
  for (const [width, height, count] of [[540,900,36],[880,1000,36],[360,680,20]]) {
    for (const seconds of [0,5,50,26,1000]) {
      for (let i=0;i<count;i++) {
        const star=streakStar(i,seconds,width,height);
        assert.deepEqual(star,streakStar(i,seconds,width,height));
        assert.ok(star.x>=0 && star.x<width);
        assert.ok(star.y>0 && star.y<height);
        assert.ok(star.opacity>=0 && star.opacity<=0.5);
        assert.ok(star.radius>=0.9 && star.radius<=2.6);
        assert.ok(star.depth>=0 && star.depth<=2);
      }
    }
  }
});
test('nearer star layers cross faster and read larger than far ones', () => {
  // depth 0 -> 26s per pass, depth 1 -> 19s, depth 2 -> 12s, so the near layer
  // covers more ground in the same time and carries the bigger radius.
  const far=streakStar(0,20,540,900);
  const mid=streakStar(1,20,540,900);
  const near=streakStar(2,20,540,900);
  assert.equal(far.depth,0);
  assert.equal(mid.depth,1);
  assert.equal(near.depth,2);
  assert.ok(far.radius<mid.radius && mid.radius<near.radius);
  const nearStep=Math.abs(streakStar(2,20.2,540,900).x-near.x);
  const farStep=Math.abs(streakStar(0,20.2,540,900).x-far.x);
  assert.ok(nearStep>farStep*2);
});
test('a star fades out at the wrap seam instead of jumping across the drawer', () => {
  const before=streakStar(0,25.9999,540,900);
  const after=streakStar(0,26.0001,540,900);
  assert.ok(before.opacity<0.01 && after.opacity<0.01);
});
test('a streak is idle for most of its period and bright at mid-pass', () => {
  // index 0 has an 8.5s period and only 0.2 of it is visible.
  assert.equal(streakTrail(0,4.25,540,900).alpha,0);
  assert.equal(streakTrail(0,5.95,540,900).alpha,0);
  const mid=streakTrail(0,0.85,540,900);
  assert.ok(mid.alpha>0.95);
  assert.ok(mid.length>0);
  assert.ok(Number.isFinite(mid.angle));
});
test('a streak tail stretches as it travels and dies out at the end of its pass', () => {
  const early=streakTrail(0,0.17,540,900);
  const late=streakTrail(0,1.53,540,900);
  assert.ok(late.length>early.length);
  assert.ok(early.alpha>0 && late.alpha>0);
  assert.ok(streakTrail(0,1.75,540,900).alpha<0.01);
  // The head stays inside the drawer vertically even as it runs off the sides.
  for (const t of [0,0.4,0.85,1.2,1.6]) {
    const s=streakTrail(0,t,540,900);
    if (s.alpha>0) assert.ok(s.y>0 && s.y<900);
  }
});
