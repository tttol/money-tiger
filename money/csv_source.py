"""Read and validate Money Forward CSV exports without executing their content."""

import csv
import io
import re
from collections import defaultdict
from datetime import datetime

from money.domain import CategoryTotal, Kind, Month, Transaction

MAX_BYTES = 10 * 1024 * 1024
REQUIRED_COLUMNS = frozenset({"計算対象", "日付", "金額（円）", "大項目", "振替"})


class CsvError(ValueError):
    """A readable validation failure suitable for display beside a CSV input."""


def parse_csv(content: bytes) -> Month:
    """Parse one calendar month from UTF-8/BOM or CP932 data.

    Raises CsvError for malformed rows, ambiguous months, or duplicate IDs.
    Excluded and transfer rows never contribute to category totals.
    """
    if len(content) > MAX_BYTES:
        raise CsvError("CSVは10MB以下にしてください。")
    decoded = _decode(content)
    reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
    try:
        fieldnames = reader.fieldnames
    except csv.Error as exc:
        raise CsvError("CSVのヘッダーを読み取れません。引用符の形式を確認してください。") from exc
    if fieldnames is None or not REQUIRED_COLUMNS.issubset(fieldnames):
        raise CsvError("家計CSVの必須列（計算対象・日付・金額（円）・大項目・振替）がありません。")
    if len(set(fieldnames)) != len(fieldnames):
        raise CsvError("CSVのヘッダーに同じ列名が重複しています。")
    totals: defaultdict[tuple[Kind, str], int] = defaultdict(int)
    dates = []
    identifiers: set[str] = set()
    included = 0
    transactions: list[Transaction] = []
    try:
        for number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise CsvError(f"{number}行目の列数が一致しません。")
            try:
                day = datetime.strptime(row["日付"].strip(), "%Y/%m/%d").date()
            except ValueError as exc:
                raise CsvError(f"{number}行目の日付を読み取れません。YYYY/MM/DD形式にしてください。") from exc
            amount_text = row["金額（円）"].strip()
            if re.fullmatch(r"[+-]?[0-9]+", amount_text) is None or len(amount_text.lstrip("+-")) > 12:
                raise CsvError(f"{number}行目の金額は12桁以内の整数（円）にしてください。")
            amount = int(amount_text)
            if row["計算対象"] not in {"0", "1"} or row["振替"] not in {"0", "1"}:
                raise CsvError(f"{number}行目の計算対象・振替は0または1にしてください。")
            identifier = row.get("ID", "").strip()
            if identifier and identifier in identifiers:
                raise CsvError(f"{number}行目に重複したIDがあります。二重計上を防ぐため読み込みを中止しました。")
            if identifier:
                identifiers.add(identifier)
            dates.append(day)
            if row["計算対象"] == "1" and row["振替"] == "0":
                included += 1
                kind = Kind.EXPENSE if amount < 0 else Kind.INCOME
                category = row["大項目"].strip() or "未分類"
                if len(category) > 50:
                    raise CsvError(f"{number}行目の大項目は50文字以内にしてください。")
                totals[kind, category] += abs(amount)
                transactions.append(Transaction(
                    day=day,
                    kind=kind,
                    category=category,
                    amount=abs(amount),
                    description=row.get("内容", "").strip() or "内容未記載",
                    subcategory=row.get("中項目", "").strip(),
                    memo=row.get("メモ", "").strip(),
                ))
    except csv.Error as exc:
        raise CsvError("CSVの引用符または行の形式が正しくありません。") from exc
    if not dates:
        raise CsvError("CSVに明細がありません。")
    if len(totals) > 60:
        raise CsvError("1つのCSVのカテゴリは収支区分を合わせて60個以内にしてください。")
    periods = {day.strftime("%Y-%m") for day in dates}
    if len(periods) != 1:
        raise CsvError("1つのCSVには1か月分の明細を入れてください。")
    items = tuple(CategoryTotal(kind, category, amount) for (kind, category), amount in sorted(totals.items()))
    return Month(periods.pop(), items, len(dates), included, max(dates), tuple(transactions))


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvError("文字コードを読み取れません。UTF-8またはShift_JISのCSVを選んでください。")
