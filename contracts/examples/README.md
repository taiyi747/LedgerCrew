# P2-0 前端 JSON Mock

每个 `<resource>.json` 有 `operation` 与五个场景：`success`、`empty`、`validation_error`、`forbidden`、`business_blocked`。场景包含 HTTP `status` 和可直接传给前端请求模拟器的 `body`；例如读取 `filing_tasks.json` 的 `success.body`。`empty.body` 对应同资源列表接口，不是详情接口的 200 空对象。`forbidden` 仅演示通用无权响应，不表示客户/老板对 P2 新动作的具体权限已确认；跨租户对象沿用 MVP 的 404 隐藏原则。

`REGION_TBD`、`ENTITY_TBD`、`FORM_TBD`、`example.invalid` 和候选规则均为**占位测试数据**，不代表实际支持地区、政策、税率或申报表。Mock 中的阻塞计算和草稿没有任何税额/字段，不应被展示为可申报成果。API 尚未实现；错误场景是目标契约。

`auth.json` 是 v0.2 认证接口（login/logout/me）的请求与响应示例（手工维护，不由 `build_examples` 生成），含认证失败、无效/过期状态和生产 503 场景。`credential` 为提供者定义的不透明认证状态，开发环境取值不代表任何生产机制；`POST /api/v1/auth/refresh` 仍是 `proposed`，未实现未挂载。详见 [API.md §5.1](../API.md)。

`synthetic_policy_rule_import.json` 和 `synthetic_form_template_import.json` 是 BE2-10-05 通用 JSON 预检的 **synthetic fixture**，不属于上述前端 HTTP Mock，也不由 `build_examples` 生成。其虚构来源、地区、主体、事项、字段与参数均不能作为官方政策或可申报模板；正式导入仍未实现。详见 [导入测试报告](../../docs/BE2_10_05_IMPORT_TEST.md)。

使用 Python 3.11 环境从仓库根目录执行 `python -m contracts.build_examples` 可重新生成，成功响应会先经过 Pydantic 2 校验。OpenAPI 用 `python contracts/build_openapi.py` 重新导出；两者均为设计产物，不是运行服务。
