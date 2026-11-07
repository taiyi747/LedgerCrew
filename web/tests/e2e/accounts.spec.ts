import { test, expect } from '@playwright/test';

test('trial registration, errors, logout and login',async({page})=>{
  const username='account-'+Date.now(),password='Account-test-password';
  await page.goto('/upload/?source=direct');
  await expect(page).toHaveURL(/\/start\/\?next=/);
  await expect(page.getByRole('article',{name:'免费体验，已选中'})).toBeVisible();
  await expect(page.getByText('即将开放',{exact:true})).toHaveCount(2);
  await page.getByLabel('用户名',{exact:true}).fill(username);
  await page.getByLabel('设置密码',{exact:true}).fill(password);
  await page.getByLabel('确认密码',{exact:true}).fill('different');
  await page.getByRole('button',{name:'注册并开始免费体验',exact:true}).click();
  await expect(page.locator('form').getByRole('alert')).toHaveText('两次输入的密码不一致');
  await page.getByLabel('确认密码',{exact:true}).fill(password);
  await page.getByRole('button',{name:'注册并开始免费体验',exact:true}).click();
  await expect(page).toHaveURL(/\/upload\/\?source=direct$/);
  await expect(page.getByRole('button',{name:'退出登录',exact:true})).toBeVisible();
  await expect(page.getByRole('status').filter({hasText:'无需支付'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:/建立本期订单/}).last()).toBeVisible();
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  await expect(page).toHaveURL(/\/start\/$/);
  await page.getByRole('tab',{name:'注册账号'}).click();
  await page.getByLabel('用户名',{exact:true}).fill(username);
  await page.getByLabel('设置密码',{exact:true}).fill(password);
  await page.getByLabel('确认密码',{exact:true}).fill(password);
  await page.getByRole('button',{name:'注册并开始免费体验',exact:true}).click();
  await expect(page.locator('form').getByRole('alert')).toContainText('用户名已被使用');
  await page.getByRole('tab',{name:'登录账号'}).click();
  await page.getByLabel('密码',{exact:true}).fill('wrong');
  await page.getByRole('button',{name:'登录并继续体验',exact:true}).click();
  await expect(page.locator('form').getByRole('alert')).toContainText('用户名或密码不正确');
  await page.getByLabel('密码',{exact:true}).fill(password);
  await page.getByRole('button',{name:'登录并继续体验',exact:true}).click();
  await expect(page).toHaveURL(/\/upload\/$/);
});

test('account entry desktop and mobile layouts and safe return destination',async({page},testInfo)=>{
  for(const width of [1440,768,390,360]){
    await page.setViewportSize({width,height:900});
    await page.goto('/start/?next=https%3A%2F%2Fevil.invalid');
    await expect(page.getByRole('button',{name:'注册并开始免费体验',exact:true})).toBeEnabled();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    const plans=await page.getByRole('region',{name:/服务方案/}).boundingBox();
    const account=await page.getByRole('region',{name:'为你的账目，留一个位置。'}).boundingBox();
    expect(plans).not.toBeNull();expect(account).not.toBeNull();
    if(width<=700)expect(account!.y).toBeGreaterThan(plans!.y+plans!.height);
    else expect(account!.x).toBeGreaterThan(plans!.x);
    await page.screenshot({path:testInfo.outputPath(`account-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:390,height:844});
  await page.getByLabel('用户名',{exact:true}).fill('mobile-'+Date.now());
  await page.getByLabel('设置密码',{exact:true}).fill('mobile-password');
  await page.getByLabel('确认密码',{exact:true}).fill('mobile-password');
  await page.getByRole('button',{name:'注册并开始免费体验',exact:true}).click();
  await expect(page).toHaveURL(/\/upload\/$/);
  await expect(page.getByRole('button',{name:/建立本期订单/}).last()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
