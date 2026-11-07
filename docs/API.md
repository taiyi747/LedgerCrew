# 后端 API 状态与文档入口

更新日期：2026-11-07。实际可调用接口以运行应用的 `/openapi.json` 与 [MVP API 文档](../server/docs/api.md) 为准。本轮检查当前 FastAPI 有 **32 条路径**：原有 29 条 MVP 路径（含 `/health`）未移除，另有 3 条开发/测试认证路径 `/api/v1/auth/login`、`/api/v1/auth/logout`、`/api/v1/auth/me`。认证路由在生产环境由 503 `authentication_unavailable` 门禁阻断；不能据此宣称具备正式客户登录。当前运行应用没有 v0.2 申报、平台、政策、税务计算或资料包 API。

[第二阶段候选契约](../contracts/API.md)、[候选 OpenAPI](../contracts/openapi.json)、[Pydantic 线协议](../contracts/schemas.py) 和 [Mock](../contracts/examples/README.md) 包含 **35 个 `proposed` 操作**。它们未挂载，业务范围、权限、错误、版本与状态语义仍待 [决策登记表](P2_DECISIONS.md) 和 [P2-0.5 审查](phase-2/P2-0.5-REVIEW.md) 处理。前端可将 Mock 用于静态原型，不得向真实客户展示为已启用的申报能力。

API 变更验收要求：保留旧方法、路径、请求与响应，增量扩展 `/api/v1`；新增资源逐项落实 Studio 租户隔离、权限、幂等键、条件版本、审计与测试。未确认的支持范围不得进入正式计算或交付。BE2-01～09 未实现，因此本次没有发布新的申报 API 文档。
