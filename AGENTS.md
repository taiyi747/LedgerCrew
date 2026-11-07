# LedgerCrew 项目开发规范

本文件适用于整个仓库；第二阶段的业务状态以 [docs/P2_DECISIONS.md](docs/P2_DECISIONS.md) 为准。用户已确认的要求优先于旧计划或契约草案。禁止把 `pending` 或 `proposed` 当成正式业务规则。

## 文件操作

禁止批量删除文件或目录，不得使用 `del /s`、`rd /s`、`rmdir /s`、`Remove-Item -Recurse`、`rm -rf`。需要删除时一次只删除一个明确路径的文件；若需批量删除，停止并请用户手动处理。

## 第二阶段 Python 与依赖

- `server/` 后端固定 Python **3.11**；`server/pyproject.toml` 必须为 `requires-python = ">=3.11,<3.12"`，Ruff `target-version = "py311"`。不得用 3.12+ 专属语法或运行时 API。
- 所有后端第三方依赖须在 Python 3.11 可解析、安装和运行；锁文件与 CI 必须以 3.11 验证。测试只在 Python 3.11 执行；没有 3.11 环境时记录阻塞，不用其他版本替代测试结果。
- AI Agent 依赖如不能在 3.11 运行，隔离到独立服务或其他明确边界；不得改变 `server/` 的 Python 版本。仅凭包元数据不能宣称运行时已兼容，需在 3.11 实测。

## 第二阶段业务决策门禁

- 每次开发前检查 [docs/P2_DECISIONS.md](docs/P2_DECISIONS.md) 中相关 `decision_id`、Python 3.11 兼容性、现有数据库和 API，列出本次涉及的待确认事项。
- 只有 `current_status: confirmed` 且记录 `confirmed_decision`、`confirmation_date` 的决策可进入正式业务实现。未确认部分可以设计基础模型、通用 Pydantic Schema、接口扩展点、可配置规则结构、无政策依赖的基础设施及明确标注的 Mock。
- 在三人完成确认前，不确定首个地区、经营主体、纳税人身份、申报事项、平台及导出格式；不假设一个 Studio 只有一个税务主体；不添加申报任务的业务唯一约束；不决定历史税务身份适用规则、客户/老板审批权限、资料包发布/撤回/历史访问规则；不编造税率、优惠、申报字段或政策。
- 不将临时假设写成数据库不可逆设计，不将 Mock 当真实政策，不把待确认事项标为完成。依赖未确认规则时，暂停对应业务实现并输出待确认问题；其他不受影响的工作可继续。

## MVP 兼容

第二阶段在 MVP 上增量扩展，不随意重写 `Studio`、`Order`、`UploadedFile`、`AgentTask`、`AgentRun`、`WorkflowEvent`、`ReportVersion` 或现有权限体系。申报任务与 MVP 订单分开管理；原 API 保持兼容；数据库变化必须经 Alembic 迁移并验证旧数据升级。
