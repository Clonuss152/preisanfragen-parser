from __future__ import annotations

import html
import re
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path

from .models import EmailData


class _HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "li", "tr", "table", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return html.unescape("".join(self.parts))


_QUOTE_PATTERNS = [
    re.compile(r"(?im)^\s*-{2,}\s*(?:original message|ursprüngliche nachricht)\s*-{2,}\s*$"),
    re.compile(r"(?im)^\s*(?:from|von):\s+.+$"),
    re.compile(r"(?im)^\s*on\s+.+\s+wrote:\s*$"),
    re.compile(r"(?im)^\s*am\s+.+\s+schrieb\s+.+:\s*$"),
]

_SIGNATURE_PATTERNS = [
    re.compile(r"(?im)^\s*--\s*$"),
    re.compile(r"(?im)^\s*(?:mit freundlichen grüßen|freundliche grüße|viele grüße|beste grüße)\s*[,!]*\s*$"),
    re.compile(r"(?im)^\s*(?:kind regards|best regards|regards|sincerely)\s*[,!]*\s*$"),
]

_DISCLAIMER_PATTERNS = [
    re.compile(r"(?im)^\s*(?:diese e-?mail|this e-?mail).{0,120}(?:vertraulich|confidential).*$"),
    re.compile(r"(?im)^\s*(?:achtung|notice):.{0,120}(?:vertraulich|confidential).*$"),
]


def _html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return parser.text()


def _part_text(part: Message) -> str:
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        content = payload.decode(charset, errors="replace")
    return str(content)


def _extract_body_and_attachments(message: Message) -> tuple[str, list[str]]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            disposition = part.get_content_disposition()
            if filename or disposition == "attachment":
                attachments.append(filename or "unnamed-attachment")
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(_part_text(part))
            elif content_type == "text/html":
                html_parts.append(_html_to_text(_part_text(part)))
    else:
        content_type = message.get_content_type()
        value = _part_text(message)
        if content_type == "text/html":
            html_parts.append(_html_to_text(value))
        else:
            plain_parts.append(value)

    body = "\n".join(part for part in plain_parts if part.strip())
    if not body.strip():
        body = "\n".join(part for part in html_parts if part.strip())
    return body, attachments


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\xa0]+", " ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n[ ]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_quoted_history(text: str) -> tuple[str, str]:
    positions: list[int] = []
    for pattern in _QUOTE_PATTERNS:
        for match in pattern.finditer(text):
            # Avoid treating a header-like first line as quoted history.
            if match.start() >= 30:
                positions.append(match.start())
    if not positions:
        return text, ""
    cut = min(positions)
    return text[:cut].strip(), text[cut:].strip()


def _remove_signature_and_disclaimer(text: str) -> str:
    positions: list[int] = []
    for pattern in _SIGNATURE_PATTERNS + _DISCLAIMER_PATTERNS:
        for match in pattern.finditer(text):
            if match.start() >= 30:
                positions.append(match.start())
    if positions:
        text = text[: min(positions)]
    return _normalize(text)


def parse_eml(path: Path) -> EmailData:
    with path.open("rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle)

    sender_name, sender_email = parseaddr(str(message.get("From", "")))
    sender_email = sender_email.lower().strip() or None
    sender_domain = sender_email.rsplit("@", 1)[1] if sender_email and "@" in sender_email else None
    subject = _normalize(str(message.get("Subject", "")))
    raw_body, attachments = _extract_body_and_attachments(message)
    normalized = _normalize(raw_body)
    current, history = _split_quoted_history(normalized)
    current = _remove_signature_and_disclaimer(current)

    return EmailData(
        source_path=str(path),
        message_id=str(message.get("Message-ID")) if message.get("Message-ID") else None,
        sender_name=sender_name or None,
        sender_email=sender_email,
        sender_domain=sender_domain,
        subject=subject,
        current_body=current,
        quoted_history=history,
        attachment_names=attachments,
    )


def parse_txt(path: Path) -> EmailData:
    text = path.read_text(encoding="utf-8", errors="replace")
    current, history = _split_quoted_history(_normalize(text))
    current = _remove_signature_and_disclaimer(current)
    return EmailData(
        source_path=str(path),
        message_id=None,
        sender_name=None,
        sender_email=None,
        sender_domain=None,
        subject=path.stem,
        current_body=current,
        quoted_history=history,
        attachment_names=[],
    )


def parse_email_file(path: Path) -> EmailData:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        return parse_eml(path)
    if suffix == ".txt":
        return parse_txt(path)
    raise ValueError(f"Unsupported file type: {suffix}. Use .eml or .txt")
