# LedgerCrew v0.2 后端验收清单

核对日期：2026-11-07。**结论：不具备 v0.2 上线条件。** 完成状态依据 [代码审查](BE2_10_AUDIT_REPORT.md)和 [实测结果](BE2_10_TEST_REPORT.md)，不是计划清单或 Mock。仅 DEC-001 Python 3.11 confirmed，DEC-002～014 pending。

| 项目 | 状态 | 验收证据或阻塞 |
| --- | --- | --- |
| [ ] BE2-01 商户与申报领域模型 | `not_implemented` | 无目标模型、迁移、服务、API 或测试；DEC-002～004/006～008 pending。 |
| [ ] BE2-02 平台数据与来源追溯 | `not_implemented` | 无 P2 文件、导入与平台记录；DEC-005/009 pending。 |
| [ ] BE2-03 结算与到账核对 | `not_implemented` | 无批次、分配或到账服务；DEC-009 pending。 |
| [ ] BE2-04 账务分类与修订 | `not_implemented` | 无建议、分录及确认流程；DEC-010 pending。 |
| [ ] BE2-05 政策与规则版本 | `not_implemented` | 无来源、规则、导入和审核；DEC-011 pending。 |
| [ ] BE2-06 确定性税务计算 | `not_implemented` | 无计算模型或服务；无已批准政策参数。 |
| [ ] BE2-07 申报表字段与草稿 | `not_implemented` | 无表单模板和草稿；DEC-011 pending。 |
| [ ] BE2-08 工作流与版本审批 | `not_implemented` | 无 FilingTask 工作流和版本审批；DEC-010/014 pending。 |
| [ ] BE2-09 资料包与交付 | `not_implemented` | 无 FilingPackage；DEC-012 pending。 |
| [ ] BE2-10 迁移、测试与上线回归 | `partially_completed` | MVP 迁移/备份与 121 项现有测试通过；v0.2 业务、迁移和核心测试均阻塞，全仓 Ruff 仍失败。 |

## 必要上线门槛

| 条件 | 当前状态 |
| --- | --- |
| 首发地区、身份、事项、平台与结算口径 confirmed | `blocked`：DEC-002～005/009 pending。 |
| Studio 关系、历史身份、任务粒度 confirmed | `blocked`：DEC-006～008 pending。 |
| 审批、政策/官方表单、资料包规则 confirmed | `blocked`：DEC-010～012 pending。 |
| 生产认证和 Agent 运行边界 confirmed 并联调 | `blocked`：DEC-013/014 pending。 |
| v0.2 模型、API、迁移、权限、审计、幂等均有实现和测试 | `not_implemented`。 |
| v0.2 数据可复算、规则/模板导入幂等、历史审批失效 | `not_implemented`。 |
| v0.2 空库/旧库升级、回退及备份恢复演练 | `blocked`：当前只有 MVP `0001`～`0008`。 |
| MVP 全量回归 | `completed`：本轮 Python 3.11 全量 121 项测试通过，其中包含旧 MVP 测试及新增安全测试。 |
| 全仓 Ruff、生产安全与真实客户上线门禁 | `blocked`：Ruff 119 项；生产认证 503 占位。 |

下一次验收应在 BE2-01～09 逐项真实完成、相关决策确认后重跑全部检查，补足 v0.2 专属测试与发布演练。本文件不把 MVP 测试的通过结果当成 v0.2 能力。
