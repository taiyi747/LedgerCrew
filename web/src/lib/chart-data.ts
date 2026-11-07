import type { LedgerRow } from './ledger.ts';

export type TransactionStatus = Exclude<LedgerRow['status'], 'duplicate'>;
const categories: { status: TransactionStatus; label: string }[] = [
  { status: 'matched', label: '核对一致' },
  { status: 'difference', label: '金额差异' },
  { status: 'missing', label: '缺少凭证' },
];

export function getChartData(rows: LedgerRow[]) {
  const transactions = rows.filter(row => row.status !== 'duplicate' && row.transactionCents !== null);
  return {
    transactions,
    slices: categories.map(category => ({ ...category, count: transactions.filter(row => row.status === category.status).length })),
    duplicateCount: rows.filter(row => row.status === 'duplicate').length,
  };
}
