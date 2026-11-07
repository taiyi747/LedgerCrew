import { test, expect } from '@playwright/test';

test('owner pages are native frontend routes and legacy console redirects',async({page,request})=>{
  const requests:string[]=[];page.on('request',r=>requests.push(r.url()));
  await page.goto('/owner/');
  await expect(page.getByRole('heading',{name:'LedgerCrew · 老板作战室',exact:true})).toBeVisible();
  await expect(page.getByRole('navigation',{name:'老板中控导航'})).toBeVisible();
  await page.getByRole('link',{name:'仪表盘',exact:true}).first().click();
  await expect(page).toHaveURL(/\/owner\/dashboard\/$/);
  await expect(page.getByRole('heading',{name:'经营仪表盘',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'咨询预检',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('heading',{name:'咨询与材料预检',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.goto('/owner/');
  await expect(page.locator('.warroom-room')).toHaveCount(4);
  await expect(page.locator('.warroom-desk')).toHaveCount(5);
  expect(requests.some(url=>url.includes('/console/'))).toBe(false);
  expect(requests.some(url=>url.includes(':8010'))).toBe(false);
  const legacy=await request.get('http://127.0.0.1:8010/console/',{maxRedirects:0});
  expect(legacy.status()).toBe(307);
  expect(legacy.headers().location).toBe('http://127.0.0.1:3211/owner/');
  await page.goto('/owner/dashboard.html');
  await expect(page).toHaveURL(/\/owner\/dashboard\/$/);
  await page.setViewportSize({width:390,height:844});
  await page.goto('/owner/');
  await expect(page.getByRole('navigation',{name:'老板中控导航'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
