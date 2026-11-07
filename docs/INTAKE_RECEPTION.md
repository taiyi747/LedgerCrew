# 接洽、材料预检与确认下单

本轮在原 MVP 前增加独立接洽流程：**原始材料上传 → ReAct Agent 列待办、调用读取工具、观察结果并整理 → 客户确认服务 → 创建订单并自动排队 → 总管派工、审核与交付。**

## 运行与操作

沿用 Python 3.14、Next.js 和原 MiMo 配置。首次更新先执行 `uv sync --project server --extra dev` 安装锁定的文档读取依赖，再在 `server/` 执行 `python -m alembic upgrade head`（含 `0011_material_workspace`），再分别启动 FastAPI、`python -m app.live.worker` 和 `web/` 的 `npm run dev`。具体安装命令见 [本机联调说明](LIVE_INTEGRATION.md)。

- 客户入口：http://127.0.0.1:3210/upload/（首页点击“开始清账”）。点击“开始咨询”或“新建咨询”即可聊天、上传，尚未创建订单。
- “添加材料”、聊天附件和拖放都会立即上传，材料框显示上传中、失败与重试，无需再点击聊天发送。上传入口接收原始文件；未知类型也会保留，由 Agent 明确标记无法读取的待办。
- 上传成功后自动启动材料 Agent，前端展示实际待办的待处理、读取中、已完成和待确认状态。待办来自模型计划，完成状态只能由工具回执推进。刷新或 Worker 重启后保留成果和累计用量。
- ZIP 内部路径和文件、PDF 页、Excel 工作表、CSV 原始表头与行均由受控工具读取；客户不需要修改成平台 CSV 模板。字段映射由 Agent 提出，金额、日期、收支方向和内部流水由代码校验。
- 在资料卡确认已有／新工作室及账期。未确认资料时也能先上传和咨询，Agent 会把缺失信息列为待确认项；客户确认前不会创建订单。
- 客服将读取结论和补充问题保存到对话中。“开始对话／重新整理材料”可继续启动本版本检查。此时只整理服务输入，不创建正式票据记录或对账批次，也不保证资料完整或账目正确。
- 资料、文件、分类、替换或纳入选择变化后，旧预检和确认卡失效，需重新检查。
- 服务卡显示服务端套餐、¥19.90／单、模拟交易、有效材料、交付内容及待确认事项。客户须勾选警告，再点击“确认创建订单”。聊天文字不会触发下单。
- 确认后自动进入原订单页与总管流程，历史会话保留。旧订单仍能直接访问；“接洽与材料预检”可返回咨询。
- 老板在 `/owner/` 点击“咨询预检”，只读查看材料、结果和调用次数；客户材料选择与下单由客户本人完成。

正式处理需要已确认的工作室、账期和一份经过校验的内部流水；内部流水可以由 Agent 从原始 Excel、CSV 或文字 PDF 整理而来。没有票据可以知情下单，报告仍列出缺票；CSV 错误、账期外记录、未分类或未排除的无效文件及超限输入会阻止下单。没有真实支付、正式认证或税务申报。

## 接口与事务

前缀 `/api/v1`，OpenAPI `/docs` 提供请求及主要响应类型。

| 接口 | 行为 |
| --- | --- |
| `GET /services` | 服务代码 `monthly_records`、版本、价格和材料要求 |
| `POST/GET /intakes` | 创建／恢复客户接洽会话 |
| `GET/PATCH /intakes/{id}` | 快照、确认工作室与账期 |
| `POST /intakes/{id}/files` | 普通材料或混合 ZIP 上传 |
| `PATCH /intakes/{id}/files/{file_id}` | 分类、纳入／排除、替换关联 |
| `GET /intakes/{id}/files/{file_id}/download` | 有权限的原文件下载 |
| `GET/POST /intakes/{id}/messages` | 持久化会话与异步客服答复 |
| `POST /intakes/{id}/prechecks` | 本版本预检；已成功则复用，失败可显式重试 |
| `GET /intakes/{id}/events/stream` | 支持游标和 `Last-Event-ID` 的 SSE |
| `POST /intakes/{id}/confirm` | 校验最新确认卡，原子创建订单并入队 |
| `GET /owner/intakes` | 老板可见预检列表与失败原因 |

修改携带 `expected_revision`；确认另携带 `precheck_id`、`service_version`、`idempotency_key`、`acknowledged_warning_ids`。价格由服务端确定，客户端不能覆盖。一个接洽会话仅能关联一单，重复或并发确认返回同一结果。

确认事务中完成工作室、订单、套餐快照、文件元数据映射、CSV 导入、聊天历史和处理队列创建。原始文件不重复复制；ZIP 仅作来源追溯，排除项不进入有效处理输入。任一步失败全部回滚，不留下半成品订单、流水或运行。

迁移 `0009_intakes` 新增接洽、材料、会话、任务与事件表；`0010_precheck_usage` 取消预检总次数硬上限。订单保留原结构与接口，增补接洽来源、套餐快照和价格输出。

## Agent、任务恢复与用量

预检使用现有客服角色和真实 MiMo Flash。`inspect_intake_materials` 工具读取清单、确定性 CSV 检查并抽查图片；`save_precheck_result` 验证来源并保存结构化成果。模型不能创建订单、改价或调用正式对账。

**预检调用次数只作统计，不以 12 次作为失败条件。** 单次请求有 60 秒总时限，临时故障最多重试两次，结构纠正最多两次。连续重复同一检查、没有新成果也不保存时明确停止。手工重试保留用量和抽查缓存，只重置无进展标记。已经校验并保存的工具成果可以直接恢复，无需额外模型确认。

一个 Worker 的处理槽位按时间领取接洽预检或正式处理，问答槽位领取接洽或订单问答；共享模型 HTTP 并发上限二。租约 60 秒、心跳 5 秒。预检运行期间禁止修改输入，旧租约不能保存结果。接洽问答仍沿用每条六次请求的限制，正式订单沿用六十四次限制。

接洽问答排队期间若客户完成确认，迟到的答复会同步至关联订单会话。失败明确呈现，不使用固定样例回退。

## 验证

```powershell
# server/
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app/agents app/live app/intake scripts tests/agents tests/test_live.py tests/test_intake.py tests/live_support.py tests/browser_stack.py
.venv\Scripts\python.exe -m alembic check

# web/
npm test
npm run typecheck
npm run build
npm run test:e2e
```

端到端测试使用混合包 `fixtures/mvp/materials.zip`，内含六张合成票据及标准 CSV；在独立临时数据库和显式测试模型下，覆盖确认前零订单、ZIP 清单、预检、刷新、警告确认、转订单、四笔匹配、270 元差额、审批与下载。原有 107 项回归继续保留。

显式收费真实模型验证：

```powershell
# server/；先启动本机三个服务
.venv\Scripts\python.exe -X utf8 scripts/verify_intake_live.py --simulate-synthetic-review
```

脚本使用合成材料，明确模拟资料确认、警告确认和人工审批，分别记录接洽预检及正式处理的用量。`--intake-id` 可继续本人已有的合成接洽，`--precheck-only` 可只验证预检与确认。运行证据见 [预检记录](verification/intake-live.json) 和 [正式交付记录](verification/intake-delivery-live.json)。

当前预检无硬总次数限制的真实记录见 [独立预检验证](verification/intake-precheck-live.json)。`--preview-only` 可只验证预检而不创建订单。

## ReAct 材料工作区

`server/app/intake/workspace.py` 提供按咨询文件 ID 隔离的工具工作区。模型不能传入任意宿主机路径、读取别人的咨询或执行 shell。文档解析器运行在 Worker 进程中，此版没有容器级进程隔离。

| 工具能力 | 真实行为 |
| --- | --- |
| 制定待办 | 模型安排文件、任务类型与目标；重规划保留历史任务 |
| 查看压缩包 | 读取原 ZIP、校验路径和展开限制，返回包内文件与来源 |
| 读取文档 | CSV/TSV、Excel `.xlsx` 工作表、文字 PDF、Word `.docx`、文本/JSON |
| 读取图片 | 逐份判断用途与可读性，正式票据字段仍由订单阶段的票据 Agent 提取 |
| 整理流水 | 映射已读表头，或逐字引用文字 PDF 原始行；代码解析金额和日期，生成内部标准流水 |
| 准备 PDF 票据 | 将选定页渲染为图片，原 PDF 和页图的来源关系留存 |
| 检查与询问 | 基于实际工具成果列缺失项、异常和询问，不代替客户确认下单 |

未知、损坏或加密文件会成为待确认事项；不会编造读取结果。扫描 PDF 可转页图交给图片工具，但本版不把银行截图自动转换成流水。资源上限仍由服务端执行，限制体积、页数和交易行数。

`intake_files.derived_from_file_id` 与幂等 `derivation_key` 保存原文件和 Agent 成果关系；模型规划、真实工具回执、待办和用量持久化在本次任务的 artifacts 中。业务 SSE 推送待办变化，不公开模型私有推理。

真实验证使用合成材料，需显式执行：

```powershell
cd server
python scripts/verify_intake_workspace.py --run-live
```

可用 `--intake-id` 恢复同一验证咨询，累计请求量不清零。CI 使用注入测试网关，不调用真实 MiMo。
