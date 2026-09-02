"""Document attachment loading shared by chat and the ``file_view`` tool."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from markdownify import markdownify
from pydantic_ai import BinaryContent
from pypdf import PdfReader

from hoshino import data_dir
from hoshino.ai import media
from hoshino.ai.net import is_private_host
from hoshino.ai.tools.computer.runtime import computer_workdir

MAX_FILE_BYTES = 15 * 1024 * 1024
INLINE_MAX_CHARS = 24_000
_TEXT_EXTENSIONS = {
    ".csv",
    ".ini",
    ".json",
    ".log",
    ".markdown",
    ".md",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_HTML_EXTENSIONS = {".htm", ".html", ".xhtml"}
_IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


@dataclass(frozen=True, slots=True)
class ReadDocument:
    name: str
    path: Path
    size: int
    text: str | None = None
    image: BinaryContent | None = None


def _safe_name(name: str, default: str = "file.bin") -> str:
    name = Path(unquote(name)).name
    name = re.sub(r"[^\w.()\[\] -]+", "_", name).strip(" .")
    return name or default


def _attachment_path(name: str, identity: str) -> Path:
    root = data_dir / "ai_attachments"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    return root / f"{digest}_{_safe_name(name)}"


def _allowed_local_path(path: str | Path, config, deps=None) -> Path:
    candidate = Path(path).expanduser().resolve()
    roots = (
        (data_dir / "ai_attachments").resolve(),
        Path(computer_workdir(config, deps)).resolve(),
    )
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise ValueError("路径不在允许的附件目录或工作目录内。")
    return candidate


async def _save_response(response: httpx.Response, path: Path) -> None:
    response.raise_for_status()
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_BYTES:
        raise ValueError("文件超过 15MB 限制。")
    with path.open("wb") as output:
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise ValueError("文件超过 15MB 限制。")
            output.write(chunk)


async def _download(url: str, *, config, name: str | None = None) -> Path:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅支持 http/https 文件 URL。")
    if await is_private_host(parsed.hostname):
        raise ValueError("拒绝访问私有/内网地址。")

    filename = _safe_name(name or Path(unquote(parsed.path)).name)
    path = _attachment_path(filename, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
        return path

    proxy = getattr(config, "proxy", None) if getattr(config, "tool_use_proxy", False) else None
    try:
        async with (
            httpx.AsyncClient(
                trust_env=False,
                verify=config.web_fetch_verify_ssl,
                proxy=proxy,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            ) as client,
            client.stream("GET", url) as response,
        ):
            await _save_response(response, path)
    except (httpx.HTTPError, ValueError):
        path.unlink(missing_ok=True)
        raise
    return path


async def _write_raw(raw: bytes, name: str) -> Path:
    path = _attachment_path(name, hashlib.sha256(raw).hexdigest())
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("文件超过 15MB 限制。")
    if not path.exists():
        await asyncio.to_thread(path.write_bytes, raw)
    return path


async def _source_path(source, *, config, deps=None) -> tuple[Path, str]:
    if isinstance(source, str | Path):
        value = str(source)
        if value.startswith(("http://", "https://")):
            return await _download(value, config=config), _safe_name(
                Path(urlparse(value).path).name
            )
        path = _allowed_local_path(source, config, deps)
        return path, path.name

    raw = getattr(source, "raw", None)
    if raw:
        if hasattr(raw, "getvalue"):
            raw = raw.getvalue()
        name = _safe_name(getattr(source, "name", "file.bin"))
        return await _write_raw(raw, name), name

    path = getattr(source, "path", None)
    if path:
        resolved = _allowed_local_path(path, config, deps)
        return resolved, _safe_name(getattr(source, "name", resolved.name))

    url = (getattr(source, "url", None) or "").strip()
    if url:
        name = _safe_name(getattr(source, "name", "file.bin"))
        return await _download(url, config=config, name=name), name
    raise ValueError("文件没有可用的 path、url 或 raw 数据；平台可能无法下载此文件。")


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _read_path(path: Path, name: str, mimetype: str | None = None) -> ReadDocument:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError("文件超过 15MB 限制。")
    raw = path.read_bytes()
    suffix = Path(name).suffix.lower() or path.suffix.lower()
    guessed_type = (mimetype or mimetypes.guess_type(name)[0] or "").lower()
    if suffix == ".pdf" or guessed_type == "application/pdf":
        text = _read_pdf(path)
    elif suffix in _IMAGE_EXTENSIONS or guessed_type.startswith("image/"):
        compressed = media.compress_image_bytes(raw)
        image = BinaryContent(data=compressed, media_type="image/jpeg")
        return ReadDocument(name=name, path=path, size=size, image=image)
    else:
        text = _decode_text(raw)
        if suffix in _HTML_EXTENSIONS or guessed_type in {"text/html", "application/xhtml+xml"}:
            text = markdownify(text)
    return ReadDocument(name=name, path=path, size=size, text=text.strip())


async def read_document(source, *, config, deps=None, mimetype: str | None = None) -> ReadDocument:
    """Download or read one supported file and parse it without blocking the loop."""
    path, name = await _source_path(source, config=config, deps=deps)
    return await asyncio.to_thread(
        _read_path, path, name, mimetype or getattr(source, "mimetype", None)
    )


def _line_window(text: str, start_line: int | None, end_line: int | None) -> str:
    if start_line is None and end_line is None:
        return text
    start = max(1, start_line or 1)
    end = max(start, end_line or start + 199)
    lines = text.splitlines()
    return "\n".join(f"{index}: {line}" for index, line in enumerate(lines[start - 1 : end], start))


async def file_view(
    source: str,
    *,
    config,
    deps=None,
    start_line: int | None = None,
    end_line: int | None = None,
):
    """Read a supported local path or HTTP(S) URL; images are native model content."""
    document = await read_document(source, config=config, deps=deps)
    if document.image is not None:
        return document.image
    return _line_window(document.text or "（空内容）", start_line, end_line)


async def file_segments_to_prompt(segments, *, config) -> tuple[str, list[BinaryContent]]:
    """Turn incoming files into inline text/image parts or file_view hints."""
    text_parts: list[str] = []
    image_parts: list[BinaryContent] = []
    for segment in segments:
        name = _safe_name(getattr(segment, "name", "file.bin"))
        try:
            document = await read_document(segment, config=config)
        except Exception as exc:
            text_parts.append(f"[文件 {name}]\n读取失败：{type(exc).__name__}。")
            continue
        if document.image is not None:
            text_parts.append(f"[文件 {name}]\n这是一个图片文件，请直接查看附件内容。")
            image_parts.append(document.image)
        elif document.text is not None and len(document.text) <= INLINE_MAX_CHARS:
            text_parts.append(f"[文件 {name}]\n{document.text or '（空内容）'}")
        else:
            text_parts.append(
                f"[文件 {name}] 内容较长，已保存到 `{document.path}`；需要细节时请使用 file_view。"
            )
    return "\n\n".join(text_parts), image_parts


__all__ = [
    "INLINE_MAX_CHARS",
    "MAX_FILE_BYTES",
    "ReadDocument",
    "file_segments_to_prompt",
    "file_view",
    "read_document",
]
