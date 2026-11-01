"""Behavioral coverage for CSV boundaries, financial rules and local web flows."""

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from money.csv_source import CsvError, parse_csv
from money.domain import CategoryTotal, Change, DescriptionComparison, Kind, Month, Transaction, change_between, compare
from money.repository import Catalog, CsvRepository, Source, default_pair
from money.web import create_app

HEADERS = ["計算対象", "日付", "金額（円）", "大項目", "振替", "ID"]


def csv_bytes(rows: list[list[str]], encoding: str = "utf-8-sig", headers: tuple[str, ...] | None = None) -> bytes:
    """Build real quoted CSV input, including a BOM when requested."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers or HEADERS)
    writer.writerows(rows)
    return stream.getvalue().encode(encoding)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp932"])
def test_parser_respects_flags_and_keeps_positive_uncategorized_income(encoding: str) -> None:
    # GIVEN
    content = csv_bytes([
        ["1", "2026/09/02", "-1200", "食費", "0", "a"],
        ["1", "2026/09/03", "-300", "食費", "0", "b"],
        ["0", "2026/09/04", "-9999", "食費", "0", "c"],
        ["1", "2026/09/05", "-8888", "食費", "1", "d"],
        ["1", "2026/09/30", "137", "未分類", "0", "e"],
    ], encoding)
    expected = Month("2026-09", (CategoryTotal(Kind.INCOME, "未分類", 137), CategoryTotal(Kind.EXPENSE, "食費", 1500)), 5, 3, date(2026, 9, 30), (
        Transaction(date(2026, 9, 2), Kind.EXPENSE, "食費", 1200, "内容未記載"),
        Transaction(date(2026, 9, 3), Kind.EXPENSE, "食費", 300, "内容未記載"),
        Transaction(date(2026, 9, 30), Kind.INCOME, "未分類", 137, "内容未記載"),
    ))
    # WHEN
    actual = parse_csv(content)
    # THEN
    assert actual == expected


@pytest.mark.parametrize("row", [
    ["1", "2026/09/31", "-100", "食費", "0", "a"],
    ["1", "2026/09/01", "1.5", "食費", "0", "a"],
    ["1", "2026/09/01", "1,000", "食費", "0", "a"],
    ["yes", "2026/09/01", "-100", "食費", "0", "a"],
    ["1", "2026/09/01", "-100", "食費", "2", "a"],
    ["1", "2026/09/01", "1000000000000", "食費", "0", "a"],
    ["1", "2026/09/01", "-100", "食費", "0"],
])
def test_invalid_rows_are_rejected(row: list[str]) -> None:
    # GIVEN
    content = csv_bytes([row])
    # WHEN / THEN
    with pytest.raises(CsvError):
        parse_csv(content)


@pytest.mark.parametrize("content", [b"", b"hello,world\n1,2\n", b"\x81", b'"unclosed header', csv_bytes([])])
def test_unreadable_or_empty_csv_is_rejected(content: bytes) -> None:
    # WHEN / THEN
    with pytest.raises(CsvError):
        parse_csv(content)


def test_mixed_months_are_rejected() -> None:
    # GIVEN
    content = csv_bytes([["1", "2026/09/30", "-1", "食費", "0", "a"], ["1", "2026/10/01", "-1", "食費", "0", "b"]])
    # WHEN / THEN
    with pytest.raises(CsvError, match="1か月分"):
        parse_csv(content)


def test_duplicate_transaction_ids_are_rejected() -> None:
    # GIVEN
    content = csv_bytes([["1", "2026/09/01", "-1", "食費", "0", "same"], ["1", "2026/09/02", "-2", "食費", "0", "same"]])
    # WHEN / THEN
    with pytest.raises(CsvError, match="重複"):
        parse_csv(content)


def test_duplicate_header_columns_are_rejected() -> None:
    # GIVEN
    content = "計算対象,日付,金額（円）,大項目,振替,金額（円）\n1,2026/09/01,-100,食費,0,-200\n".encode("utf-8")
    # WHEN / THEN
    with pytest.raises(CsvError, match="列名が重複"):
        parse_csv(content)


@pytest.mark.parametrize(("previous", "current", "expected"), [(100, 150, Change(50, Decimal(50))), (100, 0, Change(-100, Decimal(-100))), (0, 100, Change(100, None)), (0, 0, Change(0, None)), (100, 100, Change(0, Decimal(0)))])
def test_change_handles_zero_and_missing_categories(previous: int, current: int, expected: Change) -> None:
    # WHEN
    actual = change_between(previous, current)
    # THEN
    assert actual == expected


def test_comparison_preserves_both_months_and_zero_for_absent_category() -> None:
    # GIVEN
    a = parse_csv(csv_bytes([["1", "2026/09/01", "-1200", "食費", "0", "a"]]))
    b = parse_csv(csv_bytes([["1", "2026/10/01", "-2735", "医療", "0", "b"]]))
    expected = [("医療", 0, 2735, (0, 1, 2, 3)), ("食費", 1200, 0, (0, 1, 2))]
    # WHEN
    actual = compare(a, b, Kind.EXPENSE)
    # THEN
    assert [(c.category, c.previous, c.current, c.ticks) for c in actual.categories] == expected


@pytest.mark.parametrize(("a", "b"), [("2026/09/01", "2026/09/02"), ("2026/10/01", "2026/09/01")])
def test_comparison_rejects_same_or_reversed_months(a: str, b: str) -> None:
    # GIVEN
    previous = parse_csv(csv_bytes([["1", a, "-1", "食費", "0", "a"]]))
    current = parse_csv(csv_bytes([["1", b, "-1", "食費", "0", "b"]]))
    # WHEN / THEN
    with pytest.raises(ValueError, match="前の月"):
        compare(previous, current, Kind.EXPENSE)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Use isolated synthetic files so uploads never touch personal source data."""
    (tmp_path / "september.csv").write_bytes(csv_bytes([["1", "2026/09/01", "-1200", "食費", "0", "a"], ["1", "2026/09/20", "10000", "収入", "0", "b"]]))
    (tmp_path / "october.csv").write_bytes(csv_bytes([["1", "2026/10/26", "-2400", "食費", "0", "c"], ["1", "2026/10/20", "9000", "収入", "0", "d"]]))
    return tmp_path


def test_default_pair_uses_latest_distinct_months(data_dir: Path) -> None:
    # GIVEN
    source = CsvRepository(data_dir).get("october.csv")
    old = CsvRepository(data_dir).get("september.csv")
    catalog = Catalog((old, source, Source("other-october.csv", source.month)), ())
    expected = ("september.csv", "other-october.csv")
    # WHEN
    actual = default_pair(catalog)
    # THEN
    assert actual == expected


@pytest.mark.parametrize("name", ["../secret.csv", "/tmp/secret.csv", "..\\secret.csv", "", "missing.csv"])
def test_repository_rejects_paths_outside_catalog(data_dir: Path, name: str) -> None:
    # GIVEN
    repository = CsvRepository(data_dir)
    # WHEN / THEN
    with pytest.raises(CsvError):
        repository.get(name)


def test_repository_does_not_follow_symlinks(data_dir: Path) -> None:
    # GIVEN
    (data_dir / "link.csv").symlink_to(data_dir / "september.csv")
    repository = CsvRepository(data_dir)
    # WHEN / THEN
    with pytest.raises(CsvError):
        repository.get("link.csv")


@pytest.mark.parametrize("path", ["/", "/?kind=income", "/static/style.css", "/static/favicon.svg", "/static/details.js"])
def test_web_pages_and_local_assets_work(data_dir: Path, path: str) -> None:
    # GIVEN
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.get(path)
    # THEN
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


def test_dashboard_has_actual_totals_and_accessible_charts(data_dir: Path) -> None:
    # GIVEN
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.get("/")
    # THEN
    assert all(value in response.text for value in ["1,200", "2,400", 'role="img"', "千円", "2026/10/26"])
    assert "https://" not in response.text


@pytest.mark.parametrize("kind", ["expense", "income"])
def test_png_download_is_a_real_image(data_dir: Path, kind: str) -> None:
    # GIVEN
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.get(f"/download/{kind}.png?previous=september.csv&current=october.csv")
    # THEN
    with Image.open(io.BytesIO(response.data)) as image:
        assert (response.status_code, response.mimetype, image.format, image.width) == (200, "image/png", "PNG", 3200)
    assert "attachment" in response.headers["Content-Disposition"]


def test_valid_upload_is_stored_and_original_files_stay_intact(data_dir: Path) -> None:
    # GIVEN
    original = (data_dir / "september.csv").read_bytes()
    content = csv_bytes([["1", "2026/11/01", "-4500", "食費", "0", "new"]], "cp932")
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.post("/csv", data={"csv": (io.BytesIO(content), "new.csv")}, follow_redirects=True)
    # THEN
    assert (response.status_code, len(tuple(data_dir.glob("*.csv"))), (data_dir / "september.csv").read_bytes()) == (200, 3, original)
    assert "4,500" in response.text


def test_invalid_upload_does_not_create_file(data_dir: Path) -> None:
    # GIVEN
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.post("/csv", data={"csv": (io.BytesIO(b"bad,data"), "bad.csv")})
    # THEN
    assert (response.status_code, len(tuple(data_dir.glob("*.csv")))) == (400, 2)
    assert 'role="alert"' in response.text


def test_uploading_an_original_csv_does_not_duplicate_it(data_dir: Path) -> None:
    # GIVEN
    content = (data_dir / "september.csv").read_bytes()
    repository = CsvRepository(data_dir)
    expected = ("september.csv", 2)
    # WHEN
    actual = repository.add(content)
    # THEN
    assert (actual.name, len(tuple(data_dir.glob("*.csv")))) == expected


def test_wrong_month_order_shows_friendly_error(data_dir: Path) -> None:
    # GIVEN
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.get("/?previous=october.csv&current=september.csv")
    # THEN
    assert response.status_code == 400
    assert "前の月" in response.text


@pytest.mark.parametrize(("host", "remote", "headers"), [("evil.example", "127.0.0.1", {}), ("localhost", "192.168.1.5", {}), ("localhost", "127.0.0.1", {"Origin": "https://evil.example"}), ("localhost", "127.0.0.1", {"Sec-Fetch-Site": "cross-site"})])
def test_nonlocal_requests_are_rejected(data_dir: Path, host: str, remote: str, headers: dict[str, str]) -> None:
    # GIVEN
    client = create_app(data_dir).test_client()
    # WHEN
    response = client.get("/", base_url=f"http://{host}", environ_overrides={"REMOTE_ADDR": remote}, headers=headers)
    # THEN
    assert response.status_code in {400, 403}


def test_empty_directory_has_onboarding(tmp_path: Path) -> None:
    # GIVEN
    client = create_app(tmp_path).test_client()
    # WHEN
    response = client.get("/")
    # THEN
    assert response.status_code == 200
    assert "2か月分のCSVを追加してください" in response.text


@pytest.fixture
def detailed_month() -> Month:
    """Include normal rows, a refund, exclusions, and an unrelated category."""
    headers = tuple(HEADERS) + ("内容", "中項目", "メモ")
    content = csv_bytes([
        ["1", "2026/09/02", "-1200", "食費", "0", "a", "スーパー", "食料品", "家族分"],
        ["1", "2026/09/03", "-300", "食費", "0", "b", "カフェ", "外食", ""],
        ["0", "2026/09/04", "-9999", "食費", "0", "c", "計算対象外", "", ""],
        ["1", "2026/09/05", "-8888", "食費", "1", "d", "振替の明細", "", ""],
        ["1", "2026/09/06", "137", "食費", "0", "e", "返金", "食料品", "返金のメモ"],
        ["1", "2026/09/07", "-80", "交通費", "0", "f", "電車", "電車", ""],
    ], headers=headers)
    return parse_csv(content)


@pytest.mark.parametrize(("kind", "expected"), [
    (Kind.EXPENSE, (
        Transaction(date(2026, 9, 3), Kind.EXPENSE, "食費", 300, "カフェ", "外食"),
        Transaction(date(2026, 9, 2), Kind.EXPENSE, "食費", 1200, "スーパー", "食料品", "家族分"),
    )),
    (Kind.INCOME, (Transaction(date(2026, 9, 6), Kind.INCOME, "食費", 137, "返金", "食料品", "返金のメモ"),)),
])
def test_details_preserve_fields_and_use_the_chart_filter(detailed_month: Month, kind: Kind, expected: tuple[Transaction, ...]) -> None:
    # WHEN
    actual = detailed_month.details(kind, "食費")
    # THEN
    assert actual == expected
    assert sum(row.amount for row in actual) == detailed_month.amount(kind, "食費")


def test_details_for_an_absent_category_are_empty(detailed_month: Month) -> None:
    # GIVEN
    expected = ()
    # WHEN
    actual = detailed_month.details(Kind.EXPENSE, "存在しないカテゴリ")
    # THEN
    assert actual == expected


def test_details_sort_same_day_by_amount_descending() -> None:
    # GIVEN
    month = parse_csv(csv_bytes([
        ["1", "2026/09/02", "-100", "食費", "0", "a"],
        ["1", "2026/09/02", "-300", "食費", "0", "b"],
    ]))
    expected = (300, 100)
    # WHEN
    actual = month.details(Kind.EXPENSE, "食費")
    # THEN
    assert tuple(row.amount for row in actual) == expected


def test_modal_content_has_both_months_and_excludes_nonmatching_rows(tmp_path: Path) -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容", "中項目", "メモ")
    (tmp_path / "september.csv").write_bytes(csv_bytes([
        ["1", "2026/09/02", "-1200", "食費", "0", "a", "スーパー", "食料品", "家族分"],
        ["1", "2026/09/03", "137", "食費", "0", "b", "返金は収入タブへ", "", ""],
        ["0", "2026/09/04", "-9999", "食費", "0", "c", "計算対象外の店", "", ""],
        ["1", "2026/09/05", "-8888", "食費", "1", "d", "振替の店", "", ""],
    ], headers=headers))
    (tmp_path / "october.csv").write_bytes(csv_bytes([
        ["1", "2026/10/26", "-2400", "食費", "0", "e", "レストラン", "外食", "会食"],
    ], headers=headers))
    client = create_app(tmp_path).test_client()
    # WHEN
    response = client.get("/")
    # THEN
    assert response.status_code == 200
    assert all(value in response.text for value in ['aria-haspopup="dialog"', "スーパー", "家族分", "レストラン", "会食", "1,200", "2,400", "2026/09/02", "2026/10/26"])
    assert all(value not in response.text for value in ["返金は収入タブへ", "計算対象外の店", "振替の店"])


def test_modal_income_content_keeps_refunds_in_income_direction(tmp_path: Path) -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容",)
    (tmp_path / "september.csv").write_bytes(csv_bytes([["1", "2026/09/02", "-1200", "食費", "0", "a", "支出の内容"]], headers=headers))
    (tmp_path / "october.csv").write_bytes(csv_bytes([["1", "2026/10/26", "137", "食費", "0", "b", "返金の内容"]], headers=headers))
    client = create_app(tmp_path).test_client()
    # WHEN
    response = client.get("/?kind=income")
    # THEN
    assert response.status_code == 200
    assert all(value in response.text for value in ["返金の内容", "137円", "この月に該当する明細はありません。"])
    assert "支出の内容" not in response.text


def test_transaction_text_is_escaped_in_modal_templates(tmp_path: Path) -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容", "中項目", "メモ")
    (tmp_path / "september.csv").write_bytes(csv_bytes([["1", "2026/09/02", "-1200", "食費", "0", "a", "<script>alert(1)</script>", "<b>分類</b>", "<img src=x onerror=alert(1)>"]], headers=headers))
    (tmp_path / "october.csv").write_bytes(csv_bytes([["1", "2026/10/26", "-2400", "食費", "0", "b", "普通の店", "", ""]], headers=headers))
    client = create_app(tmp_path).test_client()
    # WHEN
    response = client.get("/")
    # THEN
    assert all(value in response.text for value in ["&lt;script&gt;", "&lt;b&gt;", "&lt;img"])
    assert all(value not in response.text for value in ["<script>alert(1)</script>", "<b>分類</b>", "<img src=x"])


def test_comparison_aligns_repeated_names_and_keeps_unmatched_rows() -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容",)
    previous = parse_csv(csv_bytes([
        ["1", "2026/09/02", "-100", "食費", "0", "a", "同じ店"],
        ["1", "2026/09/03", "-200", "食費", "0", "b", "同じ店"],
        ["1", "2026/09/04", "-400", "食費", "0", "c", "旧店"],
    ], headers=headers))
    current = parse_csv(csv_bytes([
        ["1", "2026/10/05", "-200", "食費", "0", "d", "同じ店"],
        ["1", "2026/10/06", "-800", "食費", "0", "e", "同じ店"],
        ["1", "2026/10/07", "-700", "食費", "0", "f", "新店"],
    ], headers=headers))
    comparison = compare(previous, current, Kind.EXPENSE)
    expected = (
        DescriptionComparison("同じ店", (
            Transaction(date(2026, 9, 3), Kind.EXPENSE, "食費", 200, "同じ店"),
            Transaction(date(2026, 9, 2), Kind.EXPENSE, "食費", 100, "同じ店"),
        ), (
            Transaction(date(2026, 10, 6), Kind.EXPENSE, "食費", 800, "同じ店"),
            Transaction(date(2026, 10, 5), Kind.EXPENSE, "食費", 200, "同じ店"),
        )),
        DescriptionComparison("新店", (), (Transaction(date(2026, 10, 7), Kind.EXPENSE, "食費", 700, "新店"),)),
        DescriptionComparison("旧店", (Transaction(date(2026, 9, 4), Kind.EXPENSE, "食費", 400, "旧店"),), ()),
    )
    # WHEN
    actual = comparison.details("食費")
    # THEN
    assert actual == expected
    assert sum(group.previous_total for group in actual) == comparison.previous.amount(Kind.EXPENSE, "食費")
    assert sum(group.current_total for group in actual) == comparison.current.amount(Kind.EXPENSE, "食費")
    assert sum(group.change.amount for group in actual) == comparison.change.amount


def test_alignment_uses_exact_names_without_guessing_prefixes() -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容",)
    previous = parse_csv(csv_bytes([["1", "2026/09/02", "-100", "食費", "0", "a", "同じ店"]], headers=headers))
    current = parse_csv(csv_bytes([["1", "2026/10/05", "-100", "食費", "0", "b", "VISA 同じ店"]], headers=headers))
    comparison = compare(previous, current, Kind.EXPENSE)
    expected = {"同じ店": (100, 0), "VISA 同じ店": (0, 100)}
    # WHEN
    actual = comparison.details("食費")
    # THEN
    assert {group.description: (group.previous_total, group.current_total) for group in actual} == expected


def test_alignment_keeps_income_and_expenses_separate() -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容",)
    previous = parse_csv(csv_bytes([["1", "2026/09/02", "-100", "食費", "0", "a", "同じ店"]], headers=headers))
    current = parse_csv(csv_bytes([["1", "2026/10/05", "100", "食費", "0", "b", "同じ店"]], headers=headers))
    comparison = compare(previous, current, Kind.INCOME)
    expected = (DescriptionComparison("同じ店", (), (Transaction(date(2026, 10, 5), Kind.INCOME, "食費", 100, "同じ店"),)),)
    # WHEN
    actual = comparison.details("食費")
    # THEN
    assert actual == expected


def test_alignment_for_absent_category_is_empty(detailed_month: Month) -> None:
    # GIVEN
    current = parse_csv(csv_bytes([["1", "2026/10/01", "-1", "食費", "0", "a"]]))
    comparison = compare(detailed_month, current, Kind.EXPENSE)
    expected = ()
    # WHEN
    actual = comparison.details("存在しないカテゴリ")
    # THEN
    assert actual == expected


def test_modal_renders_matching_names_in_one_shared_group(tmp_path: Path) -> None:
    # GIVEN
    headers = tuple(HEADERS) + ("内容", "中項目", "メモ")
    (tmp_path / "september.csv").write_bytes(csv_bytes([
        ["1", "2026/09/02", "-100", "食費", "0", "a", "同じ店", "食料品", "先月のメモ"],
        ["1", "2026/09/03", "-200", "食費", "0", "b", "同じ店", "食料品", "2回目"],
    ], headers=headers))
    (tmp_path / "october.csv").write_bytes(csv_bytes([
        ["1", "2026/10/05", "-500", "食費", "0", "c", "同じ店", "食料品", "今月のメモ"],
    ], headers=headers))
    client = create_app(tmp_path).test_client()
    # WHEN
    response = client.get("/")
    # THEN
    assert response.status_code == 200
    assert response.text.count('<section class="matched-group"') == 1
    assert response.text.count('<section class="paired-month"') == 2
    assert response.text.count("<h4>同じ店</h4>") == 1
    assert all(value in response.text for value in ["300円", "500円", "200円増", "先月のメモ", "今月のメモ", "2回目", "2026/09/02", "2026/09/03", "2026/10/05"])
