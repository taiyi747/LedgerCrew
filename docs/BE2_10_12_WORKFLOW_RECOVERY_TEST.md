# BE2-10-12 审批失效与工作流恢复测试

## 结论与范围

**v0.2 审批失效与工作流恢复验收：BLOCKED。** 当前仓库没有 `FilingTask`、`TaxReturnDraft`、`TaxCalculation`、`FilingPackage`、申报审批记录（候选 `filing_review_actions`）的运行模型、迁移、Service 或路由；`contracts/API.md` 中的申报结构与操作仍是候选契约。MVP 的 `ReportVersion`/`ReportReviewAction` 审批与 Agent 检查点不能证明 P2 行为，不能声称申报草稿 V1/V2 的审批失效、资料包发布或恢复已获验证。

本次只新增合成数据回归测试 `server/tests/test_be2_10_12_workflow_recovery.py`（9 项），在 MVP 已有的 `ReportVersion`/`ReportReviewAction`、`AgentTask`/`AgentRun`、`WorkflowEvent`、`AuditLog` 与检查点机制上验证对应技术安全边界。没有修改业务代码、migration、数据库或决策状态；没有改写 `server/app/agents/` 的 Agent 内部工作流（只读复用其检查点、工作流构建与测试替身）；没有使用客户数据。

## 决策门禁

- `DEC-004`（申报事项与所属期）、`DEC-008`（任务粒度与唯一性）、`DEC-010`（分类确认与审批权限）、`DEC-011`（政策来源、规则与表单）、`DEC-012`（资料包发布与历史访问）、`DEC-013`（生产认证与角色）、`DEC-014`（Agent 与后端运行边界）均为 `pending`。
- 因此不设计 P2 审批角色、生产授权策略、草稿/资料包状态机或发布口径；相关场景仅按现有技术安全边界验证并标记 **BLOCKED**。

## 审批失效测试

对应场景 1–9，由 `test_v1_approval_never_transfers_to_v2_and_history_is_preserved` 等覆盖（MVP 以报告版本类比草稿版本）：

| 场景 | 实测结果 / 当前边界 | v0.2 验收 |
| --- | --- | --- |
| 1. 创建草稿 V1 | Agent 任务产出 `ReportVersion` v1（draft），内容哈希落库 | MVP 类比已验证；P2 草稿 **BLOCKED** |
| 2. V1 提交审核 | owner `submit-review` → in_review，订单转 `awaiting_owner_review` | 同上 |
| 3. 审批人批准 V1 | owner `approve` → approved，`ReportReviewAction` 记录 `report_version=1`+内容哈希 | 同上 |
| 4. 修改输入数据 | 新增流水并重算 → 新对账 batch（新数据版本） | 同上 |
| 5. 生成草稿 V2 | 新任务产出 v2，旧 v1 转 `superseded` 但行保留 | 同上 |
| 6. V1 审批不能自动批准 V2 | V1 发布被 `stale_report` 拒绝；V2 直接/送审后发布均 409；不存在指向 V2 的 V1 审批记录 | 同上 |
| 7. V2 必须重新审核 | V2 只能 `submit-review → approve → publish`，其审批记录绑定 v2 自身版本与哈希 | 同上 |
| 8. V1 历史继续保留 | v1 行、其审批记录（版本/哈希不变）与 `report.created/approved/published` 审计均保留 | 同上 |
| 9. V2 发布后不能被普通更新覆盖 | 发布后改内容再发布 → 409；送审 → 409；批准后改内容则发布被 `report_content_changed` 拦截 | 同上 |

另验证：任务创建后输入/证据变化时，旧任务成果不能生成草稿（`stale_report_source`），即使任务本身已成功完成——即成果生成绑定任务创建时的数据版本。

## 版本变化测试

| 变化类型 | 实测结果 / 当前边界 | v0.2 验收 |
| --- | --- | --- |
| 输入数据变化 | 新对账 batch 使已批准成果 `stale_report`，必须重算、重生成、重审 | MVP 已验证；P2 数据版本 **BLOCKED** |
| 账务分类变化 | `correct_classification` 决定后已批准 V1 不能发布（`stale_report`）；基于更正后数据的 V2 重新审核后可发布 | MVP 已验证；P2 分类版本 **BLOCKED**（DEC-010） |
| 证据材料变化 | 补充材料后已批准 V1 不能发布；任务创建后补充材料 → `stale_report_source` | MVP 已验证；P2 材料版本 **BLOCKED** |
| 政策规则版本变化 | 无 `PolicyRule` 模型/版本，无从构造 | **BLOCKED**（DEC-011） |
| 计算引擎版本变化 | 无 `TaxCalculation`/`calculation_version`，MVP 对账不是税务计算 | **BLOCKED**（DEC-011） |
| 表单模板版本变化 | 无 `FormTemplate`/`form_version`（仅不写库的 synthetic 预检） | **BLOCKED**（DEC-011） |
| 所属期变化 | 无 `FilingPeriod`；MVP 订单所属期创建后不可变，仅能以新对账 batch 表达数据版本变化 | **BLOCKED**（DEC-004/008） |

## 检查点恢复测试

覆盖 12 项恢复场景；后端侧由 `test_recovery_lifecycle_restart_repeated_recovery_and_failing_again`、`test_recovery_then_resume_finishes_delivery`、`test_waiting_states_and_blocked_status_cannot_be_bypassed` 覆盖，Agent 工作流侧复用既有 `tests/agents/test_workflow.py`（未改工作流内部）：

| # | 场景 | 覆盖与结果 |
| --- | --- | --- |
| 1 | 正常运行 | 任务 `queued → running → succeeded`，事件与审计逐条落库（通过） |
| 2 | 中途暂停 | `save_checkpoint` + `pause`，检查点随 `AgentRun.checkpoint_data` 持久化（通过） |
| 3 | 等待材料补充 | `material_review` 输出 `NEEDS_REUPLOAD` → 订单 `awaiting_customer`，不得直达 `delivered`（通过） |
| 4 | 等待人工审批 | 报告 in_review 期间订单 `awaiting_owner_review`，跨“重启”保留（通过） |
| 5 | Agent 执行失败 | `fail_task` 持久化失败原因；网关异常/非法输出失败另见既有 `test_stage5`（通过） |
| 6 | 服务异常退出 | 关闭引擎连接模拟进程退出；状态、检查点、事件已提交（通过） |
| 7 | 服务重启 | 全新连接读回 paused 状态与检查点内容（通过） |
| 8 | 从检查点恢复 | `resume_task` 续跑；Agent 工作流侧 `test_failed_node_retries_from_saved_checkpoint` 不重跑已完成节点（通过） |
| 9 | 重复恢复请求 | 二次 `resume` 被拒（`invalid_task_transition`）且 `attempt_count` 不变；工作流侧同一检查点重复恢复落到**同一待办**（`request_id` 确定性一致），旧检查点不能应答被替换待办（`test_old_checkpoint_cannot_resolve_replaced_review`）（通过） |
| 10 | 恢复后继续执行 | 恢复后任务完成，重复投递不再触发网关调用（通过） |
| 11 | 恢复后再次失败 | 恢复后再次失败被持久化，检查点机制不受影响（通过） |
| 12 | 恢复后完成交付 | 恢复后完成任务 → 生成成果 → 送审/批准/发布，客户可取已发布版本（通过） |

## 幂等测试

`test_repeated_submissions_consumption_and_publish_stay_idempotent` 等覆盖必验点：

| 必验点 | 实测结果 / 当前边界 | v0.2 验收 |
| --- | --- | --- |
| 相同请求重复提交不重复创建任务 | 同幂等键返回同一任务，仅 1 行 `AgentTask`、1 条 `agent.task.queued`；不同载荷同键 → `idempotency_conflict` | MVP 已验证；P2 任务唯一性 **BLOCKED**（DEC-008） |
| 相同事件不重复消费 | 事件追加+游标消费：游标推进后不重复返回；同一游标重复读取返回相同事件序列且不产生新事件行 | MVP 已验证；无 broker ack，P2 消费语义 **BLOCKED** |
| 成功计算不重复产生不一致记录 | 同一来源任务重复生成返回同一记录（`UNIQUE(source_task_id)`），仅一份内容哈希一致的成果 | MVP 报告生成已验证；P2 `TaxCalculation` 幂等 **BLOCKED** |
| 成功资料包生成不重复发布 | 二次发布 409，`published_at` 不变，`report.published` 审计仅 1 条 | MVP 报告发布已验证；P2 `FilingPackage` **BLOCKED**（DEC-012） |
| 已完成阶段不因恢复重复执行副作用 | succeeded 任务重复投递不再调用网关；检查点恢复不重跑已完成节点；重复恢复落到同一待办 | 已验证 |
| 重试不破坏原有审批记录 | 任务失败/重试前后 `ReportReviewAction` 行（动作、版本、哈希）完全不变 | 已验证 |

## 权限测试

`test_permission_boundaries_and_version_specific_approval`、`test_waiting_states_and_blocked_status_cannot_be_bypassed` 覆盖：

- **客户不能越权审批**：客户对 `submit-review`/`approve`/`publish` 均 403（通过）。
- **Agent 不能批准自己的成果**：Agent 任务产出停留在 draft 且无审批记录；以 agent 身份调用审批服务 → `forbidden`；Agent 输出通道只写 `output_data`，不写审批字段（通过）。
- **无权限用户不能发布**：跨租户读取 404（隐藏存在性），全局发布动作 403，与 [P2-0.5 审查](phase-2/P2-0.5-REVIEW.md) 要求的 401/403/404 语义分离一致（通过）。
- **审批绑定具体草稿版本**：审批记录绑定 `report_version`+内容哈希；篡改审批哈希 → `approval_missing`，篡改报告内容 → `report_content_changed`，旧版本不能被审核/发布（通过）。
- **阻塞状态不能绕过**：`awaiting_customer` 不得直达 `delivered`（`invalid_order_transition`）；抹掉未解决异常披露 → `unresolved_exception_undisclosed`；stale/旧版本/未审批均被拦截（通过）。
- **生产身份服务与审批角色：BLOCKED。** `DEC-010`/`DEC-013` 仍为 `pending`，不自行设计生产授权策略。当前 `X-User-Id` 为开发态合成身份，仅测试用；既有 `test_auth` 已确认生产环境认证不可用（production gate）。生产角色、多人审批与审批人资格待确认后补测。

## 阻塞事项

1. **BE2-08/09 未实现**：无 FilingTask 工作流/事件/检查点、TaxReturnDraft/TaxCalculation/FilingPackage 与申报审批记录；上述 P2 行为全部 **BLOCKED**，实现后须在合成 fixture 上重跑本文件全部场景并补写 P2 断言（草稿/计算/包版本失效、资料包发布幂等、FilingTask 恢复）。
2. **待确认决策**：DEC-004/008（所属期、任务唯一性）、DEC-010（审批权限）、DEC-011（规则/表单版本）、DEC-012（资料包发布/历史访问）、DEC-013（生产认证与角色）、DEC-014（Agent 运行边界）。
3. **环境事项（不阻塞交付）**：DSH 受限沙箱会把 pytest 创建临时目录的 `mode=0o700` 翻译成连当前用户都无法访问的权限项，导致 `tmp_path` 用例无法运行；已用官方诊断命令确认不属于可修复的权限缺失/外来权限项问题（未做任何权限更改，报告存 `/.acl-recovery/`）。本次测试以一次性不受限授权执行，`--basetemp` 仅为绕开旧的不可访问 `.pytest_tmp`。若后续会话遇到同类错误，可直接在不受限模式下运行测试。

## 执行记录

- 环境：Python 3.11.18、项目锁定依赖、每个用例独立临时 SQLite 数据库；未连接开发或客户数据库。
- 命令：`server/.venv/py311-env/Scripts/python.exe -B -m ruff check tests/test_be2_10_12_workflow_recovery.py`；结果通过。
- 命令：`server/.venv/py311-env/Scripts/python.exe -B -m pytest -q tests/test_be2_10_12_workflow_recovery.py --basetemp=.pytest_be21012_run`；**9 passed**。
- 全量后端回归：`server/.venv/py311-env/Scripts/python.exe -B -m pytest -q --basetemp=.pytest_be21012_run`；**209 passed**（含 MVP 既有全部用例与 `tests/agents` 工作流用例）。

## 未确认问题与后续门禁

1. DEC-010/013：审批角色、审批人资格、多人审批与生产身份服务接入；确认前权限测试中的生产授权部分保持 BLOCKED。
2. DEC-004/008/011/012：所属期与任务唯一性、规则/表单版本化、资料包发布与历史访问；决定 P2 审批失效与发布幂等的精确口径。
3. BE2-08/09 实现后：新增 P2 回归（草稿 V1/V2 审批隔离、六类版本失效、FilingTask 检查点恢复、资料包发布幂等），并保持本文件 MVP 用例通过；`server/app/agents/` 工作流内部仍不由后端改写。

本轮没有修改 migration、业务代码、数据库、决策状态或原有测试；所有验证仅针对合成数据。确认以上事项前，不把 MVP 报告审批行为提升为 P2 申报审批规则。
