export type LedgerStatus = 'matched' | 'difference' | 'duplicate' | 'missing';

export type LedgerRow = {
  id: string;
  date: string;
  counterparty: string;
  invoiceCents: number | null;
  transactionCents: number | null;
  status: LedgerStatus;
  evidence: string[];
};

export type LedgerFile = {
  id: string;
  name: string;
  kind: 'image' | 'csv';
  sizeLabel: string;
};

// Synthetic material from the MVP brief. These are example results, not OCR output.
export const DEMO_FILES: LedgerFile[] = [
  { id: 'file-01', name: '01_办公场地租赁.jpg', kind: 'image', sizeLabel: '1.2 MB' },
  { id: 'file-02', name: '02_设备租赁.jpg', kind: 'image', sizeLabel: '860 KB' },
  { id: 'file-03', name: '03_设计素材.png', kind: 'image', sizeLabel: '640 KB' },
  { id: 'file-04', name: '04_制作服务.jpg', kind: 'image', sizeLabel: '1.1 MB' },
  { id: 'file-05', name: '05_印刷服务.jpg', kind: 'image', sizeLabel: '920 KB' },
  { id: 'file-06', name: '06_办公场地租赁_重复.jpg', kind: 'image', sizeLabel: '1.2 MB' },
  { id: 'file-07', name: '2026年10月_银行流水.csv', kind: 'csv', sizeLabel: '2 KB' },
];

export const DEMO_ROWS: LedgerRow[] = [
  { id: 'LC-001', date: '2026-10-03', counterparty: '和光空间', invoiceCents: 360000, transactionCents: 360000, status: 'matched', evidence: ['01_办公场地租赁.jpg', '银行流水第 1 行'] },
  { id: 'LC-002', date: '2026-10-08', counterparty: '映像设备租赁', invoiceCents: 128000, transactionCents: 128000, status: 'matched', evidence: ['02_设备租赁.jpg', '银行流水第 2 行'] },
  { id: 'LC-003', date: '2026-10-12', counterparty: '纸间设计', invoiceCents: 68000, transactionCents: 68000, status: 'matched', evidence: ['03_设计素材.png', '银行流水第 3 行'] },
  { id: 'LC-004', date: '2026-10-18', counterparty: '青禾制作', invoiceCents: 240000, transactionCents: 240000, status: 'matched', evidence: ['04_制作服务.jpg', '银行流水第 4 行'] },
  { id: 'LC-005', date: '2026-10-23', counterparty: '方圆印务', invoiceCents: 258000, transactionCents: 285000, status: 'difference', evidence: ['05_印刷服务.jpg', '银行流水第 5 行'] },
  { id: 'LC-006', date: '2026-10-03', counterparty: '和光空间（重复票据）', invoiceCents: 360000, transactionCents: null, status: 'duplicate', evidence: ['06_办公场地租赁_重复.jpg', '与 01_办公场地租赁.jpg 重复，不计入有效票据汇总'] },
  { id: 'LC-007', date: '2026-10-27', counterparty: '拾光办公', invoiceCents: null, transactionCents: 56000, status: 'missing', evidence: ['银行流水第 6 行', '尚未提供对应票据'] },
];

const currency = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'CNY',
  currencyDisplay: 'narrowSymbol',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMoney(cents: number): string {
  return currency.format(cents / 100).replace(/\s/g, '');
}

export function getSummary(rows: LedgerRow[]) {
  const summary = {
    matched: 0,
    difference: 0,
    duplicate: 0,
    missing: 0,
    invoiceTotalCents: 0,
    transactionTotalCents: 0,
    differenceCents: 0,
  };
  for (const row of rows) {
    summary[row.status] += 1;
    if (row.status === 'duplicate') continue;
    summary.invoiceTotalCents += row.invoiceCents ?? 0;
    summary.transactionTotalCents += row.transactionCents ?? 0;
    if (row.status === 'difference' && row.invoiceCents !== null && row.transactionCents !== null) {
      summary.differenceCents += Math.abs(row.transactionCents - row.invoiceCents);
    }
  }
  return summary;
}

const statusLabels: Record<LedgerStatus, string> = {
  matched: '核对一致',
  difference: '金额差异',
  duplicate: '重复票据（不计入汇总）',
  missing: '待补充凭证',
};

function csvCell(value: string): string {
  // Spreadsheet formulas can execute even in quoted CSV cells. Prefix unsafe
  // text with an apostrophe, including formulas preceded by whitespace.
  const safe = /^[\s]*[=+@-]/u.test(value) || /^[\t\r\n]/u.test(value)
    ? `'${value}`
    : value;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function exportCsv(rows: LedgerRow[]): string {
  const records = [
    ['编号', '日期', '交易方', '票据金额（元）', '流水金额（元）', '核对结果', '依据'],
    ...rows.map((row) => [
      row.id,
      row.date,
      row.counterparty,
      row.invoiceCents === null ? '' : (row.invoiceCents / 100).toFixed(2),
      row.transactionCents === null ? '' : (row.transactionCents / 100).toFixed(2),
      statusLabels[row.status],
      row.evidence.join('；'),
    ]),
  ];
  return '\uFEFF' + records.map((record) => record.map(csvCell).join(',')).join('\r\n');
}

type UploadFile = Pick<File, 'name' | 'size' | 'type'>;
const MAX_FILE_BYTES = 5 * 1024 * 1024;

function fileKind(file: UploadFile): 'image' | 'csv' | null {
  if (/\.(jpe?g|png)$/i.test(file.name)) return 'image';
  if (/\.csv$/i.test(file.name)) return 'csv';
  return null;
}

export function validateFiles(files: UploadFile[], existing: UploadFile[] = []): string | null {
  for (const file of files) {
    const kind = fileKind(file);
    if (!kind) return '仅支持 JPG、PNG 票据和 CSV 流水，暂不支持 PDF';
    if (file.size > MAX_FILE_BYTES) return `“${file.name}”超过 5 MB，请压缩后重试`;
    const mime = file.type.toLowerCase();
    const allowedMime = kind === 'image'
      ? ['image/jpeg', 'image/png']
      : ['text/csv', 'application/csv', 'application/vnd.ms-excel', 'text/plain'];
    if (mime && !allowedMime.includes(mime)) return `“${file.name}”的文件类型与扩展名不一致`;
  }
  const combined = [...existing, ...files];
  if (combined.filter((file) => fileKind(file) === 'image').length > 20) {
    return '每单最多上传 20 张票据图片';
  }
  if (combined.filter((file) => fileKind(file) === 'csv').length > 1) {
    return '每单仅支持 1 份 CSV 流水，请先移除已有流水';
  }
  // Checking the CSV's header and 200-row limit requires reading its contents.
  // The upload UI performs those asynchronous checks before accepting the file.
  return null;
}

export function countCsvDataRows(text: string): number {
  const input = text.replace(/^\uFEFF/, '');
  let inQuotes = false;
  let hasContent = false;
  let records = 0;
  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];
    if (char === '"') {
      hasContent = true;
      if (inQuotes && input[i + 1] === '"') {
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (!inQuotes && (char === '\n' || char === '\r')) {
      if (hasContent) records += 1;
      hasContent = false;
      if (char === '\r' && input[i + 1] === '\n') i += 1;
    } else if (char.trim() !== '') {
      hasContent = true;
    }
  }
  if (hasContent) records += 1;
  return Math.max(0, records - 1);
}

export function validateCsvContent(text: string): string | null {
  const input = text.replace(/^\uFEFF/, '');
  const records: string[][] = [];
  let record: string[] = [];
  let field = '';
  let started = false;
  let state: 'unquoted' | 'quoted' | 'after-quote' = 'unquoted';

  const finishRecord = () => {
    if (started) records.push([...record, field]);
    record = [];
    field = '';
    started = false;
  };

  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];
    if (state === 'quoted') {
      if (char === '"') {
        if (input[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          state = 'after-quote';
        }
      } else {
        field += char;
      }
      continue;
    }
    if (char === ',') {
      record.push(field);
      field = '';
      started = true;
      state = 'unquoted';
    } else if (char === '\n' || char === '\r') {
      finishRecord();
      state = 'unquoted';
      if (char === '\r' && input[i + 1] === '\n') i += 1;
    } else if (state === 'after-quote') {
      if (char !== ' ' && char !== '\t') return 'CSV 引号闭合后存在无效字符，请检查文件格式';
    } else if (char === '"') {
      if (field !== '') return 'CSV 引号格式不正确，请将整个字段放在双引号内';
      state = 'quoted';
      started = true;
    } else {
      field += char;
      if (char.trim() !== '') started = true;
    }
  }
  if (state === 'quoted') return 'CSV 中存在未闭合的双引号，请检查后重新添加';
  finishRecord();
  if (!records.length) return 'CSV 文件为空，请添加包含表头和流水记录的文件';

  const columns = ['transaction_id', 'date', 'counterparty', 'amount', 'direction', 'remark'];
  if (records[0].length !== columns.length || records[0].some((value, index) => value.trim() !== columns[index])) {
    return 'CSV 表头必须依次为 transaction_id,date,counterparty,amount,direction,remark';
  }
  if (records.length === 1) return 'CSV 仅包含表头，请至少添加 1 条流水记录';
  if (records.length - 1 > 200) return 'CSV 最多支持 200 条流水，请拆分后重新添加';
  for (let i = 1; i < records.length; i += 1) {
    if (records[i].length !== columns.length) return `CSV 第 ${i} 条流水必须包含 6 列，请检查逗号和引号`;
  }
  return null;
}
