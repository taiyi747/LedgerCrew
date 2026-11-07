# LedgerCrew · 统一前端入口

品牌首页、客户接洽与老板控制台统一由 `web/` 的 Next.js App Router 提供，不依赖独立 HTML 原型或后端静态页面。

| 地址 | 页面 | 数据边界 |
| --- | --- | --- |
| `/` | 账清品牌首页 | 服务介绍，开始清账进入 `/upload/` |
| `/upload/` | 客户咨询、材料预检与订单交付 | 真实 API、SSE 和 Worker；确认服务后才创建订单 |
| `/owner/` | 老板作战室 | 真实总管派单、任务、异常和报告审批 |
| `/owner/dashboard/` | 经营仪表盘 | 真实业务统计 |
| `/demo/` | 客户端交互演示 | 合成账目与本地文件选择，不上传或分析真实文件 |
| `/workspace/` | 旧链接兼容入口 | 跳转至 `/owner/`，不再发布历史静态页面 |

## 安装与运行

需要 Node.js 24+。在 `web/`：

```powershell
npm ci
npm run dev
```

访问 `http://127.0.0.1:3210/`。客户与老板业务页面还需启动 FastAPI（8000）和独立 Worker，见 [完整启动与联调说明](../docs/LIVE_INTEGRATION.md)。

只有 `/api` 同源代理到 FastAPI，后端地址由 `LEDGERCREW_API_ORIGIN` 指定，默认 `http://127.0.0.1:8000`。生产运行：

```powershell
npm run build
npx next start --hostname 127.0.0.1 --port 3210
```

已取消静态导出，不能使用静态服务器托管 `out/`。客户开发身份默认为 `local-customer`，老板默认为 `owner`；后端执行数据隔离与角色校验。当前仍用于本机与受控演示，不代表正式登录已完成。

## 客户接单与老板控制台

客户可以先咨询或上传原始材料，上传后 ReAct 材料 Agent 自动列待办、读取文件并整理。支持的读取工具包含 ZIP、图片、PDF、Excel `.xlsx`、CSV/TSV、Word 和文本；未知类型明确留为待确认。客户无需套用 CSV 模板。只有确认服务卡后才创建订单，随后由总管委派专业 Agent，并保留异常处理、报告审核发布和下载闭环，详见 [接单说明](../docs/INTAKE_RECEPTION.md)。

老板控制台保留原作战室、总管区、四个网格工位区及 SVG 插画；按钮、表单和审批抽屉使用 shadcn/ui。旧 `/owner/dashboard.html` 跳转到 `/owner/dashboard/`，FastAPI `/console/` 也只跳转到前端。

Agent 整理的内部流水使用 `transaction_date,counterparty,direction,amount,description,external_id`，方向 IN/OUT；原始文件与派生成果保留关联，金额转换和最终导入由服务端验证。

## 品牌首页与独立演示

首页保留浅色品牌视觉、HeroVisual 和 ParticleField；首页、客户页、老板中控与演示页的样式分别隔离。ParticleField 在离屏、后台暂停，减少动态效果时静止。

`/demo/` 保留 GSAP 消息、弹窗、筛选与图表动效，并明确标注合成示例。示例有效票据 10,540 元、流水 11,370 元，830 元总额差异由 270 元金额差异与 560 元缺票付款组成，重复票据不重复计入。演示选择的文件只保存在当前页面内存中；真实服务请从 `/upload/` 开始。

## 检查

```powershell
npm test
npm run build
npm run typecheck
npm run test:e2e
```

Playwright 使用注入测试网关运行客户接洽至老板审批发布的闭环，另验证品牌首页、独立演示与原生老板路由；测试不会调用真实 MiMo。
