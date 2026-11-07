# 生产改造前代码审计（2026-11-07）

## 实测基线与范围

- 仓库实际位于 `LedgerCrew/`；后端固定 Python 3.11，FastAPI、SQLAlchemy async、SQLite、Alembic、Microsoft Agent Framework、MiMo；前端含独立 `web/` 与旧 `HTML/` 演示页。
- Python 3.11.9 在可运行的执行环境中执行 `python -m pytest -q --basetemp=.pytest_audit_unsandboxed`：**209 passed，79.37 秒**。受限执行环境的最小 `asyncio.run(asyncio.sleep(0))` 会挂起，故该环境内的未完成运行不算测试结果。
- 当前 OpenAPI 为 **32 条路径**。`ruff check app` 为 **108 条问题**，其中大部分是 FastAPI `Depends`/`File` 参数触发的 B008；CI 目前只检查 `app/agents` 等子目录。
- 审计读取了路由、服务、模型、迁移、测试、CI 和文档；本报告是修改前清单，不将历史文档的状态当作实测结果。

## 功能现状

| 领域 | 已完成 | 部分完成或未实现 |
| --- | --- | --- |
| 文件与导入 | 图片真实格式验证、CSV 基本校验、单文件和 ZIP 条目/压缩比/解压总量上限、路径穿越与符号链接检查；CSV 导入幂等及回滚有测试 | 多次请求累计容量、存储写入失败清理、孤儿文件回收、API/SSE 限流未完成 |
| 订单与租户 | Studio 所有者、订单→Studio→用户的权限链，文件/报告按订单校验，状态转换与审计事件 | `owner_user_id` 可空；无正式用户与租户成员表；`is_simulated` 恒真、价格可空；无支付订单与回调 |
| Agent 与报告 | Agent 任务幂等键、持久化状态/检查点/审计；MiMo 独立工作流有真实调用、超时/有限重试/用量记录；报告版本、人工审批、发布和下载 | 后端网关与真实工作流未联调；运行中任务崩溃恢复、取消与超时状态、模型结果人工纠错统计不完整；`publish()` 直接将订单变成 `delivered` |
| 认证与权限 | 开发/测试令牌登录接口、服务端解析凭据、生产环境安全关闭；MVP owner/customer 权限检查 | 开发环境仍可直接使用 `X-User-Id`；生产用户/密码哈希、持久会话、Cookie、CSRF、失败限制与账号审计未实现 |
| 运维与工程 | Alembic 0001–0008、SQLite 快照脚本及备份文档、209 项测试、Python 3.11 CI | `/health` 仅静态 `ok`，无 readiness/Worker 心跳；CI Ruff 未覆盖整个 app，未做迁移漂移检查；部分文档仍描述旧状态 |
| 前端 | `web/` 有独立 CSV 处理页面与测试；后端 API 可独立使用 | `HTML/js/api.js` 对不同契约 `/overview`、`/tasks` 自动回退 Mock，尚非真实后端业务界面 |

## 关键风险与最小改造依赖

1. **身份可伪造（开发配置）**：`core/security.py` 的 `get_current_principal` 在无 Authorization 时信任 `X-User-Id`，`services/access.py` 只按此身份比较 Studio 所有者。需先增加真实用户、角色、会话与租户授权，再调整依赖；保持现有开发测试兼容。生产目前 503，未暴露伪造身份。
2. **租户根未建模**：`models/records.py` 的 Studio 是当前事实租户根，Order、UploadedFile、AgentTask、报告与对账记录通过外键传递归属。应先定义用户→Studio 成员关系和统一访问查询，再扩展索引与跨租户测试；不能把历史空 owner 自动归属给任何用户。
3. **价格与支付缺位**：`services/order_service.py` 创建模拟订单且不定价；模型允许 `price_cents=NULL`。需先有业务价格/币种配置，再建 Payment Provider、支付意图/事件/对账表和状态机。用户已确认支付供应商与价格尚未确定，仅做 Sandbox，不声称真实扣款。
4. **报告发布过早交付**：`services/report_service.py:publish` 在审批通过后直接调用 `order_state.move(..., 'delivered')`；需要在明确交付条件后将发布与交付分离，并检查 `ReportVersion`/Order/导出调用链及前端返回兼容。
5. **任务不可自动恢复**：`services/agent_service.py` 有 queued/running/paused/succeeded/failed 与幂等键，但缺取消、租约过期与调度器；`workers/runner.py` 只有 Protocol。需新增有限重试、超时和恢复策略，迁移状态约束及事件历史。
6. **文件落盘与事务不原子**：`services/file_service.py:_save_record` 先写存储，后提交数据库；提交失败可能留孤儿文件。应增加单文件安全删除能力与补偿清理，并对原包与多条目检查累计容量。
7. **静态健康检查误报**：`main.py:/health` 不查数据库或 Worker；需保留 liveness 兼容，同时增加独立 readiness、脱敏依赖状态与必要运行指标。SQLite 单写入与本地文件存储不适合未经容量测试的多实例生产；升级数据库/队列需要单独迁移方案，当前不直接更换。

## 迁移与文件关系

- 认证/租户：新增 Alembic 迁移 → `models`、`core/security.py`、`services/access.py`、`api/v1/endpoints/auth.py` → 现有业务路由与前端认证流程 → 跨租户测试。
- 支付：新增支付表迁移 → Provider 接口与 Sandbox → 订单服务/状态机 → 回调 API、对账、测试；价格规则未确认前不得创建真实应付金额。
- Worker：任务状态约束迁移 → `agent_service.py` 与网关 → 调度/恢复入口、事件、测试。
- 健康与文件：配置和服务层 → `main.py`/上传路由 → 测试、部署和备份文档。
- CI/文档：`server/pyproject.toml`、`.github/workflows/agents.yml`、`docs/API.md`、README/BACKLOG/LIVE_INTEGRATION/FRONTEND/DELIVERY。不存在的目标文档需按真实现状新建，不复制历史结论。

## 待确认业务决定

- 用户本次明确选择**用户名/密码本地登录**，以及**支付仅 Sandbox**。这确定身份来源与支付环境，不等于已确定账号开通流程、平台管理员授予规则、价格/币种、真实支付商、退款审批规则。
- `docs/P2_DECISIONS.md` 的 DEC-002–012、DEC-014 尚含待确认的二阶段税务/Agent 边界，不将其中提案当作正式政策或审批规则。
