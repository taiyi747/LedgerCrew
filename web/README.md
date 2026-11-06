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
