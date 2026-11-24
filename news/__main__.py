"""Run News Forum: python -m news [--no-browser] [--send-prices]"""
import argparse
import os
import socket
import sys
import threading
import webbrowser

import uvicorn

from . import config
from .server import create_app
from .telegram import PriceNotifier, send_prices

LOG_PATH = config.ROOT / "data" / "news-forum.log"
LOG_MAX_BYTES = 1_000_000


def already_running(host: str, port: int) -> bool:
    """True when something is already listening on host:port (e.g. a second launch)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def use_log_file_if_windowless() -> None:
    """Under pythonw.exe there is no console (sys.stdout is None); send output to a log file."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
        LOG_PATH.replace(LOG_PATH.with_suffix(".log.old"))
    log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m news")
    parser.add_argument("--no-browser", action="store_true",
                        help="start the server without opening a browser tab (used at Windows login)")
    parser.add_argument("--send-prices", action="store_true",
                        help="send the Telegram price message once now and exit (to test the .env settings)")
    args = parser.parse_args(argv)

    use_log_file_if_windowless()
    if args.send_prices:
        print(f"Telegram prices: {send_prices()}", flush=True)
        return
    url = f"http://{config.HOST}:{config.PORT}/"
    if already_running(config.HOST, config.PORT):
        print(f"News Forum is already running at {url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return

    app = create_app(config.FEEDS_PATH, config.DB_PATH)
    if not (args.no_browser or os.environ.get("NEWS_NO_BROWSER")):
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    PriceNotifier().start()
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
