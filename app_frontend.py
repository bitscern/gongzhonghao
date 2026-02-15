"""Streamlit frontend for controlling the Web3 assistant worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

STATUS_FILE = Path("status.json")
DATABASE_FILE = Path("database.json")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        st.warning(f"{path.name} 内容损坏，已回退到默认值。")
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default


def load_status() -> dict[str, Any]:
    return _read_json(STATUS_FILE, {"is_running": False})


def save_status(is_running: bool) -> None:
    STATUS_FILE.write_text(
        json.dumps({"is_running": is_running}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_database() -> dict[str, Any]:
    return _read_json(DATABASE_FILE, {"last_fetch_time": None, "articles": []})


def render_dashboard() -> None:
    st.set_page_config(page_title="Web3 资讯助手", page_icon="📰", layout="wide")
    st.title("📰 Web3 外媒资讯助手控制台")

    status = load_status()
    current_state = bool(status.get("is_running", False))

    st.subheader("主开关")
    updated_state = st.toggle(
        "助手运行状态",
        value=current_state,
        help="开启后后端 worker 可根据 status.json 执行任务；关闭后暂停执行。",
    )

    if updated_state != current_state:
        save_status(updated_state)
        st.success(f"状态已更新：{'ON' if updated_state else 'OFF'}")

    st.divider()

    database = load_database()
    st.subheader("抓取与发布记录")

    last_fetch_time = database.get("last_fetch_time")
    st.caption(f"最近一次抓取时间：{last_fetch_time or '暂无记录'}")

    articles = database.get("articles", [])
    if not articles:
        st.info("当前还没有文章记录。")
        return

    table_rows = []
    for article in articles:
        table_rows.append(
            {
                "标题": article.get("title", ""),
                "评分": article.get("score", ""),
                "来源": article.get("source", ""),
                "发布时间": article.get("published_at", ""),
                "原文链接": article.get("url", ""),
            }
        )

    st.dataframe(table_rows, use_container_width=True)


if __name__ == "__main__":
    render_dashboard()
