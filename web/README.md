# LedgerCrew · 统一前端入口

同一个 Next.js 项目提供品牌首页、真实客户页、真实老板端与历史前端。首页导航、页脚和旧页面顶部的项目入口均在当前窗口跳转。

| 地址 | 页面 | 数据边界 |
| --- | --- | --- |
| `/` | 账清品牌首页 | 品牌介绍与协作示意；开始清账进入 `/upload/` |
| `/upload/` | 真实客户资料提交与清账结果 | sunset 已有 FastAPI、SSE、Worker 接口 |
| `/owner/` | 真实老板作战室 | `HTML/owner/`，经后端白名单提供，包含异常与报告审批 |
| `/demo/` | 客户端交互演示 | 合成账目、本地材料选择、图表与 GSAP，不上传真实文件 |
| `/workspace/` | 旧版作战室、仪表盘、助手与设置 | `HTML/` 历史原型，保留其离线演示及原有可选接口契约 |

## 安装与运行

需要 Node.js 24+。在 `web/`：

```powershell
npm ci
npm run dev
```

访问 `http://127.0.0.1:3210/`。真实客户与老板端还需要启动 FastAPI（8000）和独立 Worker，见 [完整启动与联调说明](../docs/LIVE_INTEGRATION.md)。

Next.js 将 `/api` 与 `/owner` 同源代理到 FastAPI，后端地址由 `LEDGERCREW_API_ORIGIN` 指定，默认 `http://127.0.0.1:8000`。沿用 sunset 的服务端运行方式，不使用静态导出：

```powershell
npm run build
npx next start --hostname 127.0.0.1 --port 3210
```

客户开发身份默认为 `local-customer`，老板默认为 `owner`；后端执行数据隔离与角色校验。当前仍是本机开发身份机制，不代表已具备正式登录及公网试用的访问控制。

## HTML 页面整合

`HTML/` 是旧前端的源码，不复制修改成另一套 React 页面。`scripts/prepare-legacy.mjs` 在 dev、build、test:e2e 前自动准备忽略提交的 `public/workspace/`：顶层 HTML、css、js 原样保留，页面顶部附加「历史演示」和同站项目导航。设计备份、Mock 服务、预览截图不作为网站静态资源发布。

真实老板端继续由后端提供 `HTML/owner/`，和旧作战室各自保留数据契约，避免离线演示与真实审批混用。

## 品牌与客户演示

首页复用现有浅色设计变量，使用居中的「账清 / LedgerCrew」品牌字标；HeroVisual 为可替换的独立视觉。ParticleField 使用三条同向弧线与正文避让，离屏、后台暂停，减少动态效果时静止，无新增粒子依赖。

原客户演示完整保存在 `/demo/`：GSAP 消息、弹窗、筛选与图表动效，金额始终显示最终值；用户不看到模型思考过程。示例有效票据 10,540 元、流水 11,370 元，830 元总额差异由 270 元金额差异与 560 元缺票付款组成，重复票据不重复计入。

当前票据范围为 JPG/PNG 和 CSV。真实 CSV 使用服务端模板：`transaction_date,counterparty,direction,amount,description,external_id`，方向 IN/OUT。PDF、Excel 不在当前上传支持范围。

## 检查

```powershell
npm test
npm run typecheck
npm run build
npx playwright install chromium --only-shell
npm run test:e2e
```

`npm test` 包含账目与粒子轨迹测试。Playwright 使用临时数据库和独立测试服务验证首页跳转、客户提交、老板审批、报告交付及旧 HTML 页面；不调用真实模型，不修改本机业务数据。后端另需安装 `server` 的测试依赖。可用 `E2E_PYTHON` 指定后端 Python，`PLAYWRIGHT_BROWSERS_PATH` 指定浏览器缓存路径。

## 设计署名

本界面参考 [unslop](https://github.com/heydamir/unslop) 的设计工作流。作者 Damir Sokolovsky（[@heydamir](https://x.com/heydamir)），技能采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可。原始技能保存在 `D:\codex\unslop`。旧作战室设计与交互沿用 `HTML/` 和 `HTML/owner/` 各自的说明。
