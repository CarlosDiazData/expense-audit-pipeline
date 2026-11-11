from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from .models import (
    CategoryLimit,
    ExtractedExpense,
    Finding,
    PolicyDecision,
    PolicyReason,
    PolicyStatus,
)
from .validation import SUPPORTED_CURRENCY, money, normalize_rfc, validate_extraction

NON_DEDUCTIBLE_REASONS = frozenset(
    {
        PolicyReason.INVALID_RFC,
        PolicyReason.NON_DEDUCTIBLE_CATEGORY,
        PolicyReason.RECEPTOR_NOT_COMPANY,
        PolicyReason.MISSING_CRITICAL_FIELDS,
    }
)


def evaluate_policy(
    expense: ExtractedExpense,
    limits: Iterable[CategoryLimit],
    *,
    today: date,
    company_rfc: str | None = None,
    monthly_spend: Decimal | None = None,
    duplicate_of: str | None = None,
) -> PolicyDecision:
    """Evaluate deterministic rules; the LLM never decides policy."""
    findings = validate_extraction(expense, today)

    active_limits = {limit.category: limit for limit in limits if limit.active}
    limit = active_limits.get(expense.category)
    if limit is None:
        findings.append(
            Finding(
                PolicyReason.NON_DEDUCTIBLE_CATEGORY,
                {"category": expense.category.value},
            )
        )

    normalized_company = normalize_rfc(company_rfc)
    normalized_receptor = normalize_rfc(expense.rfc_receptor)
    if (
        normalized_company is not None
        and normalized_receptor is not None
        and normalized_receptor != normalized_company
    ):
        findings.append(
            Finding(
                PolicyReason.RECEPTOR_NOT_COMPANY,
                {
                    "company_rfc": normalized_company,
                    "receptor_rfc": normalized_receptor,
                },
            )
        )

    is_supported_currency = expense.currency.upper() == SUPPORTED_CURRENCY
    if is_supported_currency and limit is not None and expense.total is not None:
        if expense.total > limit.per_expense_limit:
            findings.append(
                Finding(
                    PolicyReason.PER_EXPENSE_LIMIT_EXCEEDED,
                    {
                        "category": expense.category.value,
                        "limit": money(limit.per_expense_limit),
                        "observed": money(expense.total),
                    },
                )
            )
        if monthly_spend is not None and monthly_spend + expense.total > limit.monthly_limit:
            findings.append(
                Finding(
                    PolicyReason.MONTHLY_BUDGET_EXCEEDED,
                    {
                        "category": expense.category.value,
                        "limit": money(limit.monthly_limit),
                        "spent": money(monthly_spend),
                        "observed": money(expense.total),
                    },
                )
            )

    if duplicate_of is not None:
        findings.append(Finding(PolicyReason.DUPLICATE_EXPENSE, {"expense_id": duplicate_of}))

    reasons = [finding.code for finding in findings]
    details = {finding.code.value: finding.detail for finding in findings}
    if any(reason in NON_DEDUCTIBLE_REASONS for reason in reasons):
        status = PolicyStatus.NON_DEDUCTIBLE
    elif reasons:
        status = PolicyStatus.SUSPICIOUS
    else:
        status = PolicyStatus.VALID

    return PolicyDecision(status=status, reasons=reasons, details=details)
