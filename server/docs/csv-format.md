# 资金流水 CSV 格式

本文件是交付入口。完整的字段、列名映射、导入步骤、行级错误说明见 [CSV 格式与导入](CSV.md)，可直接使用 [标准模板](csv_template.csv)。

默认必填列：`transaction_date`、`counterparty`、`direction`、`amount`。可选列：`description`、`external_id`。日期格式为 `YYYY-MM-DD`，方向仅接受 `IN` 或 `OUT`。金额为正数十进制字符串，最多两位小数，使用 `Decimal` 精确换算为整数分；超过两位小数直接报错。文件须为 UTF-8，可含 BOM。列名可通过 `CSV_COLUMN_MAP` 或单次导入请求的 `column_map` 配置。

导入保留原始 CSV 和每行 `raw_row_json`；行错误独立保存，有效行正常入库。空文件或缺失必填表头会拒绝整批导入。`CSV_MAX_ROWS=200` 是可调整的 MVP 初始上限。
