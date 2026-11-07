import { test, expect } from '@playwright/test';
import path from 'node:path';

async function registerCustomer(page: import('@playwright/test').Page) {
  await page.goto('/start/');
  await page.getByLabel('用户名',{exact:true}).fill('flow-'+Date.now());
  await page.getByLabel('设置密码',{exact:true}).fill('Flow-test-password');
  await page.getByLabel('确认密码',{exact:true}).fill('Flow-test-password');
  await page.getByRole('button',{name:'注册并开始免费体验',exact:true}).click();
  await expect(page).toHaveURL(/\/upload\/$/);
}

test('customer materials → genuine delegations → owner decisions → published delivery',async({browser})=>{
  const customer=await browser.newContext();const owner=await browser.newContext();
  const page=await customer.newPage();const boss=await owner.newPage();
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));boss.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await page.getByRole('link',{name:'开始清账',exact:true}).first().click();
  await expect(page).toHaveURL(/\/start\/$/);
  await registerCustomer(page);
  await page.getByRole('button',{name:'开始咨询'}).click();
  expect(await (await page.request.get('/api/v1/orders',{headers:{'X-User-Id':'local-customer'}})).json()).toEqual([]);
  await page.getByLabel('工作室名称',{exact:true}).fill('松石设计工作室');
  await page.getByLabel('账期',{exact:true}).fill('2026-10');
  await page.getByRole('button',{name:'确认服务资料'}).click();
  await expect(page.getByText('已确认',{exact:true})).toBeVisible();
  await page.locator('input[type=file]').first().setInputFiles(path.resolve('../fixtures/mvp/materials.zip'));
  const materials=page.getByRole('region',{name:'材料清单'});
  await expect(materials.getByText('statement.csv',{exact:true})).toBeVisible();
  await expect(materials.getByText('已收到的材料 · 8 份文件',{exact:true})).toBeVisible();
  await expect(page.locator('.composer .pending-files')).toHaveCount(0);
  await expect(page.getByRole('region',{name:'客服对话'}).getByText('materials.zip',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'发送接洽消息',exact:true})).toBeDisabled();
  await page.reload();
  await expect(materials.getByText('statement.csv',{exact:true})).toBeVisible();
  await expect(materials.getByRole('region',{name:'Agent 待办'})).toBeVisible();
  const offer=page.getByRole('region',{name:'服务确认卡'});
  await expect(offer).toBeVisible({timeout:60_000});
  expect(await (await page.request.get('/api/v1/orders',{headers:{'X-User-Id':'local-customer'}})).json()).toEqual([]);
  await page.reload();
  await expect(page.getByRole('region',{name:'服务确认卡'})).toBeVisible();
  const checkboxes=page.getByRole('region',{name:'服务确认卡'}).getByRole('checkbox');
  for(let i=0;i<await checkboxes.count();i++)await checkboxes.nth(i).check();
  await page.getByRole('button',{name:'确认创建订单',exact:true}).click();
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
  await expect(boss.getByRole('heading',{name:'LedgerCrew · 老板作战室',exact:true})).toBeVisible();
  await boss.getByRole('button',{name:'数据核对 Agent · 已完成'}).click();
  await boss.getByText('工具回执与输入来源',{exact:true}).click();
  await expect(boss.getByRole('dialog').getByText(/reconcile_transactions/)).toBeVisible();
  await boss.getByRole('button',{name:'关闭',exact:true}).click();
  await boss.getByRole('button',{name:'异常与报告审批',exact:true}).click();
  for(let i=0;i<3;i++){
    const card=boss.getByTestId('owner-exception').filter({has:boss.getByRole('button',{name:'保存这个决定'})}).first();
    await card.locator('textarea').fill('测试操作者：保留未解决事项，不核销差额。');
    await card.getByRole('button',{name:'保存这个决定'}).click();
    await expect(boss.getByTestId('owner-exception').filter({has:boss.getByRole('button',{name:'保存这个决定'})})).toHaveCount(2-i);
  }
  await expect.poll(async()=>{
    const r=await boss.request.get(`/api/v1/owner/dashboard?order_id=${orderId}`,{headers:{'X-User-Id':'owner'}});return (await r.json()).report?.status;
  },{timeout:60_000}).toBe('draft');
  await boss.getByRole('button',{name:'关闭',exact:true}).click();
  await boss.getByRole('button',{name:'异常与报告审批',exact:true}).click();
  await boss.getByRole('button',{name:'查看草稿与审核'}).click();
  await boss.getByLabel('审核／退回理由',{exact:true}).fill('已核验本版本证据，保留未解决事项。');
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

test('brand and preview use native customer and owner routes without legacy assets', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {name:'小账房', exact:true})).toBeVisible();
  await expect(page.locator('a[href="/start/"]')).toHaveCount(3);
  await expect(page.locator('a[href="/workspace/"]')).toHaveCount(0);
  await page.getByRole('link', {name:'演示体验', exact:true}).click();
  await expect(page).toHaveURL(/\/demo\/$/);
  await expect(page.getByRole('button', {name:'上传票据和流水', exact:true})).toBeVisible();
  await expect(page.locator('.demo-surface')).toHaveCount(1);
  await page.goto('/');
  await page.getByRole('link', {name:'老板控制台', exact:true}).click();
  await expect(page).toHaveURL(/\/owner\/$/);
  await expect(page.getByRole('navigation', {name:'老板中控导航'})).toBeVisible();
  await expect(page.locator('.warroom-room')).toHaveCount(4);
  await page.goto('/workspace/');
  await expect(page).toHaveURL(/\/owner\/$/);
  await page.goto('/workspace/index.html');
  await expect(page).toHaveURL(/\/owner\/$/);
  for (const asset of ['css/style.css','js/api.js','js/app.js']) {
    expect((await request.get(`/workspace/${asset}`)).status()).toBe(404);
  }
});

test('material-card uploads show failure and retry without using chat send',async({page})=>{
  await registerCustomer(page);
  await page.getByRole('button',{name:'新建咨询',exact:true}).click();
  const materials=page.getByRole('region',{name:'材料清单'});
  const start=materials.getByRole('button',{name:'开始对话',exact:true});
  await expect(start).toBeDisabled();
  let attempts=0;
  let release=()=>{};
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/v1/intakes/*/files',async route=>{
    if(route.request().method()!=='POST')return route.continue();
    attempts++;
    if(attempts===1)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'上传连接中断，请重试。'}})});
    await gate;
    await route.continue();
  });
  await page.locator('input[type=file]').first().setInputFiles(path.resolve('../fixtures/mvp/statement-live.csv'));
  await expect(materials.getByRole('alert')).toContainText('上传连接中断');
  await expect(materials.getByText('已收到的材料 · 0 份文件',{exact:true})).toBeVisible();
  await expect(start).toBeDisabled();
  await expect(page.locator('.composer .pending-files')).toHaveCount(0);
  await materials.getByRole('button',{name:'重试上传',exact:true}).click();
  await expect(materials.getByRole('status')).toContainText('正在上传');
  await expect(start).toBeDisabled();
  release();
  await expect(materials.getByText('已收到的材料 · 1 份文件',{exact:true})).toBeVisible();
  await expect(materials.getByRole('alert')).toHaveCount(0);
  await expect(materials.getByRole('region',{name:'Agent 待办'})).toBeVisible();
  expect(attempts).toBe(2);
  await page.reload();
  await expect(materials.getByText('已收到的材料 · 1 份文件',{exact:true})).toBeVisible();
  await expect(materials.getByText('statement-live.csv',{exact:true})).toHaveCount(1);
});

test('original column names are normalized automatically with visible Agent todos',async({page})=>{
  await registerCustomer(page);
  await page.getByRole('button',{name:'新建咨询',exact:true}).click();
  await page.getByLabel('工作室名称',{exact:true}).fill('原始流水验证工作室');
  await page.getByLabel('账期',{exact:true}).fill('2026-10');
  await page.getByRole('button',{name:'确认服务资料',exact:true}).click();
  await expect(page.getByText('已确认',{exact:true})).toBeVisible();
  const input=page.locator('input[type=file]').first();
  expect(await input.getAttribute('accept')).toBeNull();
  await input.setInputFiles({name:'银行导出.csv',mimeType:'text/csv',buffer:Buffer.from('交易日期,对方户名,收支,发生额\n2026/10/08,松石测试供应商,支出,1280.50\n','utf8')});
  const materials=page.getByRole('region',{name:'材料清单'});
  await expect(materials.getByText('银行导出_已整理.csv',{exact:true})).toBeVisible({timeout:60_000});
  await expect(page.getByRole('region',{name:'服务确认卡'})).toBeVisible();
  await expect(materials.getByRole('region',{name:'Agent 待办'})).toContainText('按实际列名整理原始流水');
  await expect(materials.getByText('原始材料（已保留）',{exact:true})).toBeVisible();
  await expect(page.getByText('下载 CSV 模板',{exact:true})).toHaveCount(0);
  await page.reload();
  await expect(materials.getByText('银行导出_已整理.csv',{exact:true})).toBeVisible();
});
