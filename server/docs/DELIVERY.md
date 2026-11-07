# 第六阶段：异常处理与报告交付

本阶段实现客户补充、老板决定、报告版本审批、HTML 下载与 CSV 明细。报告正文来自未来的 `risk_delivery/report_draft` Agent 任务；后端不生成 Agent 文字，也不让 Agent 计算金额或审批报告。

## 开发身份与权限

开发和测试环境使用 `X-User-Id` 模拟身份。`DEV_OWNER_USER_IDS` 是明确配置的平台老板 ID 列表，默认 `["owner"]`；列表中的用户具有 `owner` 角色，其余为 `customer`。客户只能访问自己工作室的订单与异常，报告只可读取已发布版本。老板可查看工作台订单、处理异常并审核报告。生产环境仍拒绝模拟身份（受保护 API 返回 503），必须接入真实认证才能使用。

## 客户补充与异常决定

`POST /api/v1/exceptions/{exception_id}/supplements` 使用 multipart，可提交 `explanation` 文字、`file` 图片，或两者同时提交。证据仅接受验证通过的 JPG/PNG，沿用 `MAX_IMAGE_BYTES`；每次请求最多一个文件，可多次提交。补充记录和文件分别保存，不覆盖原始票据或流水。客户提交后，异常转为 `waiting_owner`。已 `resolved` 或 `accepted_unresolved` 的工单不再接收补充。

`GET /api/v1/exceptions/{exception_id}` 返回工单与当前状态；`GET /api/v1/exceptions/{exception_id}/supplements` 返回补充历史。老板通过 `POST /api/v1/exceptions/{exception_id}/decisions` 提交 JSON：

```json
{"decision":"request_supplement","reason":"请补充付款说明","target_version":1}
```

| 决定 | 新状态 | 说明 |
| --- | --- | --- |
| `resolve` | `resolved` | 确认处理完成 |
| `request_supplement` | `waiting_customer` | 等待客户补充 |
| `reanalyze` | `open` | 记录请求并创建待执行 `risk_analysis` 任务；不自动调用 Agent |
| `correct_classification` | `waiting_owner` | 另传 `classification_after`，保留修改前后值及理由；异常类型不变 |
| `accept_unresolved` | `accepted_unresolved` | 带说明接受未解决异常，报告仍披露 |

每次决定独立保存决定类型、老板 ID、理由、目标报告版本、时间；终态工单不再接收决定。`target_version` 记录决定所针对的报告版本号，可用于未来联调；当前允许该版本尚未创建。

## 报告草稿与审批

可信后端编排器通过 `AgentTaskCreate` 创建 `risk_delivery/report_draft` 任务，输入中提供后端批次的整数分汇总、匹配与异常引用。任务输出必须通过 `ReportDraftOutput` 结构校验。成功任务可调用：

```python
report = await report_service.create_from_agent_task(session, task.id)
```

该服务只取 Agent 的报告文字、未解决事项描述和已验证的证据引用；金额、匹配计数和异常快照均从数据库批次读取。证据引用必须对应当前订单的文件、票据、流水、匹配、异常或补充记录；后端还会自动加入本批次匹配与异常 ID。报告按订单递增版本号，正文及业务快照参与 SHA256 内容哈希。修订内容需要新的成功任务和新版本；旧版本原文不会被覆盖。

`POST /api/v1/reports/{report_id}/submit-review`：`draft → in_review`。`approve`：`in_review → approved`，记录老板、版本、内容哈希和时间。`reject`：`in_review → draft`，要求 JSON 理由。`publish`：`approved → published`，必须存在同一版本、同一哈希的老板审批。只有最新版本可进入审核或发布。新版本发布后，旧已发布版本标为 `superseded`，历史已发布版本仍可由所属客户读取。

报告保存异常状态、补充和决定的快照；异常或对账批次在草稿生成后变化时，审核或发布会返回 `stale_report`，需要生成新版本。未解决异常由后端自动加入 `unresolved_items` 和打印版异常表，包括 `accepted_unresolved`。净资金变动仍只由后端计算，且不等于会计利润或应税所得。

## 查询与导出

- `GET /api/v1/orders/{order_id}/reports`：老板可看所有版本；客户仅可看自己订单曾发布的版本。
- `GET /api/v1/reports/{report_id}`：结构化 JSON；未发布版本对客户返回 404。
- `GET /api/v1/reports/{report_id}/download`：可打印 HTML，正文会做 HTML 转义，当前不生成 PDF。
- `GET /api/v1/orders/{order_id}/exports/{export_type}.csv`：`export_type` 为 `invoices`、`transactions`、`matches`、`exceptions`。客户必须先有已发布报告；明细按最新已发布报告的批次和创建时间快照导出。老板读取当前数据。CSV 使用 UTF-8 BOM，文本单元格做公式注入防护，金额保持整数分。

客户补充、老板决定、报告创建/修订、审批、拒绝和发布均写入审计日志；关键操作同时写订单事件。

## 待确认事项

- 平台老板的生产认证与具体授权范围，需要接入真实身份服务；当前仅有开发/测试模拟角色。
- `target_version` 与未来异常复核流程的最终绑定规则，以及待执行 `risk_analysis` 任务如何由队友工作流调度。
- 客户补充后自动转 `waiting_owner`、旧已发布版本保持客户可读，当前作为 MVP 初始规则；产品验收时确认。
- 第四阶段重新运行对账会生成新批次和新异常工单；旧工单决定与补充保留作历史记录，但不会自动迁移到新工单。跨批次沿用处理结果的判定规则仍需确认。
- 报告发布已经构成版本级交付；订单状态与报告审批状态如何同步尚无明确规则，当前不会因报告发布而擅自跳转订单状态。
- 当前 HTML 为可打印交付格式；PDF、电子签署与外部交付通知留待后续阶段。
