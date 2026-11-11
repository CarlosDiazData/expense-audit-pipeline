from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class Category(StrEnum):
    FOOD = "FOOD"
    TRANSPORT = "TRANSPORT"
    SOFTWARE = "SOFTWARE"
    LODGING = "LODGING"
    OTHER = "OTHER"


class PolicyStatus(StrEnum):
    VALID = "VALID"
    SUSPICIOUS = "SUSPICIOUS"
    NON_DEDUCTIBLE = "NON_DEDUCTIBLE"


class PolicyReason(StrEnum):
    INVALID_RFC = "INVALID_RFC"
    NON_DEDUCTIBLE_CATEGORY = "NON_DEDUCTIBLE_CATEGORY"
    RECEPTOR_NOT_COMPANY = "RECEPTOR_NOT_COMPANY"
    MISSING_CRITICAL_FIELDS = "MISSING_CRITICAL_FIELDS"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    DATE_IN_FUTURE = "DATE_IN_FUTURE"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    PER_EXPENSE_LIMIT_EXCEEDED = "PER_EXPENSE_LIMIT_EXCEEDED"
    MONTHLY_BUDGET_EXCEEDED = "MONTHLY_BUDGET_EXCEEDED"
    DUPLICATE_EXPENSE = "DUPLICATE_EXPENSE"
    CURRENCY_UNSUPPORTED = "CURRENCY_UNSUPPORTED"


class ExtractedExpense(BaseModel):
    rfc_emisor: str | None
    rfc_receptor: str | None
    expense_date: date | None
    subtotal: Decimal | None
    iva: Decimal | None
    total: Decimal | None
    currency: str = "MXN"
    category: Category
    vendor_name: str | None
    description: str | None


class CategoryLimit(BaseModel):
    category: Category
    per_expense_limit: Decimal
    monthly_limit: Decimal
    currency: str = "MXN"
    active: bool = True


@dataclass(frozen=True)
class Finding:
    code: PolicyReason
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    status: PolicyStatus
    reasons: list[PolicyReason]
    details: dict[str, dict]
