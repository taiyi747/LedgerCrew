import test from 'node:test';
import assert from 'node:assert/strict';
import { warroomLinkAlpha, warroomNode } from './warroom-flow.ts';

test('backdrop nodes are deterministic and stay inside desktop and mobile fields', () => {
  for (const [width, height, count] of [[1600,1000,46],[375,680,26]]) {
    for (const seconds of [0,5,50,149,150,1000]) {
      for (let i=0;i<count;i++) {
        const node=warroomNode(i,seconds,width,height);
        assert.deepEqual(node,warroomNode(i,seconds,width,height));
        assert.ok(node.x>=0 && node.x<width);
        assert.ok(node.y>=0 && node.y<height);
        assert.ok(node.opacity>=0 && node.opacity<=0.42);
        assert.ok(node.radius>=1.1 && node.radius<=2.45);
      }
    }
  }
});
test('every node drifts the same way with only a gentle vertical sway', () => {
  for(let i=0;i<46;i++) {
    const a=warroomNode(i,20,1600,1000);
    const b=warroomNode(i,20.1,1600,1000);
    if(b.x>a.x) assert.ok(Math.abs(b.x-a.x-1600*0.1/(150+(i%4)*35))<0.00001);
    else assert.ok(a.opacity<0.01 && b.opacity<0.01);
    assert.ok(Math.abs(b.y-a.y)<1.2);
  }
});
test('a node fades to zero at the wrap seam instead of popping across the field', () => {
  const before=warroomNode(0,149.999,1600,1000);
  const after=warroomNode(0,150.001,1600,1000);
  assert.ok(before.opacity<0.0001 && after.opacity<0.0001);
});
test('links fade out with distance and vanish past the cutoff', () => {
  assert.equal(warroomLinkAlpha(0,0,0,132,132),0);
  assert.equal(warroomLinkAlpha(0,0,0,200,132),0);
  assert.equal(warroomLinkAlpha(0,0,0,0,132),1);
  assert.ok(warroomLinkAlpha(0,0,0,66,132)===0.5);
  assert.ok(warroomLinkAlpha(0,0,0,120,132)>0);
  assert.ok(warroomLinkAlpha(0,0,0,120,132)<warroomLinkAlpha(0,0,0,60,132));
});
