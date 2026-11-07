# P2-0 前端 JSON Mock

每个 `<resource>.json` 有 `operation` 与五个场景：`success`、`empty`、`validation_error`、`forbidden`、`business_blocked`。场景包含 HTTP `status` 和可直接传给前端请求模拟器的 `body`；例如读取 `filing_tasks.json` 的 `success.body`。`empty.body` 对应同资源列表接口，不是详情接口的 200 空对象。`forbidden` 仅演示通用无权响应，不表示客户/老板对 P2 新动作的具体权限已确认；跨租户对象沿用 MVP 的 404 隐藏原则。

`REGION_TBD`、`ENTITY_TBD`、`FORM_TBD`、`example.invalid` 和候选规则均为**占位测试数据**，不代表实际支持地区、政策、税率或申报表。Mock 中的阻塞计算和草稿没有任何税额/字段，不应被展示为可申报成果。API 尚未实现；错误场景是目标契约。

使用 Python 3.11 环境从仓库根目录执行 `python -m contracts.build_examples` 可重新生成，成功响应会先经过 Pydantic 2 校验。OpenAPI 用 `python contracts/build_openapi.py` 重新导出；两者均为设计产物，不是运行服务。
