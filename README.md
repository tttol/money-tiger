# Money

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

From the project directory, install dependencies and start the app:

```sh
uv sync --locked
uv run --offline python app.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in your browser.

Stop the app with `Ctrl+C`.

If the port is busy, use `uv run --offline python app.py --port 8766` and open port 8766 instead.
