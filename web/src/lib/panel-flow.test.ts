import test from 'node:test';
import assert from 'node:assert/strict';
import { panelRibbonOffset, panelRibbonWidth, panelSpark } from './panel-flow.ts';

test('panel sparks are deterministic and stay inside narrow and wide drawers', () => {
  for (const [width, height, count] of [[540,900,30],[880,1000,30],[360,680,18]]) {
    for (const seconds of [0,5,50,8.9,9,1000]) {
      for (let i=0;i<count;i++) {
        const spark=panelSpark(i,seconds,width,height);
        assert.deepEqual(spark,panelSpark(i,seconds,width,height));
        assert.ok(spark.x>0 && spark.x<width);
        assert.ok(spark.y>0 && spark.y<height);
        assert.ok(spark.opacity>=0 && spark.opacity<=0.45);
        assert.ok(spark.radius>=1.2 && spark.radius<=2.3);
      }
    }
  }
});
test('sparks rise up the drawer with only a gentle sideways sway', () => {
  const peak=panelSpark(0,4.5,540,900).opacity;
  assert.ok(peak>0.3);
  for(let i=0;i<30;i++) {
    const a=panelSpark(i,20,540,900);
    const b=panelSpark(i,20.1,540,900);
    if(b.y<a.y) assert.ok(Math.abs((a.y-b.y)-900*0.92*0.1/(9+(i%5)*2.2))<0.00001);
    // Wrapped past the seam: it has to be faint there or the jump reads as a pop.
    else assert.ok(a.opacity<peak*0.2 && b.opacity<peak*0.2);
    // Sway amplitude is 6% of the width over a full cycle, so a tenth of a
    // second can only move a spark a couple of pixels sideways.
    assert.ok(Math.abs(b.x-a.x)<3);
  }
});
test('a spark fades out at the wrap seam instead of jumping from top to bottom', () => {
  const period=9;
  const mid=panelSpark(0,period*0.5,540,900);
  const before=panelSpark(0,period*0.9999,540,900);
  const after=panelSpark(0,period*1.0001,540,900);
  assert.ok(mid.opacity>0.15);
  assert.ok(before.opacity<0.01 && after.opacity<0.01);
  assert.ok(before.opacity<mid.opacity*0.05 && after.opacity<mid.opacity*0.05);
});
test('ribbons stay near their own lane and never swing past the drawer', () => {
  for (const width of [360,540,880]) {
    for (const seconds of [0,5,50,1000]) {
      for (let i=0;i<4;i++) {
        const half=panelRibbonWidth(i,width)/2;
        for (const t of [0,0.25,0.5,0.75,1]) {
          const x=panelRibbonOffset(i,seconds,t,width);
          assert.ok(x>0 && x<width);
          assert.ok(x-half>-width*0.2 && x+half<width*1.2);
          assert.equal(x,panelRibbonOffset(i,seconds,t,width));
        }
      }
    }
  }
});
test('ribbon width is a small share of the drawer so the gaps stay open', () => {
  for (const width of [360,540,880]) {
    for (let i=0;i<4;i++) {
      const w=panelRibbonWidth(i,width);
      assert.ok(w>width*0.05 && w<width*0.14);
    }
  }
});
