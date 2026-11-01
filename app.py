"""Start the application on this computer's loopback interface only."""

import argparse

from money.web import create_app


def main() -> None:
    """Run the local server; debug execution and network exposure stay disabled."""
    parser = argparse.ArgumentParser(description="ローカル家計グラフ")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("ポート番号は1〜65535で指定してください。")
    app = create_app()
    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
