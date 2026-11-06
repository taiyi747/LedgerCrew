"""Pure, deterministic reconciliation. No database, OCR, Agent, or model calls."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.csv_service import normalize_counterparty

MATCH_RULE = "exact_party_direction_amount_date_3d_unique_v1"


@dataclass(frozen=True)
class InvoiceInput:
    id: str
    invoice_number: str | None
    issue_date: date | None
    seller: str | None
    buyer: str | None
    total_amount_cents: int | None
    extraction_status: str
    source_sha256: str | None


@dataclass(frozen=True)
class TransactionInput:
    id: str
    external_id: str | None
    transaction_date: date
    normalized_counterparty: str
    direction: str
    amount_cents: int
    description: str | None


@dataclass(frozen=True)
class MatchResult:
    invoice_id: str
    transaction_id: str
    evidence_json: dict[str, Any]


@dataclass(frozen=True)
class TicketResult:
    exception_type: str
    invoice_id: str | None = None
    transaction_id: str | None = None
    related_amount_cents: int | None = None
    difference_cents: int | None = None
    evidence_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconciliationResult:
    matches: list[MatchResult]
    tickets: list[TicketResult]
    income_total_cents: int
    expense_total_cents: int
    net_cash_change_cents: int
    matched_count: int
    unmatched_count: int
    exception_count: int


def reconcile(
    studio_name: str, period_start: date, period_end: date,
    invoices: list[InvoiceInput], transactions: list[TransactionInput],
) -> ReconciliationResult:
    """Inputs must be ordered oldest first; only mutual one-to-one candidates match."""
    studio = normalize_counterparty(studio_name)
    tickets: list[TicketResult] = []
    matches: list[MatchResult] = []
    duplicate_invoices: set[str] = set()
    duplicate_transactions: set[str] = set()
    seen_numbers: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    seen_external_ids: dict[str, str] = {}
    seen_transaction_keys: dict[tuple[Any, ...], str] = {}

    for invoice in invoices:
        number = normalize_counterparty(invoice.invoice_number or "")
        duplicate_of = seen_numbers.get(number) if number else None
        if number and duplicate_of is None:
            seen_numbers[number] = invoice.id
        if not number and invoice.source_sha256:
            duplicate_of = seen_hashes.get(invoice.source_sha256)
            seen_hashes.setdefault(invoice.source_sha256, invoice.id)
        if duplicate_of:
            duplicate_invoices.add(invoice.id)
            tickets.append(TicketResult("DUPLICATE_INVOICE", invoice_id=invoice.id,
                                        related_amount_cents=invoice.total_amount_cents,
                                        evidence_json={"duplicate_of_invoice_id": duplicate_of,
                                                       "basis": "invoice_number" if number else "source_file_sha256"}))

    for transaction in transactions:
        external_id = normalize_counterparty(transaction.external_id or "")
        duplicate_of = seen_external_ids.get(external_id) if external_id else None
        if external_id and duplicate_of is None:
            seen_external_ids[external_id] = transaction.id
        if not external_id:
            key = (transaction.transaction_date, transaction.normalized_counterparty,
                   transaction.direction, transaction.amount_cents, transaction.description)
            duplicate_of = seen_transaction_keys.get(key)
            seen_transaction_keys.setdefault(key, transaction.id)
        if duplicate_of:
            duplicate_transactions.add(transaction.id)
            tickets.append(TicketResult("DUPLICATE_TRANSACTION", transaction_id=transaction.id,
                                        related_amount_cents=transaction.amount_cents,
                                        evidence_json={"duplicate_of_transaction_id": duplicate_of,
                                                       "basis": "external_id" if external_id else "exact_fields"}))

    eligible: dict[str, tuple[str, str]] = {}
    for invoice in invoices:
        if invoice.id in duplicate_invoices:
            continue
        missing = [name for name in ("issue_date", "seller", "buyer", "total_amount_cents")
                   if not getattr(invoice, name) or
                   (name in {"seller", "buyer"} and not normalize_counterparty(getattr(invoice, name)))]
        if invoice.extraction_status != "ready":
            missing.append("extraction_status")
        if missing:
            tickets.append(TicketResult("INVOICE_FIELD_MISSING", invoice_id=invoice.id,
                                        related_amount_cents=invoice.total_amount_cents,
                                        evidence_json={"missing_or_invalid_fields": missing}))
            continue
        if not period_start <= invoice.issue_date <= period_end:
            tickets.append(TicketResult("COUNTERPARTY_OR_DATE_CONFLICT", invoice_id=invoice.id,
                                        related_amount_cents=invoice.total_amount_cents,
                                        evidence_json={"reason": "invoice_outside_order_period"}))
            continue
        seller = normalize_counterparty(invoice.seller)
        buyer = normalize_counterparty(invoice.buyer)
        if (seller == studio) == (buyer == studio):
            tickets.append(TicketResult("COUNTERPARTY_OR_DATE_CONFLICT", invoice_id=invoice.id,
                                        related_amount_cents=invoice.total_amount_cents,
                                        evidence_json={"reason": "studio_identity_ambiguous"}))
            continue
        eligible[invoice.id] = (buyer if seller == studio else seller, "IN" if seller == studio else "OUT")

    active_transactions = [transaction for transaction in transactions
                           if transaction.id not in duplicate_transactions
                           and period_start <= transaction.transaction_date <= period_end]
    invoice_by_id = {invoice.id: invoice for invoice in invoices}
    transaction_by_id = {transaction.id: transaction for transaction in transactions}
    candidates: dict[str, list[str]] = {}
    reverse: dict[str, list[str]] = {transaction.id: [] for transaction in active_transactions}
    for invoice_id, (party, direction) in eligible.items():
        invoice = invoice_by_id[invoice_id]
        ids = [transaction.id for transaction in active_transactions
               if transaction.normalized_counterparty == party
               and transaction.direction == direction
               and transaction.amount_cents == invoice.total_amount_cents
               and abs((transaction.transaction_date - invoice.issue_date).days) <= 3]
        candidates[invoice_id] = ids
        for transaction_id in ids:
            reverse[transaction_id].append(invoice_id)

    covered_transactions: set[str] = set()
    matched_transactions: set[str] = set()
    matched_invoices: set[str] = set()
    for invoice_id, ids in candidates.items():
        if len(ids) == 1 and len(reverse[ids[0]]) == 1:
            transaction_id = ids[0]
            invoice = invoice_by_id[invoice_id]
            transaction = transaction_by_id[transaction_id]
            matches.append(MatchResult(invoice_id, transaction_id, {
                "normalized_counterparty": eligible[invoice_id][0],
                "direction": eligible[invoice_id][1],
                "amount_cents": invoice.total_amount_cents,
                "invoice_date": invoice.issue_date.isoformat(),
                "transaction_date": transaction.transaction_date.isoformat(),
                "date_difference_days": abs((transaction.transaction_date - invoice.issue_date).days),
            }))
            matched_invoices.add(invoice_id)
            matched_transactions.add(transaction_id)
            covered_transactions.add(transaction_id)
        elif ids:
            covered_transactions.update(ids)
            tickets.append(TicketResult("MULTIPLE_CANDIDATES", invoice_id=invoice_id,
                                        related_amount_cents=invoice_by_id[invoice_id].total_amount_cents,
                                        evidence_json={"candidate_transaction_ids": ids,
                                                       "competing_invoice_ids": sorted({other for transaction_id in ids
                                                                                         for other in reverse[transaction_id]})}))

    for invoice_id, (party, direction) in eligible.items():
        if invoice_id in matched_invoices or candidates[invoice_id]:
            continue
        invoice = invoice_by_id[invoice_id]
        same_party = [transaction for transaction in active_transactions
                      if transaction.id not in matched_transactions
                      and transaction.normalized_counterparty == party]
        amount_near = [transaction for transaction in same_party
                       if transaction.direction == direction
                       and abs((transaction.transaction_date - invoice.issue_date).days) <= 3
                       and transaction.amount_cents != invoice.total_amount_cents]
        if len(amount_near) > 1:
            covered_transactions.update(transaction.id for transaction in amount_near)
            tickets.append(TicketResult("MULTIPLE_CANDIDATES", invoice_id=invoice_id,
                                        related_amount_cents=invoice.total_amount_cents,
                                        evidence_json={"reason": "multiple_amount_conflicts",
                                                       "candidate_transaction_ids": [item.id for item in amount_near]}))
        elif amount_near:
            transaction = amount_near[0]
            covered_transactions.add(transaction.id)
            tickets.append(TicketResult("AMOUNT_MISMATCH", invoice_id=invoice_id,
                                        transaction_id=transaction.id,
                                        related_amount_cents=invoice.total_amount_cents,
                                        difference_cents=transaction.amount_cents - invoice.total_amount_cents,
                                        evidence_json={"invoice_amount_cents": invoice.total_amount_cents,
                                                       "transaction_amount_cents": transaction.amount_cents}))
        else:
            conflicts = [transaction for transaction in same_party
                         if transaction.amount_cents == invoice.total_amount_cents
                         and (transaction.direction != direction
                              or abs((transaction.transaction_date - invoice.issue_date).days) > 3)]
            if conflicts:
                covered_transactions.update(transaction.id for transaction in conflicts)
                tickets.append(TicketResult("COUNTERPARTY_OR_DATE_CONFLICT", invoice_id=invoice_id,
                                            transaction_id=conflicts[0].id if len(conflicts) == 1 else None,
                                            related_amount_cents=invoice.total_amount_cents,
                                            evidence_json={"candidate_transaction_ids": [item.id for item in conflicts],
                                                           "reason": "direction_or_date_conflict"}))
            else:
                tickets.append(TicketResult("MISSING_TRANSACTION", invoice_id=invoice_id,
                                            related_amount_cents=invoice.total_amount_cents,
                                            evidence_json={"reason": "no_transaction_candidate"}))

    for transaction in transactions:
        if transaction.id in duplicate_transactions or transaction.id in covered_transactions:
            continue
        if not period_start <= transaction.transaction_date <= period_end:
            tickets.append(TicketResult("COUNTERPARTY_OR_DATE_CONFLICT", transaction_id=transaction.id,
                                        related_amount_cents=transaction.amount_cents,
                                        evidence_json={"reason": "transaction_outside_order_period"}))
        else:
            tickets.append(TicketResult("MISSING_INVOICE", transaction_id=transaction.id,
                                        related_amount_cents=transaction.amount_cents,
                                        evidence_json={"reason": "no_invoice_candidate"}))

    income = sum(transaction.amount_cents for transaction in transactions
                 if period_start <= transaction.transaction_date <= period_end and transaction.direction == "IN")
    expense = sum(transaction.amount_cents for transaction in transactions
                  if period_start <= transaction.transaction_date <= period_end and transaction.direction == "OUT")
    return ReconciliationResult(matches, tickets, income, expense, income - expense,
                                len(matches), len(invoices) + len(transactions) - 2 * len(matches), len(tickets))
