# LedgerCrew 客户端与老板入口

真实客户入口使用 Next.js 聊天界面；老板作战室、仪表盘与审批通过 `/owner/` 提供。两个页面均使用真实业务 API 和 fetch SSE，无演示数据回退。

```powershell
npm ci
npm run dev
```

客户：`http://127.0.0.1:3210/`；老板：`http://127.0.0.1:3210/owner/`。另需启动 8000 端口的 FastAPI 和独立 Python Worker，完整配置及操作见 [联调说明](../docs/LIVE_INTEGRATION.md)。

Next.js 将 `/api` 和 `/owner` 同源代理到 FastAPI，后端地址可通过 `LEDGERCREW_API_ORIGIN` 配置。已取消静态导出，生产构建使用 `npm run build`，再通过 `npx next start --hostname 127.0.0.1 --port 3210` 运行，不能使用静态服务器托管 `out/`。

```powershell
npm test
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Node.js 24+；Playwright 使用临时数据库和独立测试服务验证双身份主流程，不调用真实模型、不修改本机业务数据。真实 MiMo 验证另见联调说明。

客户开发身份默认为 `local-customer`，老板默认为 `owner`；服务端执行数据隔离与角色校验。本轮只供本机开发，暂不包含正式登录和公网试用。业务 CSV 为 `transaction_date,counterparty,direction,amount,description,external_id`；金额元、方向 IN/OUT。模板从服务端下载。

## 设计署名

本界面使用 [unslop](https://github.com/heydamir/unslop) 的设计工作流进行制作。unslop 作者为 Damir Sokolovsky（[@heydamir](https://x.com/heydamir)），其技能采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可。原始技能保存在 `D:\codex\unslop`。
