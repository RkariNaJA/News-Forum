"""Paths and settings for News Forum."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS_PATH = ROOT / "feeds.json"
DB_PATH = ROOT / "data" / "news.db"
WEB_DIR = ROOT / "web"

HOST = "127.0.0.1"
PORT = 8770

STALE_MINUTES = 30   # a feed is re-fetched on page open when older than this
KEEP_DAYS = 2        # calendar days in this PC's time zone: 2 = today and yesterday. Older stories are
                     # skipped and trimmed (saved ones stay)
CATEGORIES = ("world", "business", "markets", "asia", "tech")  # markets = Crypto & Investing tab, tech = AI tab
