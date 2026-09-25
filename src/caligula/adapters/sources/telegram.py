"""Public Telegram channels, read through Telegram's own public web preview
(https://t.me/s/<channel>), which needs no account.

Only public channels. Private groups and invite links are refused: joining a
closed group to collect its members' messages raises consent, data-protection
and platform-terms problems that a public-interest purpose does not cure (see
docs/legal.md). Forwarded messages keep their origin so that ten channels
reposting one message count as one source.
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from html.parser import HTMLParser

import httpx

from caligula.application.ports.sources import PrivateSourceError, TelegramPost

PREVIEW = "https://t.me/s/{channel}"
_CHANNEL = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def channel_name(ref: str) -> str:
    ref = ref.strip()
    if "joinchat" in ref or "/+" in ref or ref.startswith("+"):
        raise PrivateSourceError("invite links point to private groups or channels; only public channels are collected")
    name = re.sub(r"^(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?", "", ref).strip("@/").split("/")[0]
    if not _CHANNEL.match(name):
        raise ValueError(f"not a public channel name: {ref!r}")
    return name


class _Parser(HTMLParser):
    """Collects message blocks from the preview page's markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.posts: list[dict] = []
        self._depth = 0
        self._text_depth: int | None = None
        self._fwd_depth: int | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "div":
            self._depth += 1
        if tag == "div" and "tgme_widget_message " in cls + " " and a.get("data-post"):
            self.posts.append({"post": a["data-post"], "text": [], "time": None, "fwd": []})
        if not self.posts:
            return
        if tag == "div" and "tgme_widget_message_text" in cls and self._text_depth is None:
            self._text_depth = self._depth
        if "tgme_widget_message_forwarded_from_name" in cls:
            self._fwd_depth = self._depth
        if tag == "time" and a.get("datetime") and self.posts[-1]["time"] is None:
            self.posts[-1]["time"] = a["datetime"]
        if tag == "br" and self._text_depth is not None:
            self.posts[-1]["text"].append("\n")

    def handle_endtag(self, tag):
        if tag == "div":
            if self._text_depth == self._depth:
                self._text_depth = None
            self._depth -= 1
        if tag in ("a", "span") and self._fwd_depth is not None:
            self._fwd_depth = None

    def handle_data(self, data):
        if not self.posts:
            return
        if self._text_depth is not None:
            self.posts[-1]["text"].append(data)
        elif self._fwd_depth is not None:
            self.posts[-1]["fwd"].append(data)


def parse_preview(html: str) -> list[TelegramPost]:
    p = _Parser()
    p.feed(html)
    out = []
    for raw in p.posts:
        channel, _, post_id = raw["post"].partition("/")
        if not post_id.isdigit():
            continue
        out.append(TelegramPost(
            channel=channel,
            post_id=int(post_id),
            url=f"https://t.me/{channel}/{post_id}",
            posted_at=datetime.fromisoformat(raw["time"]) if raw["time"] else None,
            text=unescape("".join(raw["text"])).strip(),
            forwarded_from="".join(raw["fwd"]).strip() or None,
        ))
    return out


class TelegramClient:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def fetch(self, ref: str, before: int | None = None) -> tuple[str, bytes, list[TelegramPost]]:
        """Most recent public posts of a channel (about 20 per page); `before` pages back."""
        channel = channel_name(ref)
        resp = self.http.get(PREVIEW.format(channel=channel), params={"before": before} if before else None)
        resp.raise_for_status()
        return str(resp.url), resp.content, parse_preview(resp.text)
