# 架构与端到端流程

LedgerCrew v0.1 后端原定 Python 3.11，使用 FastAPI、Pydantic 2、SQLAlchemy 2、SQLite 和 Alembic。当前合并的独立 AI 模块使项目包要求变为 Python 3.14，统一版本仍待确认。HTTP 路由只处理请求与响应；业务状态、校验和金额计算在服务层；仓储层负责查询；迁移负责表结构，应用启动不自动建表。

## 目录与边界

| 路径 | 职责 |
| --- | --- |
| `app/api/v1` | `/api/v1` 路由、认证依赖、响应转换 |
| `app/core` | 环境配置、身份抽象、统一异常 |
| `app/db`, `app/models` | 异步 Session、UTC 类型和关系模型 |
| `app/schemas` | 请求与响应 Pydantic Schema |
| `app/repositories` | 数据库读取与持久化查询 |
| `app/services` | 订单状态、文件、CSV、确定性对账、异常、审批、报告与导出 |
| `app/integrations/agents` | Agent 契约、网关 Protocol、开发测试 Fake |
| `app/agents` | 独立 MiMo 与 Microsoft Agent Framework 工作流；尚未适配后端网关 |
| `app/storage` | 存储接口及本地实现；原始文件只读保留 |
| `app/workers` | 未来工作流执行器适配接口 |
| `alembic/versions`, `tests` | 版本化迁移和自动化验证 |

## 业务链

客户创建工作室和模拟订单后上传图片、CSV 或 ZIP。ZIP 原包与每个条目独立登记，条目保留 `archive_file_id` 和 `archive_entry_path`，实际存储键由后端生成。CSV 导入保留原文件和每行原始 JSON；金额由 `Decimal` 转整数分。可信编排器使用 `AgentGateway` 调用五类 Agent。发票图片必须有最新 `material_review` 任务的 `ACCEPTED` 且 `is_invoice=true` 结果，才能创建识别任务或入库；`InvoiceRecord` 引用审核任务、识别任务和原始文件。Agent 本身不写原始数据或审批。

对账引擎使用工作室身份、规范化交易方、方向、整数分金额、三天日期窗口和双向唯一候选规则。每次执行创建新的批次、匹配与异常工单，保留历史。风险与报告 Agent 只提供结构化分析或文字；报告服务读取数据库中的确定性财务汇总，绑定批次和证据，创建递增版本。老板处理异常、审核并批准特定版本与内容哈希后才能发布。客户只可读取自己订单已发布的报告及相应 CSV 导出。

订单状态由 `order_state` 服务推进：`draft → awaiting_materials → ready_to_process → processing → awaiting_owner_review → approved → delivered`。材料退回或要求补充会进入 `awaiting_customer`，补充后回到 `processing`。修订可从已审批或已交付状态重进处理。Agent 任务状态、异常状态和报告状态各自独立存储；每次关键转换记录审计和订单事件。

## 安全与事务

开发环境以 `X-User-Id` 模拟身份；客户访问按工作室所有者隔离，老板有审核权限；生产环境禁用模拟身份，接入真实认证前受保护接口返回 503。文件校验扩展名、大小、真实内容及 SHA256；ZIP 另防路径穿越、绝对路径、符号链接、嵌套压缩包及压缩炸弹。文件下载经权限检查，API 不暴露实际存储键。原始与标准化数据分开保存。金额不使用浮点数；Agent 金额字符串再次经后端严格解析。外键、唯一约束和事务由 SQLite 与 SQLAlchemy 执行。

测试覆盖完整 Fake Agent 链、越权读取、未发布报告、材料审核门禁、输入错误、回滚、外键、迁移和各业务单元。此覆盖不等于真实 Agent 联调或生产认证验收。
