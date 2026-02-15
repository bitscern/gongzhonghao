"""Backend worker: monitor status, fetch RSS, score via AI, persist high-score articles."""

import json
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import urlopen, Request
from xml.etree import ElementTree

from config import COINDESK_RSS, THEBLOCK_RSS
from ai_processor import score_article

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent
STATUS_PATH = PROJECT_ROOT / "status.json"
DATABASE_PATH = PROJECT_ROOT / "database.json"
CHECK_INTERVAL_SEC = 10

# Default cutoff when last_fetch_time is null (only fetch news from last 24h)
DEFAULT_CUTOFF_HOURS = 24


def _load_json(path: Path, default: dict) -> dict:
    """Load JSON file; return default if missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default.copy()


def _save_json(path: Path, data: dict) -> None:
    """Write JSON file atomically."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_rss_datetime(pub_date_str: str | None) -> datetime | None:
    """Parse RSS pubDate to timezone-aware datetime (UTC)."""
    if not pub_date_str or not pub_date_str.strip():
        return None
    try:
        dt = parsedate_to_datetime(pub_date_str.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _fetch_rss_items(url: str, after: datetime) -> list[dict]:
    """Fetch RSS from url and return items with pubDate > after. Each item: title, link, summary, published_at."""
    items: list[dict] = []
    try:
        req = Request(url, headers={"User-Agent": "RSSWorker/1.0"})
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return items

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return items

    # RSS 2.0: channel/item; Atom: feed/entry. Support with or without namespace.
    for node in root.iter():
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
        if tag != "item" and tag != "entry":
            continue
        title_el = node.find(".//{*}title") or node.find("title")
        link_el = node.find(".//{*}link") or node.find("link")
        desc_el = node.find(".//{*}description") or node.find("description") or node.find(".//{*}summary") or node.find("summary") or node.find(".//{*}content") or node.find("content")
        pub_el = node.find(".//{*}pubDate") or node.find("pubDate") or node.find(".//{*}published") or node.find("published") or node.find(".//{*}updated") or node.find("updated")

        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        if not link and link_el is not None:
            link = link_el.get("href", "")
        summary = (desc_el.text or "").strip() if desc_el is not None else ""
        if not summary and desc_el is not None and len(desc_el):
            summary = (ElementTree.tostring(desc_el, encoding="unicode", method="text") or "").strip()[:500]

        pub_dt = _parse_rss_datetime(pub_el.text if pub_el is not None else None)
        if pub_dt is None or pub_dt <= after:
            continue
        if not title:
            continue

        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published_at": pub_dt.isoformat(),
            "_dt": pub_dt,
        })
    return items


def _get_cutoff(last_fetch_time: str | None) -> datetime:
    """Return cutoff datetime: from last_fetch_time or default (now - 24h)."""
    if last_fetch_time:
        try:
            dt = datetime.fromisoformat(last_fetch_time.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc) - timedelta(hours=DEFAULT_CUTOFF_HOURS)


def run_task() -> None:
    """Run one fetch+score+store cycle: RSS -> score -> save articles with score > 80, update last_fetch_time."""
    try:
        _run_task_impl()
    except Exception:
        pass  # 防止网络波动等异常导致后端崩溃，本次跳过


def _run_task_impl() -> None:
    db = _load_json(DATABASE_PATH, {"last_fetch_time": None, "articles": []})
    last_fetch = db.get("last_fetch_time")
    articles: list = list(db.get("articles") or [])
    cutoff = _get_cutoff(last_fetch)

    all_items: list[dict] = []
    for url in (COINDESK_RSS, THEBLOCK_RSS):
        all_items.extend(_fetch_rss_items(url, cutoff))

    # Dedupe by link, keep newer pubDate
    by_link: dict[str, dict] = {}
    for it in all_items:
        key = (it.get("link") or "").strip() or it.get("title", "")
        if key and (key not in by_link or (it.get("_dt") and (by_link[key].get("_dt") or datetime.min.replace(tzinfo=timezone.utc)) < it["_dt"])):
            by_link[key] = it
    all_items = list(by_link.values())

    latest_time: datetime | None = None
    for it in all_items:
        pub_dt = it.get("_dt")
        if pub_dt:
            latest_time = pub_dt if latest_time is None else max(latest_time, pub_dt)

    for it in all_items:
        title = it.get("title", "")
        summary = it.get("summary", "")
        try:
            score = score_article(title, summary)
        except Exception:
            score = 0
        if score <= 80:
            continue
        articles.append({
            "title": it.get("title", ""),
            "link": it.get("link", ""),
            "summary": summary,
            "published_at": it.get("published_at", ""),
            "score": score,
        })

    new_last = latest_time.isoformat() if latest_time else last_fetch
    _save_json(DATABASE_PATH, {
        "last_fetch_time": new_last,
        "articles": articles,
    })


def main() -> None:
    """Loop: every 10s check status.json; if is_running flips False->True, run task once."""
    was_running = False
    while True:
        try:
            status = _load_json(STATUS_PATH, {"is_running": False})
            is_running = bool(status.get("is_running", False))

            if not is_running:
                was_running = False
                time.sleep(CHECK_INTERVAL_SEC)
                continue

            if is_running and not was_running:
                run_task()
            was_running = True
        except Exception:
            was_running = False
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
