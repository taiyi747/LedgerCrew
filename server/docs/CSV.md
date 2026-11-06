# 资金流水 CSV 格式与导入

[下载标准模板](csv_template.csv)。文件编码须为 UTF-8，可包含 UTF-8 BOM。首行为表头，默认日期格式为严格的 `YYYY-MM-DD`。空文件、无数据行、重复或缺失必填表头会被整批拒绝。

| 标准字段 | 必填 | 格式 |
| --- | --- | --- |
| `transaction_date` | 是 | 日期，默认 `YYYY-MM-DD` |
| `counterparty` | 是 | 非空交易方，最多 300 字符 |
| `direction` | 是 | 仅 `IN` 或 `OUT`，区分大小写 |
| `amount` | 是 | 正数十进制金额，最多两位小数；不接受科学记数法、千分位或静默舍入 |
| `description` | 否 | 交易说明 |
| `external_id` | 否 | 外部交易编号，最多 200 字符；同一导入中不得重复 |

金额由 `Decimal` 精确解析并换算为整数分。交易方标准化执行 Unicode NFKC、压缩空白及大小写折叠；原始单元格值保存在 `raw_row_json`，不会被标准化结果覆盖。CSV 原件也保留在上传文件存储中。默认最多 200 条非空数据行，属于可调整的 MVP 初始限制。

## 列名映射

`CSV_COLUMN_MAP` 是 JSON 对象，键为上述标准字段，值为源 CSV 表头。必填字段必须全部映射；可选字段可省略。可在 `.env` 中配置默认映射，也可在单次导入请求中通过 `column_map` 覆盖部分或全部映射。例如源文件表头为 `Date,Payee,Flow,Value`：

```json
{"transaction_date":"Date","counterparty":"Payee","direction":"Flow","amount":"Value"}
```

`CSV_DATE_FORMAT` 默认 `%Y-%m-%d`，`CSV_MAX_ROWS` 默认 `200`。数据行中的 `direction` 值仍只接受 `IN` 与 `OUT`；列名映射不改变业务值规则。

## 导入步骤

1. 以 `file_category=bank_statement_csv` 上传 CSV 到 `POST /api/v1/orders/{order_id}/files`，取得文件 `id`。
2. 调用 `POST /api/v1/orders/{order_id}/imports/csv`，JSON 示例：

```json
{"file_id":"<上传文件 ID>","column_map":{"transaction_date":"Date","counterparty":"Payee","direction":"Flow","amount":"Value"}}
```

3. 返回结果包含 `total_rows`、`success_rows`、`failed_rows`、`errors`。每条错误包含 `row_number`、`reason` 与原始行。行号是 CSV 文件中的物理结束行号，表头通常为第 1 行。表头或编码错误返回 422，不创建导入记录；行级错误不阻止其他行入库。同一上传文件再次导入时返回已有导入结果，不重复写入交易。

读取接口：`GET /api/v1/orders/{order_id}/transactions`、`GET /api/v1/orders/{order_id}/imports`、`GET /api/v1/imports/{import_id}`。这些接口沿用订单归属检查；开发和测试环境需传 `X-User-Id`。

常见行错误原因：`missing_required_value`、`invalid_date`、`invalid_amount`、`amount_precision`、`amount_out_of_range`、`invalid_direction`、`duplicate_external_id`、`column_count_mismatch`。同一订单内不同上传文件的相同 `external_id` 是否视为同一交易，仍待业务确认；目前只在单次导入内检查重复。
