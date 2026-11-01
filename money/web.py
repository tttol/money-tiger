"""Flask routes and local-only HTTP boundaries for household comparisons."""

from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, abort, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from money.charts import render_png
from money.csv_source import CsvError, MAX_BYTES
from money.domain import Kind, compare
from money.repository import CsvRepository, default_pair

KINDS = {"expense": Kind.EXPENSE, "income": Kind.INCOME}


def create_app(data_directory: Path | None = None) -> Flask:
    """Compose the local file repository and web adapter; no external services."""
    app = Flask(__name__)
    repository = CsvRepository(data_directory or Path(__file__).resolve().parents[1] / "money_forward_csv")
    app.config.update(MAX_CONTENT_LENGTH=MAX_BYTES + 1024 * 1024, TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"])
    app.jinja_env.filters["yen"] = lambda amount: f"{amount:,}"

    @app.before_request
    def local_boundary() -> None:
        """Reject non-loopback clients and cross-origin browser requests."""
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            abort(403)
        origin = request.headers.get("Origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403)
        if origin and urlsplit(origin).netloc != request.host:
            abort(403)

    @app.after_request
    def local_headers(response: Response) -> Response:
        """Keep financial responses uncached and all page resources local."""
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def page(error: str | None = None, status: int = 200) -> tuple[str, int]:
        catalog = repository.catalog()
        previous_default, current_default = default_pair(catalog)
        previous = request.args.get("previous", previous_default)
        current = request.args.get("current", current_default)
        kind_key = request.args.get("kind", "expense")
        comparison = None
        selected_kind = KINDS.get(kind_key)
        try:
            if selected_kind is None:
                raise CsvError("表示区分は支出または収入を選んでください。")
            if previous and current:
                comparison = compare(repository.get(previous).month, repository.get(current).month, selected_kind)
        except (CsvError, ValueError, OSError) as exc:
            error = str(exc) if isinstance(exc, ValueError) else "CSVファイルを読み取れません。"
            status = 400
        return render_template("index.html", catalog=catalog, previous=previous, current=current, comparison=comparison, kind_key=kind_key, selected_kind=selected_kind, error=error), status

    @app.get("/")
    def index() -> tuple[str, int]:
        """Display the latest pair or the user's explicitly selected months."""
        return page()

    @app.post("/csv")
    def upload() -> Response | tuple[str, int]:
        """Import a valid monthly CSV and redirect to the refreshed comparison."""
        file = request.files.get("csv")
        if file is None or not file.filename or not file.filename.lower().endswith(".csv"):
            return page("追加するCSVファイルを選んでください。", 400)
        try:
            repository.add(file.stream.read(MAX_BYTES + 1))
        except (CsvError, OSError) as exc:
            message = str(exc) if isinstance(exc, CsvError) else "CSVを保存できません。フォルダの書き込み権限を確認してください。"
            return page(message, 400)
        return redirect(url_for("index"), code=303)

    @app.get("/download/<kind_key>.png")
    def download(kind_key: str) -> Response:
        """Generate an image from the current CSVs without writing a report file."""
        if kind_key not in KINDS:
            abort(404)
        try:
            a = repository.get(request.args.get("previous", "")).month
            b = repository.get(request.args.get("current", "")).month
            comparison = compare(a, b, KINDS[kind_key])
            output = render_png(comparison)
        except (CsvError, ValueError) as exc:
            return Response(str(exc), status=400, content_type="text/plain; charset=utf-8")
        except OSError:
            return Response("PNGを生成できません。CSVと日本語フォントを確認してください。", status=400, content_type="text/plain; charset=utf-8")
        return send_file(output, mimetype="image/png", as_attachment=True, download_name=f"{kind_key}_{a.period}_{b.period}.png")

    @app.errorhandler(RequestEntityTooLarge)
    def oversized_upload(_error: RequestEntityTooLarge) -> tuple[str, int]:
        """Render a useful message instead of Flask's generic HTML upload error."""
        return page("CSVは10MB以下にしてください。", 413)

    return app
