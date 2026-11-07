# 老板作战室历史资产

本目录保留 `sunset@451c88a` 的原作战室、仪表盘和工位插画源码。

当前控制台已迁入 Next.js `/owner/`，布局、总管区、四个网格工作区及桌椅插画继续保留。`web/src/components/owner/desk-art.ts` 复用本目录的原 SVG；按钮、表单、选择器及审批抽屉采用 shadcn/ui。

FastAPI 不再提供本目录 HTML/CSS/JS。旧 `http://127.0.0.1:8000/console/` 会跳转到 `http://127.0.0.1:3210/owner/`；自定义跳转地址使用 `FRONTEND_ORIGIN`。真实订单、SSE、派单、轨迹、咨询预检和版本审批仍通过原业务 API 执行。
