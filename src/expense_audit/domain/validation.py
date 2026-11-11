from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .models import ExtractedExpense, Finding, PolicyReason

RFC_PATTERN = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")
TOTAL_TOLERANCE = Decimal("1.00")
CRITICAL_FIELDS = ("rfc_emisor", "rfc_receptor", "expense_date", "total")
SUPPORTED_CURRENCY = "MXN"


def normalize_rfc(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(value.split()).upper()
    return cleaned or None


def is_valid_rfc(value: str | None) -> bool:
    normalized = normalize_rfc(value)
    return normalized is not None and RFC_PATTERN.match(normalized) is not None


def money(value: Decimal) -> str:
    """Plain decimal string without exponent or thousands separators."""
    return format(value, "f")


def validate_extraction(expense: ExtractedExpense, today: date) -> list[Finding]:
    """Deterministic document-level validation independent of stored data."""
    findings: list[Finding] = []

    missing = [name for name in CRITICAL_FIELDS if getattr(expense, name) is None]
    if missing:
        findings.append(Finding(PolicyReason.MISSING_CRITICAL_FIELDS, {"missing": missing}))

    invalid_rfc_fields = [
        name
        for name in ("rfc_emisor", "rfc_receptor")
        if getattr(expense, name) is not None and not is_valid_rfc(getattr(expense, name))
    ]
    if invalid_rfc_fields:
        findings.append(Finding(PolicyReason.INVALID_RFC, {"fields": invalid_rfc_fields}))

    if expense.subtotal is not None and expense.iva is not None and expense.total is not None:
        difference = abs(expense.subtotal + expense.iva - expense.total)
        if difference > TOTAL_TOLERANCE:
            findings.append(
                Finding(
                    PolicyReason.TOTAL_MISMATCH,
                    {
                        "subtotal": money(expense.subtotal),
                        "iva": money(expense.iva),
                        "total": money(expense.total),
                        "difference": money(difference),
                        "tolerance": money(TOTAL_TOLERANCE),
                    },
                )
            )

    if expense.expense_date is not None and expense.expense_date > today:
        findings.append(
            Finding(
                PolicyReason.DATE_IN_FUTURE,
                {
                    "expense_date": expense.expense_date.isoformat(),
                    "processing_date": today.isoformat(),
                },
            )
        )

    if expense.total is not None and expense.total <= 0:
        findings.append(Finding(PolicyReason.INVALID_AMOUNT, {"total": money(expense.total)}))

    if expense.currency.upper() != SUPPORTED_CURRENCY:
        findings.append(
            Finding(PolicyReason.CURRENCY_UNSUPPORTED, {"currency": expense.currency.upper()})
        )

    return findings
