import { test, expect } from '@playwright/test';
import path from 'node:path';

test('customer materials → genuine delegations → owner decisions → published delivery',async({browser})=>{
  const customer=await browser.newContext();const owner=await browser.newContext();
  const page=await customer.newPage();const boss=await owner.newPage();
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));boss.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await page.getByRole('button',{name:'建立本期订单'}).click();
  const dialog=page.getByRole('dialog',{name:'建立本期订单'});
  await dialog.getByLabel('工作室名称（与票据抬头一致）').fill('松石设计工作室');
  await dialog.getByLabel('账期').fill('2026-10');
  await dialog.getByRole('button',{name:'确认建档'}).click();
  await expect(dialog).toBeHidden();
  await page.locator('input[type=file]').first().setInputFiles([
    ...Array.from({length:6},(_,i)=>path.resolve(`../fixtures/mvp/receipt-0${i+1}.png`)),path.resolve('../fixtures/mvp/statement-live.csv')]);
  await page.getByRole('button',{name:'发送消息',exact:true}).click();
  await expect(page.getByRole('heading',{name:'4 笔匹配，3 项待核实事项'})).toBeVisible({timeout:60_000});
  await expect(page.getByText('差 ¥270.00',{exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading',{name:'4 笔匹配，3 项待核实事项'})).toBeVisible();
  const orderId=await page.evaluate(()=>localStorage.getItem('ledgercrew.order-id'));
  const privateResponse=await page.request.get('/api/v1/owner/dashboard',{headers:{'X-User-Id':'local-customer'}});
  expect(privateResponse.status()).toBe(403);
  const reports=await page.request.get(`/api/v1/orders/${orderId}/reports`,{headers:{'X-User-Id':'local-customer'}});
  expect(await reports.json()).toEqual([]);
  await boss.goto('/owner/');
  await expect(boss.getByText('每一项任务，都有真实派单与回执。')).toBeVisible();
  await boss.getByRole('button',{name:'数据核对 Agent · 已完成'}).click();
  await expect(boss.locator('#drawer').getByText(/reconcile_transactions/)).toBeVisible();
  await boss.getByRole('button',{name:'关闭',exact:true}).click();
  await boss.getByRole('button',{name:'异常与报告审批',exact:true}).click();
  for(let i=0;i<3;i++){
    const card=boss.locator('.live-exception').filter({has:boss.getByRole('button',{name:'保存这个决定'})}).first();
    await card.locator('textarea').fill('测试操作者：保留未解决事项，不核销差额。');
    await card.getByRole('button',{name:'保存这个决定'}).click();
    await expect(boss.locator('.live-exception').filter({has:boss.getByRole('button',{name:'保存这个决定'})})).toHaveCount(2-i);
  }
  await expect.poll(async()=>{
    const r=await boss.request.get(`/api/v1/owner/dashboard?order_id=${orderId}`,{headers:{'X-User-Id':'owner'}});return (await r.json()).report?.status;
  },{timeout:60_000}).toBe('draft');
  await boss.getByRole('button',{name:'关闭',exact:true}).click();
  await boss.getByRole('button',{name:'异常与报告审批',exact:true}).click();
  await boss.getByRole('button',{name:'查看草稿与审核'}).click();
  await boss.getByRole('button',{name:'审核、批准并发布'}).click();
  await expect(page.getByRole('button',{name:/账目核对报告 v1/})).toBeVisible({timeout:30_000});
  await page.getByRole('button',{name:/账目核对报告 v1/}).click();
  await expect(page.getByRole('dialog',{name:'已发布报告'}).getByText(/AMOUNT_MISMATCH/)).toBeVisible();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'下载可打印报告'}).click();
  expect((await download).suggestedFilename()).toContain('v1.html');
  expect(errors).toEqual([]);
  await customer.close();await owner.close();
});
