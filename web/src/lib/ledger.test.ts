import test from 'node:test';
import assert from 'node:assert/strict';
import { DEMO_ROWS, exportCsv, formatMoney, getSummary, validateFiles, countCsvDataRows, validateCsvContent } from './ledger.ts';
import type { LedgerRow } from './ledger.ts';

const image = (name = '票据.jpg', size = 1024) => ({ name, size, type: 'image/jpeg' });
const csv = (name = '流水.csv') => ({ name, size: 1024, type: 'text/csv' });

test('example totals exclude duplicate invoices and retain missing-voucher payments', () => {
  assert.deepEqual(getSummary(DEMO_ROWS), {
    matched: 4,
    difference: 1,
    duplicate: 1,
    missing: 1,
    invoiceTotalCents: 1054000,
    transactionTotalCents: 1137000,
    differenceCents: 27000,
  });
});

test('differences are calculated as integer cents, separately from missing evidence', () => {
  const rows: LedgerRow[] = [
    { id: '1', date: '2026-10-01', counterparty: '示例', invoiceCents: 10, transactionCents: 30, status: 'difference', evidence: [] },
    { id: '2', date: '2026-10-02', counterparty: '待补票', invoiceCents: null, transactionCents: 80, status: 'missing', evidence: [] },
  ];
  assert.equal(getSummary(rows).differenceCents, 20);
  assert.equal(formatMoney(258000), '¥2,580.00');
  assert.equal(formatMoney(20), '¥0.20');
});

test('upload limits apply across existing and newly selected materials', () => {
  assert.equal(validateFiles([image('新票据.jpg')], Array.from({ length: 19 }, (_, i) => image(`${i}.jpg`))), null);
  assert.match(validateFiles([image()], Array.from({ length: 20 }, (_, i) => image(`${i}.jpg`))) ?? '', /20/);
  assert.match(validateFiles([csv('新增.csv')], [csv()]) ?? '', /1 份 CSV/);
  assert.equal(validateFiles([image('大票据.jpg', 5 * 1024 * 1024)]), null);
  assert.match(validateFiles([image('超限.jpg', 5 * 1024 * 1024 + 1)]) ?? '', /5 MB/);
  assert.match(validateFiles([{ ...csv(), size: 5 * 1024 * 1024 + 1 }]) ?? '', /5 MB/);
  assert.match(validateFiles([{ name: '票据.pdf', size: 100, type: 'application/pdf' }]) ?? '', /暂不支持 PDF/);
  assert.match(validateFiles([{ name: '伪装.jpg', size: 100, type: 'application/pdf' }]) ?? '', /不一致/);
  assert.equal(validateFiles([{ name: '手机照片.JPG', size: 100, type: '' }]), null);
});

test('CSV uses a UTF-8 BOM, escapes quotes and neutralizes spreadsheet formulas', () => {
  const row: LedgerRow = {
    ...DEMO_ROWS[0],
    id: '=1+1',
    counterparty: ' =HYPERLINK("https://example.com")',
    evidence: ['@SUM(A1)', '原始说明含有,逗号和"引号"'],
  };
  const output = exportCsv([row]);
  assert.ok(output.startsWith('\uFEFF'));
  assert.ok(output.includes('"\'=1+1"'));
  assert.ok(output.includes('"\' =HYPERLINK(""https://example.com"")"'));
  assert.ok(output.includes('"\'@SUM(A1)；原始说明含有,逗号和""引号"""'));
  assert.ok(output.includes('\r\n'));
  assert.ok(output.includes('"3600.00"'));
});


test('CSV data-row count skips BOM, CRLF, blank lines and quoted newlines', () => {
  assert.equal(countCsvDataRows(''), 0);
  assert.equal(countCsvDataRows('\uFEFFtransaction_id,date\r\n'), 0);
  assert.equal(countCsvDataRows('\uFEFFtransaction_id,remark\r\n1,"首行\r\n说明"\r\n\r\n2,"引号""示例"\r\n   \r\n'), 2);
  assert.equal(countCsvDataRows('id,remark\n1,"分两行\n说明"\n2,正常\n'), 2);
  assert.equal(countCsvDataRows('id,remark\n' + Array.from({ length: 201 }, (_, i) => `${i},说明`).join('\n')), 201);
});


const csvHeader = 'transaction_date,counterparty,direction,amount,description,external_id';

test('CSV validation accepts six columns with BOM, escaped quotes and multiline fields', () => {
  const input = '\uFEFF' + csvHeader + '\r\n1,2026-10-01,"方圆,印务",2580,out,"备注\r\n含""引号"""\r\n\r\n';
  assert.equal(validateCsvContent(input), null);
});

test('CSV validation rejects unclosed or invalid quotes and incorrect column counts', () => {
  assert.match(validateCsvContent(csvHeader + '\n1,2026-10-01,商户,10,out,"未闭合\n' + '继续\n'.repeat(201)) ?? '', /未闭合/);
  assert.match(validateCsvContent(csvHeader + '\n1,2026-10-01,商户,10,out,"备注"无效') ?? '', /无效字符/);
  assert.match(validateCsvContent(csvHeader + '\n1,2026-10-01,商"户,10,out,备注') ?? '', /引号格式/);
  assert.match(validateCsvContent(csvHeader + '\n1,2026-10-01,商户,10,out') ?? '', /6 列/);
});

test('CSV validation enforces the agreed header and one to 200 data rows', () => {
  assert.match(validateCsvContent('\uFEFF\r\n  \n') ?? '', /文件为空/);
  assert.match(validateCsvContent('id,date,name,amount,type,note\n1,2026-10-01,商户,10,out,备注') ?? '', /表头必须/);
  assert.match(validateCsvContent(csvHeader) ?? '', /至少添加 1 条/);
  const rows = Array.from({ length: 200 }, (_, i) => `${i},2026-10-01,商户,10,out,备注`);
  assert.equal(validateCsvContent(csvHeader + '\n' + rows.join('\n')), null);
  assert.match(validateCsvContent(csvHeader + '\n' + [...rows, '201,2026-10-01,商户,10,out,备注'].join('\n')) ?? '', /200 条/);
});
