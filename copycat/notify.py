"""Discord webhook 發送層(泛用訊息;訊號內容由 caller 決定).

介面形狀沿 treading-king discord_notifier / alerts:keyword-only、URL 未設即 no-op、
never-raise(通知失敗不可炸 caller);傳輸為 stdlib urllib 同步實作。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_ENV_KEY = "DISCORD_WEBHOOK_URL"
_TIMEOUT = 5.0
_RETRY_AFTER_CAP = 5.0
# Discord embed 硬限制
_MAX_DESCRIPTION = 4096
_MAX_FIELDS = 25
_MAX_FIELD_NAME = 256
_MAX_FIELD_VALUE = 1024

_WEBHOOK_URL: str | None = None
_URL_RESOLVED: bool = False


def resolve_webhook_url() -> str | None:
    """讀取順序:env → repo root .env → None(lazy cache;測試 reset module 屬性)."""
    global _WEBHOOK_URL, _URL_RESOLVED
    if _URL_RESOLVED:
        return _WEBHOOK_URL
    url = os.environ.get(_ENV_KEY, "").strip()
    if not url:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == _ENV_KEY and value.strip():
                    url = value.strip()
                    break
    _WEBHOOK_URL = url or None
    _URL_RESOLVED = True
    return _WEBHOOK_URL


def _build_embed(message: str, title: str | None, fields: dict[str, str] | None) -> dict:
    embed: dict = {
        "title": title if title is not None else "copycat",
        "description": message[:_MAX_DESCRIPTION],
    }
    if fields:
        embed["fields"] = [
            {"name": str(name)[:_MAX_FIELD_NAME], "value": str(value)[:_MAX_FIELD_VALUE]}
            for name, value in list(fields.items())[:_MAX_FIELDS]
        ]
    return embed


def _post(url: str, data: bytes) -> bool:
    """單次 POST;429 拋回 caller 決定重試,其餘非 2xx 記 log 回 False."""
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=_TIMEOUT) as resp:
        status = int(getattr(resp, "status", 0) or 0)
    if 200 <= status < 300:
        return True
    logger.error("Discord webhook 非 2xx:%s", status)
    return False


def notify_discord(
    message: str,
    *,
    title: str | None = None,
    fields: dict[str, str] | None = None,
) -> bool:
    """送一則 embed 訊息到 Discord webhook;URL 未設 no-op、失敗不拋例外.

    回傳 True = Discord 已收(2xx);False = 未設定或發送失敗(細節在 log)。
    """
    url = resolve_webhook_url()
    if url is None:
        logger.info("DISCORD_WEBHOOK_URL 未設定,略過 Discord 通知")
        return False
    data = json.dumps({"embeds": [_build_embed(message, title, fields)]}).encode("utf-8")
    try:
        try:
            return _post(url, data)
        except HTTPError as e:
            if e.code != 429:
                logger.error(
                    "Discord webhook 拒絕:%s %s", e.code, e.read()[:200].decode("utf-8", "replace")
                )
                return False
            try:
                delay = float(e.headers.get("Retry-After", "1"))
            except ValueError:
                delay = 1.0
            sleep(min(delay, _RETRY_AFTER_CAP))
            try:
                return _post(url, data)
            except HTTPError as e2:
                logger.error("Discord webhook 重試仍失敗:%s", e2.code)
                return False
    # TimeoutError 獨立列:SSL read timeout 不包在 URLError(CLAUDE.md §8)
    except (URLError, TimeoutError, OSError) as e:
        logger.warning("Discord webhook 連線失敗:%s", e)
        return False
