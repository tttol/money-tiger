"""Render category comparisons as downloadable PNGs without external services."""

from dataclasses import dataclass
from io import BytesIO
from math import ceil
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont

from money.domain import CategoryComparison, Comparison, Kind

BACKGROUND = "#F4F6F8"
TEXT = "#172B40"
MUTED = "#536477"
GRID = "#E2E8EE"
PREVIOUS = "#A1AFBF"
COLORS = {"more": "#C65B21", "less": "#1675A8", "same": "#56677B"}


def japanese_fonts() -> tuple[Path, Path]:
    """Find Japanese-capable fonts on macOS, or locally installed Noto/IPA fonts."""
    mac = Path("/System/Library/Fonts")
    if mac.is_dir():
        names = {unicodedata.normalize("NFC", path.name): path for path in mac.iterdir()}
        regular = names.get("ヒラギノ角ゴシック W3.ttc")
        bold = names.get("ヒラギノ角ゴシック W6.ttc")
        if regular and bold:
            return regular, bold
    pairs = (
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        ("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"),
        ("C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/meiryob.ttc"),
    )
    for regular, bold in pairs:
        if Path(regular).is_file() and Path(bold).is_file():
            return Path(regular), Path(bold)
    raise OSError("PNG出力用の日本語フォントがありません。Noto Sans CJKをインストールしてください。")


@dataclass
class Canvas:
    """Keep raster drawing coordinates in logical pixels at a fixed 2× density."""

    image: Image.Image
    draw: ImageDraw.ImageDraw
    fonts: tuple[Path, Path]
    scale: int = 2

    def text(self, x: float, y: float, value: str, size: int = 18, color: str = TEXT, bold: bool = False, anchor: str | None = None) -> None:
        """Draw Japanese text with an explicit size, color and optional anchor."""
        font = ImageFont.truetype(str(self.fonts[int(bold)]), size * self.scale)
        self.draw.text((round(x * self.scale), round(y * self.scale)), value, font=font, fill=color, anchor=anchor)

    def box(self, xy: tuple[float, float, float, float], fill: str, radius: int = 0) -> None:
        """Draw a filled rectangle or rounded panel at logical coordinates."""
        points = tuple(round(v * self.scale) for v in xy)
        self.draw.rounded_rectangle(points, radius=radius * self.scale, fill=fill)

    def line(self, xy: tuple[float, float, float, float], fill: str = GRID, width: int = 1) -> None:
        """Draw a grid line or visible zero-value marker."""
        self.draw.line(tuple(round(v * self.scale) for v in xy), fill=fill, width=width * self.scale)


def render_png(comparison: Comparison) -> BytesIO:
    """Create the same paired-bar overview as the browser, using exact yen totals."""
    if not comparison.categories:
        raise ValueError("この区分にはグラフ化する明細がありません。")
    columns = min(3, len(comparison.categories))
    rows = ceil(len(comparison.categories) / columns)
    width, padding, gap, panel_height, start_y = 1600, 44, 22, 360, 282
    panel_width = (width - padding * 2 - gap * (columns - 1)) / columns
    height = start_y + rows * (panel_height + gap) + 114
    image = Image.new("RGB", (width * 2, height * 2), BACKGROUND)
    canvas = Canvas(image, ImageDraw.Draw(image), japanese_fonts())
    a, b = comparison.previous, comparison.current
    canvas.text(padding, 28, f"カテゴリ別{comparison.kind}の比較", 34, bold=True)
    canvas.text(padding, 82, f"{a.label}（比較元）と{b.label}（比較先）", 22, MUTED)
    canvas.text(padding, 130, f"{comparison.kind}合計   {a.label} {a.amount(comparison.kind):,}円    →    {b.label} {b.amount(comparison.kind):,}円", 22, bold=True)
    canvas.text(padding, 168, f"比較元比 {comparison.change.label}  ({comparison.change.rate_label})", 20, COLORS[comparison.change.tone], True)
    for index, (fill, label) in enumerate(((PREVIOUS, "比較元"), (COLORS["more"], "比較先：増加"), (COLORS["less"], "比較先：減少"), (COLORS["same"], "比較先：同額"))):
        x = padding + index * 245
        canvas.box((x, 226, x + 18, 244), fill, 3)
        canvas.text(x + 28, 222, label, 18, MUTED)
    for index, category in enumerate(comparison.categories):
        _panel(canvas, padding + index % columns * (panel_width + gap), start_y + index // columns * (panel_height + gap), panel_width, panel_height, category, comparison)
    footer_y = start_y + rows * (panel_height + gap) + 1
    canvas.text(padding, footer_y, "集計：大項目別。計算対象=1・振替=0の明細のみ。支出は正の金額で表示。", 16, MUTED)
    canvas.text(padding, footer_y + 28, "縦軸：千円単位。カテゴリごとに縮尺を調整。同カテゴリの2か月は同一縮尺。明細なしは0円。", 16, MUTED)
    canvas.text(padding, footer_y + 56, f"最終明細日：比較元 {a.last_date:%Y/%m/%d} ／ 比較先 {b.last_date:%Y/%m/%d}。CSVに記録された金額を比較。", 16, MUTED)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _panel(canvas: Canvas, x: float, y: float, width: float, height: float, category: CategoryComparison, comparison: Comparison) -> None:
    canvas.box((x, y, x + width, y + height), "white", 12)
    label = f"{category.category}（入金）" if comparison.kind == Kind.INCOME and category.category == "未分類" else category.category
    canvas.text(x + 24, y + 18, label, 24, bold=True)
    canvas.text(x + 24, y + 56, f"比較元比 {category.change.label}  ({category.change.rate_label})", 16, COLORS[category.change.tone], True)
    canvas.text(x + 24, y + 94, "千円", 14, MUTED)
    left, right, base, plot_height = x + 78, x + width - 26, y + height - 46, height - 173
    for tick in category.ticks:
        tick_y = base - tick / category.top * plot_height
        canvas.line((left, tick_y, right, tick_y))
        canvas.text(left - 12, tick_y, f"{tick:,}", 15, MUTED, anchor="rm")
    for index, (value, fill, month) in enumerate(((category.previous, PREVIOUS, comparison.previous), (category.current, COLORS[category.change.tone], comparison.current))):
        center = left + (right - left) * (0.29 if index == 0 else 0.75)
        bar_top = base - value / 1000 / category.top * plot_height
        if value:
            canvas.box((center - 40, bar_top, center + 40, base), fill)
        else:
            canvas.line((center - 40, base - 1, center + 40, base - 1), fill, 3)
        canvas.text(center, bar_top - 10, f"{value:,}円", 17, bold=True, anchor="mb")
        canvas.text(center, base + 12, month.label, 16, MUTED, anchor="mt")
