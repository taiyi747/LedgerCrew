# LedgerCrew · 账清社用户端

第一阶段 MVP 的客户聊天界面原型，供小型工作室上传票据与流水、咨询核对结果、查看异常依据和报告。仅包含客户侧，不包含老板工作台和第二阶段功能。

## 本地运行

使用 Node.js 22 或更高版本，在本目录安装依赖后启动：

```powershell
npm install
npm run dev
```

生产构建：

```powershell
npm run build
```

构建结果保存在 `out/`，可以由静态服务器托管。本地预览使用 `npm run dev`。

业务模块验证（Node.js 24 可直接运行）：

```powershell
node --experimental-strip-types --test src/lib/ledger.test.ts
```

## 原型边界

- 页面中的账目、材料和核对结果是明确标注的合成演示数据；前端不调用 MiMo，不执行 OCR，也不分析用户实际上传的票据。选择文件不代表完成上传或核对。
- 演示样例包含 4 笔核对一致、1 笔金额差异（票据 2,580 元、付款 2,850 元，差额 270 元）、1 张重复票据和 1 笔缺票流水。
- 有效票据总额 10,540 元，不重复计算重复件；流水总额 11,370 元。830 元的总额差额由 270 元金额差异和 560 元缺票流水构成，不能将两者混为一类。
- 材料选择限制为 JPG/PNG 最多 20 张（单张不超过 5 MiB）及 1 份 CSV；CSV 最多 200 行数据。首版不支持 PDF。客户端校验不能代替服务端文件验证。
- 用户只看到简短业务状态、最终结果及证据，不展示思考过程。正式集成时，必须由后端过滤模型推理、内部 Agent 日志、工具返回和未发布报告；仅在界面隐藏不构成数据隔离。
- 当前未接入订单 API、SSE、真实文件存储、会话鉴权或老板审批。页面出现的报告和下载均属于演示，不能作为真实财务核验结果。
- CSV 下载使用 UTF-8 BOM，对可能被表格软件识别成公式的文本做转义。

## 后续接线依据

以第一阶段 [公共协作约定](https://github.com/taiyi747/LedgerCrew/blob/main/docs/PLAN.md) 和 [前端任务](https://github.com/taiyi747/LedgerCrew/blob/main/docs/FRONTEND.md) 为准：Next.js App Router、TypeScript、Tailwind CSS；金额使用整数分；客户只可访问自己的订单和已发布报告。

待后端冻结实际字段后，对接 `/api/v1/orders`、`/orders/{id}/files`、`/orders/{id}/runs`、`/orders/{id}/events`（SSE）、`/orders/{id}/messages`、`/orders/{id}/report` 和 `/orders/{id}/report.csv`。仓库 `HTML/` 作战室的 `tasks` 与 WebSocket 是另一套契约，不作为该用户端的正式订单接口。

## 设计署名

本界面使用 [unslop](https://github.com/heydamir/unslop) 的设计工作流进行制作。unslop 作者为 Damir Sokolovsky（[@heydamir](https://x.com/heydamir)），其技能采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可。原始技能保存在 `D:\codex\unslop`。

## 第二轮界面精修

保留现有配色与三栏结构。聊天结果先展示单笔差额、票据与付款金额、凭证依据及补充说明入口；重复票据和缺少凭证单独列出，完整核对明细按需展开。删除侧栏装饰口号和主界面的技术标签，放大正文与材料名称。

保留 `gsap@3.15.1` 的消息、筛选和弹窗反馈，金额始终直接显示最终值。服务说明中可手动重播结果呈现。系统启用「减少动态效果」时使用静态终态；切换、关闭和组件卸载时清理动画。

## 图表回答

回答内嵌四项摘要、逐笔票据与付款金额柱状图、流水核对环形图。图表使用现有 React/SVG 和 GSAP，无新增依赖。柱状图点击交易打开凭证依据；缺少票据保留为空，不当成 0 元。环形图仅统计六条流水，重复票据另列，点击分段或图例打开对应状态明细。金额采用原始整数分数据，¥830 总额差异与 ¥270 单笔差额分别说明。桌面双图并排，手机上下排列，沿用现有配色。

图表首次进入聊天可视区域时自动播放 GSAP：柱形从基线逐项展开，环形分段绘制。顶部「重播图表」可再次播放。按可见性触发，避免用户滚动到图表之前动效就已播完；遵循系统减少动态效果设置，金额和笔数仍始终显示真实终值。

## 青蓝配色改版

保留原来的米白页面底色与浅灰绿侧栏，使用用户指定的 #4ED7F1、#6FE6FC、#A8F1FF 与 #FFFA8D 作为交互和数据颜色。青蓝用于主操作、导航选中及票据图形，淡黄提示待核实金额，正文保持深色对比。统一聊天答复卡片、摘要、差额卡片、材料列表、输入框和弹窗的间距、边界与圆角；桌面保留三栏，手机图表纵向排列。保留原有 GSAP 动效和重播按钮。

## 品牌首页与用户端入口

- `/`：账清品牌 Landing Page，包含产品介绍、能力卡片、三步流程与 CTA。
- `/upload/`：原客户聊天、材料选择和核对结果页面。迁移时保留原文件内容，上传校验、表单、示例数据与 GSAP 不变。
- 导航栏、Hero 与底部 CTA 均以 Next.js Link 在当前窗口跳转到 `/upload/`；原用户端 Logo 返回 `/`。
- `components/landing/hero-visual.tsx` 为独立静态视觉，可替换成图片、视频或动画；`landing-sections.tsx` 分别封装能力与流程，使用独立 CSS Module 避免影响用户端。
- 首页不加载 GSAP 或新增动效依赖。静态示意及服务方向不代表已接入真实 AI 服务；现有版本仍只支持本地 JPG、PNG 和 CSV。

## 品牌居中与微粒流

首屏以居中的「账清 / LedgerCrew」字标呈现品牌，原口号、介绍及 CTA 在下方，协作示意卡片继续向下衔接。新增独立 ParticleField Canvas，三条宽缓弧线同向运行，正文和按钮区域留空；主色为 #7AD5EE 与稍深的 #5EBBD2。手机减为 36 颗粒子、限制画布像素比，绘制上限约 30 fps；离屏、后台暂停，减少动态效果时保留静态画面。无新增依赖，用户端路由与功能不变。

微粒轨迹测试：`node --experimental-strip-types --test src/lib/particle-flow.test.ts`。
