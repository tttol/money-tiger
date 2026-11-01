"""Immutable monthly totals and comparison rules, independent of the web UI."""

from dataclasses import dataclass
from collections import defaultdict
from datetime import date
from decimal import Decimal
from enum import StrEnum
from itertools import groupby, zip_longest
from math import ceil


class Kind(StrEnum):
    """Distinguish incoming and outgoing transactions by their amount sign."""

    EXPENSE = "支出"
    INCOME = "収入"


@dataclass(frozen=True)
class CategoryTotal:
    """An aggregated, positive yen amount for one category and direction."""

    kind: Kind
    category: str
    amount: int


@dataclass(frozen=True)
class Transaction:
    """One included CSV row, with the same sign convention as category totals."""

    day: date
    kind: Kind
    category: str
    amount: int
    description: str
    subcategory: str = ""
    memo: str = ""


@dataclass(frozen=True)
class Month:
    """Parsed CSV totals with coverage and exclusion information."""

    period: str
    totals: tuple[CategoryTotal, ...]
    rows: int
    included: int
    last_date: date
    transactions: tuple[Transaction, ...] = ()

    @property
    def label(self) -> str:
        """Return the actual source month as a Japanese display label."""
        year, month = self.period.split("-")
        return f"{year}年{int(month)}月"

    def amount(self, kind: Kind, category: str | None = None) -> int:
        """Sum one direction, optionally restricted to a single category."""
        return sum(
            item.amount for item in self.totals
            if item.kind == kind and (category is None or item.category == category)
        )

    def details(self, kind: Kind, category: str) -> tuple[Transaction, ...]:
        """Return included category rows, newest first, restricted to one direction."""
        matching = (
            item for item in self.transactions
            if item.kind == kind and item.category == category
        )
        return tuple(sorted(matching, key=lambda item: (-item.day.toordinal(), -item.amount, item.description)))


@dataclass(frozen=True)
class Change:
    """A directional change with an undefined rate when the base is zero."""

    amount: int
    rate: Decimal | None

    @property
    def tone(self) -> str:
        """Return a semantic CSS/color key, without interpreting good or bad."""
        return "more" if self.amount > 0 else "less" if self.amount < 0 else "same"

    @property
    def label(self) -> str:
        """Describe the absolute change in yen with its direction."""
        if self.amount == 0:
            return "増減なし"
        direction = "増" if self.amount > 0 else "減"
        return f"{abs(self.amount):,}円{direction}"

    @property
    def rate_label(self) -> str:
        """Format rates without dividing by a zero previous amount."""
        if self.amount == 0:
            return "0.0%"
        if self.rate is None:
            return "比較元は0円"
        return f"{self.rate:+.1f}%"


@dataclass(frozen=True)
class CategoryComparison:
    """Comparable totals and a common axis for a category's two months."""

    category: str
    previous: int
    current: int
    change: Change
    step: int
    top: int

    @property
    def ticks(self) -> tuple[int, ...]:
        """Return integral tick labels in thousands of yen."""
        return tuple(range(0, self.top + 1, self.step))


@dataclass(frozen=True)
class DescriptionComparison:
    """All transactions sharing an exact description, aligned across two months."""

    description: str
    previous: tuple[Transaction, ...]
    current: tuple[Transaction, ...]

    @property
    def previous_total(self) -> int:
        """Return the previous month's total without discarding repeated rows."""
        return sum(item.amount for item in self.previous)

    @property
    def current_total(self) -> int:
        """Return the current month's total without discarding repeated rows."""
        return sum(item.amount for item in self.current)

    @property
    def change(self) -> Change:
        """Compute this description's contribution to the category difference."""
        return change_between(self.previous_total, self.current_total)


@dataclass(frozen=True)
class DetailRow:
    """Two individual transactions on a shared ledger baseline; either may be absent."""

    previous: Transaction | None
    current: Transaction | None


@dataclass(frozen=True)
class Comparison:
    """One ordered month pair and its direction-specific category charts."""

    previous: Month
    current: Month
    kind: Kind
    categories: tuple[CategoryComparison, ...]
    change: Change

    def details(self, category: str) -> tuple[DescriptionComparison, ...]:
        """Align exact names, preserving unmatched rows and sorting by impact."""
        previous = _group_details(self.previous.details(self.kind, category))
        current = _group_details(self.current.details(self.kind, category))
        matched = (
            DescriptionComparison(name, previous.get(name, ()), current.get(name, ()))
            for name in previous.keys() | current.keys()
        )
        return tuple(sorted(matched, key=lambda item: (
            -abs(item.change.amount), -max(item.previous_total, item.current_total), item.description,
        )))

    def detail_rows(self, category: str) -> tuple[DetailRow, ...]:
        """Align same-name occurrences and zip remaining unmatched transactions.

        Names follow the previous CSV's first appearance, with current-only rows
        filling unmatched positions. Extra occurrences of a shared name retain
        blank opposite cells, and each source transaction appears exactly once.
        """
        previous = _ledger_groups(self.previous, self.kind, category)
        current = _ledger_groups(self.current, self.kind, category)
        shared = previous.keys() & current.keys()
        previous_only = tuple(row for name, rows in previous.items() if name not in shared for row in rows)
        current_only = tuple(row for name, rows in current.items() if name not in shared for row in rows)
        unmatched = tuple(DetailRow(a, b) for a, b in zip_longest(previous_only, current_only))
        rows: list[DetailRow] = []
        inserted_unmatched = False
        for name, transactions in previous.items():
            if name in shared:
                rows.extend(DetailRow(a, b) for a, b in zip_longest(transactions, current[name]))
            elif not inserted_unmatched:
                rows.extend(unmatched)
                inserted_unmatched = True
        if not inserted_unmatched:
            rows.extend(unmatched)
        return tuple(rows)


def change_between(previous: int, current: int) -> Change:
    """Compute changes using unrounded integer yen and decimal percentages."""
    amount = current - previous
    rate = Decimal(amount) / Decimal(previous) * 100 if previous else None
    return Change(amount, rate)


def compare(previous: Month, current: Month, kind: Kind) -> Comparison:
    """Compare distinct chronological months; missing categories mean zero yen."""
    if previous.period >= current.period:
        raise ValueError("比較元には、比較先より前の月のCSVを選んでください。")
    names = {
        item.category for month in (previous, current)
        for item in month.totals if item.kind == kind
    }
    ordered = sorted(names, key=lambda name: (-max(previous.amount(kind, name), current.amount(kind, name)), name))
    categories = tuple(_category(previous, current, kind, name) for name in ordered)
    return Comparison(previous, current, kind, categories, change_between(previous.amount(kind), current.amount(kind)))


def _category(previous: Month, current: Month, kind: Kind, name: str) -> CategoryComparison:
    a, b = previous.amount(kind, name), current.amount(kind, name)
    maximum = max(a, b) / 1000
    magnitude = 10 ** max(0, len(str(max(a, b))) - 6)
    steps = tuple(s * magnitude for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000))
    step = next(s for s in steps if maximum / s <= 4.5)
    top = max(step * 2, ceil(maximum / step) * step)
    return CategoryComparison(name, a, b, change_between(a, b), step, top)


def _group_details(transactions: tuple[Transaction, ...]) -> dict[str, tuple[Transaction, ...]]:
    ordered = sorted(transactions, key=lambda item: item.description)
    return {name: tuple(rows) for name, rows in groupby(ordered, key=lambda item: item.description)}


def _ledger_groups(month: Month, kind: Kind, category: str) -> dict[str, tuple[Transaction, ...]]:
    grouped: defaultdict[str, list[Transaction]] = defaultdict(list)
    for transaction in month.transactions:
        if transaction.kind == kind and transaction.category == category:
            grouped[transaction.description].append(transaction)
    return {name: tuple(sorted(rows, key=lambda item: item.day)) for name, rows in grouped.items()}
