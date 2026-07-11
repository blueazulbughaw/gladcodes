"""Markdown -> sanitized HTML for journal posts (and, later, tutorials).
Never render markdown.markdown() output directly — always through bleach.
"""
import re

import bleach
import markdown

ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "u", "s", "del",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "*": ["class"],
}


def render_markdown(text: str) -> str:
    html = markdown.markdown(text or "", extensions=["fenced_code", "tables"])
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)


def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


YOUTUBE_ID_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([a-zA-Z0-9_-]{11})")


def youtube_embed_url(url: str):
    """Accepts any common YouTube URL shape (watch/short-link/embed/shorts)
    and returns an embeddable https://www.youtube.com/embed/<id> URL, or
    None if it doesn't look like a YouTube URL at all."""
    if not url:
        return None
    match = YOUTUBE_ID_RE.search(url)
    return f"https://www.youtube.com/embed/{match.group(1)}" if match else None
