# Project guidance

## Purpose and runtime

Money is a local-only household finance comparison app built with Python 3.12+, Flask, Jinja, and Pillow. See `README.md` for usage and the full CSV contract.

- Keep the application usable offline after dependency installation. Serve assets locally; preserve loopback-only binding, disabled debug execution, and the existing local request checks.
- Keep the user-facing interface and validation messages in Japanese.
- Use `uv` with `pyproject.toml` and `uv.lock`. Update both when dependencies change; avoid introducing a separate dependency manifest.

## Working commands

Run from the project root:

```sh
uv sync --locked
uv run --offline python app.py
uv run --offline python app.py --port 8766
uv run --offline python -m pytest
```

The default URL is `http://127.0.0.1:8765`. The alternate-port command is optional. Dependency installation may require network access; normal operation must not.

## Code ownership

- `app.py`: command-line startup and loopback binding.
- `money/domain.py`: monthly totals, comparison rules, percentage changes, and chart axis calculations. Keep these independent of Flask, files, and drawing libraries.
- `money/csv_source.py`: CSV decoding, row validation, and aggregation.
- `money/repository.py`: CSV discovery, safe local file access, upload storage, and default month selection.
- `money/charts.py`: PNG rendering and Japanese font discovery.
- `money/web.py`: application composition, HTTP validation, routes, and response headers.
- `money/templates/` and `money/static/`: browser presentation, including SVG charts.
- `tests/test_money.py`: parser, comparison, repository, and HTTP behavior tests.

Keep calculation changes in the shared domain/parser code so browser charts and PNG downloads continue to agree.

## Calculation and chart invariants

- Include only rows with `計算対象=1` and `振替=0`. Group by `大項目` and amount sign: negative amounts are expenses displayed as positive values; nonnegative amounts are income, including refunds.
- Preserve integer yen totals and decimal percentage calculations. Round only for display.
- Compare two distinct months in chronological order. Never automatically merge separate exports of the same month.
- A category absent from one month means zero yen. When the comparison base is zero, show the increase/decrease amount without inventing a percentage.
- Preserve thousand-yen vertical axes, zero baselines, and a shared scale for each category's two bars. Categories may use different scales.
- Keep the browser and PNG colors consistent: previous month gray; current increase orange, decrease blue, unchanged slate.
- Report source coverage and exclusions without implying that a CSV necessarily contains the complete month.

## Source data and verification

- `money_forward_csv/` contains private household data. Preserve original files and content-based upload deduplication. Keep CSVs and generated financial images out of version control and diagnostics.
- Use synthetic CSV fixtures and `tmp_path` for automated tests. Inject a temporary directory through `create_app(data_directory=...)` or `CsvRepository`; do not upload test data into the user's real CSV directory.
- For parser or calculation changes, verify encoding support, exclusions, absent categories, a zero comparison base, duplicate IDs, and invalid or mixed-month input as applicable.
- For presentation changes, check both browser charts and exported PNGs. Verify Japanese glyphs, readable labels, thousand-yen units, and layout at desktop and narrow widths. PNG rendering depends on a Japanese-capable local font; do not replace missing glyphs silently.
- Update `README.md` when startup commands, CSV acceptance rules, or user-visible behavior change.
