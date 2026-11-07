import { test, expect } from '@playwright/test';
import path from 'node:path';

test('intake skips image previews and confirms received quantities before formal processing',async({page,request,browser},testInfo)=>{
  const password='Review-fixture-2026';
  const account=await page.request.post('/api/v1/auth/register',{data:{username:'review-'+Date.now(),password,confirm_password:password}});
  expect(account.status()).toBe(201);
  await page.goto('/upload/');
  await page.getByRole('button',{name:'开始咨询',exact:true}).click();
  await page.getByLabel('工作室名称',{exact:true}).fill('松石设计工作室');
  await page.getByLabel('账期',{exact:true}).fill('2026-10');
  await page.getByRole('button',{name:'确认服务资料',exact:true}).click();
  await expect(page.getByText('已确认',{exact:true})).toBeVisible();
  await page.locator('input[type=file]').first().setInputFiles(path.resolve('../fixtures/mvp/materials.zip'));
  const offer=page.getByRole('region',{name:'服务确认卡'});
  await expect(offer).toBeVisible({timeout:60_000});
  await expect(offer).toContainText('本次处理材料：6 张图片、1 份流水文件');
  await expect(offer).not.toContainText('有效材料');
  await expect(offer).not.toContainText('receipt-01.png');
  await expect(page.getByRole('region',{name:'Agent 待办'})).toContainText('已跳过 6 项图片预读');
  await offer.scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('confirmation.png'),animations:'disabled'});
  const checkboxes=offer.getByRole('checkbox');
  for(let i=0;i<await checkboxes.count();i++)await checkboxes.nth(i).check();
  await offer.getByRole('button',{name:'确认并开始处理',exact:true}).click();
  await expect(page.getByRole('region',{name:'财务咨询聊天'})).toBeVisible();
  const orderId=await page.evaluate(()=>localStorage.getItem('ledgercrew.order-id'));
  expect(orderId).toBeTruthy();
  await expect.poll(async()=>{
    const response=await page.request.get(`/api/v1/orders/${orderId}/runs/current`);
    return (await response.json()).status;
  },{timeout:30_000}).toBe('paused');
  const snapshot=await request.get(`/api/v1/owner/dashboard?order_id=${orderId}`,{headers:{'X-User-Id':'owner'}});
  const state=await snapshot.json();
  if(state.exceptions?.length!==3){
    const traces=[];
    for(const role of ['invoice_processing','data_reconciliation']){
      const r=await request.get(`/api/v1/owner/agents/${role}/trace?order_id=${orderId}`,{headers:{'X-User-Id':'owner'}});
      const trace=await r.json();
      traces.push({role,errors:trace.tasks?.map((t:{status:string;error_message:string})=>({status:t.status,error:t.error_message}))});
    }
    throw new Error(JSON.stringify({run:state.run,exceptions:state.exceptions?.length,traces}));
  }
  const owner=await browser.newContext({baseURL:'http://127.0.0.1:3211'});
  const boss=await owner.newPage();
  await boss.goto('/owner/');
  await expect(boss.getByRole('heading',{name:'LedgerCrew · 老板作战室',exact:true})).toBeVisible();
  await boss.getByRole('button',{name:'异常与报告审批',exact:true}).click();
  const rows=boss.getByTestId('owner-exception');
  await expect(rows).toHaveCount(2);
  for(let i=0;i<2;i++){
    await rows.nth(i).click();
    await boss.getByLabel('处理理由',{exact:true}).fill('管理员审核：保留差额及未解决事项。');
    await boss.getByRole('button',{name:'保存这个决定',exact:true}).click();
    await expect(rows.nth(i)).toContainText('已处理');
  }
  await expect.poll(async()=>{
    const r=await request.get(`/api/v1/owner/dashboard?order_id=${orderId}`,{headers:{'X-User-Id':'owner'}});
    return (await r.json()).report?.status;
  },{timeout:60_000}).toBe('draft');
  await boss.getByRole('button',{name:'查看报告并发布给客户',exact:true}).click();
  await boss.getByLabel('审核／退回理由',{exact:true}).fill('确认当前报告，所有未解决事项保留披露。');
  await boss.getByRole('button',{name:'审核、批准并发布',exact:true}).click();
  await expect(page.getByRole('button',{name:/账目核对报告 v1/})).toBeVisible({timeout:30_000});
  const reports=await (await page.request.get(`/api/v1/orders/${orderId}/reports`)).json();
  expect(reports[0].unresolved_items.some((text:string)=>text.includes('MISSING_INVOICE'))).toBe(true);
  await owner.close();
});
