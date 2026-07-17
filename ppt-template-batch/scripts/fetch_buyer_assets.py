from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import os
import re
import socket
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote_to_bytes, urljoin, urlparse

from PIL import Image

from env_utils import get_env_var
from image_layout_utils import prepare_site_image


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
PAGE_HINTS = [
    "product",
    "products",
    "solution",
    "solutions",
    "application",
    "applications",
    "industry",
    "industries",
    "equipment",
    "services",
    "about",
    "company",
    "portfolio",
    "project",
    "projects",
]
PRODUCT_HINTS = [
    "product",
    "products",
    "solution",
    "industry",
    "application",
    "equipment",
    "gear",
    "motor",
    "bearing",
    "drive",
    "power",
    "hydrogen",
    "solar",
    "wind",
    "mining",
    "transmission",
]
SOCIAL_SOURCES = [
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
]
MAP_HINTS = ["google.com", "maps.app.goo.gl"]
LOGO_HINTS = ["logo", "brand", "identity"]
LOGO_REJECT_HINTS = [
    "sale", "noti", "certificate", "certification", "award", "government",
    "bo-cong", "dang-ky", "registered", "registration", "seal", "badge",
    "trust", "verify", "validation", "compliance", "license", "licence",
    "hero", "banner", "homepage", "preview", "watermark", "captcha",
]
SCREENSHOT_HINTS = ["screenshot", "screen", "homepage", "website"]
MAX_PAGE_CANDIDATES = 10
MIN_IMAGE_BYTES = 5 * 1024
MIN_LOGO_BYTES = 512
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = MAX_IMAGE_BYTES
MIN_VISUAL_WIDTH = 240
MIN_VISUAL_HEIGHT = 140
MIN_LOGO_WIDTH = 60
MIN_LOGO_HEIGHT = 20
BROWSER_VIEWPORT_WIDTH = 1440
BROWSER_VIEWPORT_HEIGHT = 1080
BROWSER_WAIT_MS = 1200
BROWSER_PAGE_LIMIT = 6
FETCH_TIMEOUT_SECONDS = 8
MAX_REDIRECT_HOPS = 5
ASSET_LOGIC_VERSION = 4
LOGO_MIN_SCORE = 10
FETCH_DEADLINE: float | None = None


@dataclass
class AssetCandidate:
    src: str
    page: str
    kind: str
    alt: str = ""
    cls: str = ""
    score: int = 0
    origin: str = "official"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return text or "buyer"


def candidate_base_urls(domain: str) -> list[str]:
    clean = domain.strip().rstrip("/")
    clean = re.sub(r"^https?://", "", clean, flags=re.I)
    return [f"https://{clean}", f"http://{clean}"]


def _hostname_without_www(hostname: str) -> str:
    host = (hostname or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        return host[4:]
    return host


def _looks_like_ip_literal(host: str) -> bool:
    return ":" in host or bool(re.fullmatch(r"(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+))*", host, re.I))


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        if not _looks_like_ip_literal(host):
            return None
        if ":" in host:
            raise
        try:
            return ipaddress.ip_address(socket.inet_aton(host))
        except OSError as exc:
            raise ValueError("invalid_ip_literal") from exc


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_global
        and not address.is_loopback
        and not address.is_private
        and not address.is_link_local
        and not address.is_reserved
        and not address.is_multicast
        and not address.is_unspecified
    )


def _same_site_host(observed: str, expected: str) -> bool:
    if not expected:
        return True
    return observed == expected or observed.endswith(f".{expected}")


def _validate_and_resolve_asset_url(
    url: str,
    base_host: str = "",
) -> tuple[bool, str, str, int, str]:
    try:
        parsed = urlparse(url)
        parsed_hostname = parsed.hostname
        port = parsed.port
    except Exception:
        return False, "invalid_url", "", 0, ""
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "invalid_scheme", "", 0, ""
    if not parsed_hostname:
        return False, "invalid_host", "", 0, ""
    host = parsed_hostname.strip().strip("[]").lower().rstrip(".")
    port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if host == "localhost" or host.endswith(".localhost"):
        return False, "local_host", "", 0, ""
    try:
        address = _parse_ip_literal(host)
    except ValueError:
        if _looks_like_ip_literal(host):
            return False, "invalid_ip_literal", "", 0, ""
        address = None
    if address and not _is_public_address(address):
        return False, "non_public_ip", "", 0, ""
    if base_host:
        expected = _hostname_without_www(urlparse(base_host if "://" in base_host else f"//{base_host}").hostname or base_host)
        observed = _hostname_without_www(parsed_hostname)
        if not _same_site_host(observed, expected):
            return False, "different_host", "", 0, ""
    if address is None:
        try:
            resolved = socket.getaddrinfo(host, None)
        except OSError:
            return False, "host_resolution_failed", "", 0, ""
        resolved_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        try:
            for item in resolved:
                sockaddr = item[4]
                if not sockaddr:
                    continue
                resolved_addresses.append(ipaddress.ip_address(sockaddr[0]))
        except (IndexError, TypeError, ValueError):
            return False, "host_resolution_failed", "", 0, ""
        if not resolved_addresses:
            return False, "host_resolution_failed", "", 0, ""
        if any(not _is_public_address(item) for item in resolved_addresses):
            return False, "non_public_ip", "", 0, ""
        return True, "", host, port, str(resolved_addresses[0])
    return True, "", host, port, ""


def validate_asset_url(url: str, base_host: str = "") -> tuple[bool, str]:
    valid, reason, _, _, _ = _validate_and_resolve_asset_url(url, base_host=base_host)
    return valid, reason


def read_response_limited(response: Any, max_bytes: int) -> bytes:
    length_header = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            length_header = str(headers.get("Content-Length") or headers.get("content-length") or "")
        except Exception:
            length_header = ""
    if length_header:
        try:
            if int(length_header) > max_bytes:
                raise ValueError("response_too_large")
        except ValueError as exc:
            if str(exc) == "response_too_large":
                raise
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("response_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def decode_data_uri_limited(src: str, max_bytes: int) -> tuple[bytes, str]:
    if not src.startswith("data:") or "," not in src:
        raise ValueError("invalid_data_uri")
    header, payload = src.split(",", 1)
    content_type = header[5:].split(";", 1)[0] or "text/plain"
    if ";base64" in header.lower():
        compact = "".join(payload.split())
        padding = compact.count("=")
        decoded_estimate = (len(compact) * 3) // 4 - padding
        if decoded_estimate > max_bytes:
            raise ValueError("response_too_large")
        try:
            body = base64.b64decode(compact, validate=True)
        except binascii.Error as exc:
            raise ValueError("invalid_data_uri") from exc
    else:
        chunks: list[bytes] = []
        total = 0
        index = 0
        while index < len(payload):
            if payload[index] == "%" and index + 2 < len(payload):
                piece = unquote_to_bytes(payload[index:index + 3])
                index += 3
            else:
                piece = payload[index].encode("ascii", errors="replace")
                index += 1
            total += len(piece)
            if total > max_bytes:
                raise ValueError("response_too_large")
            chunks.append(piece)
        body = b"".join(chunks)
    if len(body) > max_bytes:
        raise ValueError("response_too_large")
    return body, content_type


def fetch_url(
    url: str,
    timeout: int | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    base_host: str = "",
) -> tuple[str, bytes, str]:
    return fetch_url_with_curl(url, timeout, max_bytes, base_host=base_host)


def fetch_url_with_curl(
    url: str,
    timeout: int | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    base_host: str = "",
) -> tuple[str, bytes, str]:
    timeout = int(timeout or FETCH_TIMEOUT_SECONDS)
    if FETCH_DEADLINE is not None:
        remaining = FETCH_DEADLINE - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("asset_fetch_per_buyer_timeout")
        timeout = max(1, min(timeout, int(remaining)))
    import subprocess

    redirect_base_host = base_host or (urlparse(url).hostname or "")
    current_url = url
    with tempfile.TemporaryDirectory() as temp_dir:
        body_path = Path(temp_dir) / "body"
        for hop in range(MAX_REDIRECT_HOPS + 1):
            valid, reason, host, port, pinned_ip = _validate_and_resolve_asset_url(
                current_url,
                base_host=redirect_base_host,
            )
            if not valid:
                raise ValueError(reason)
            command = [
                "curl",
                "-q",
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--max-time",
                str(timeout),
                "--max-filesize",
                str(max_bytes),
                "-A",
                USER_AGENT,
                "-o",
                str(body_path),
                "-w",
                "%{url_effective}\n%{http_code}\n%{content_type}\n%{redirect_url}",
            ]
            if pinned_ip:
                resolve_ip = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
                command.extend(["--resolve", f"{host}:{port}:{resolve_ip}"])
            command.append(current_url)
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout + 2,
            )
            if result.returncode == 63:
                raise ValueError("response_too_large")
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
            metadata = result.stdout.decode("utf-8", errors="replace").split("\n", 3)
            if len(metadata) < 4:
                raise RuntimeError("curl response did not include metadata")
            final_url = metadata[0].strip() or current_url
            try:
                status_code = int(metadata[1].strip())
            except ValueError as exc:
                raise RuntimeError("curl response did not include a status code") from exc
            content_type = metadata[2].split(";")[0].strip() or "application/octet-stream"
            redirect_url = metadata[3].strip()
            if 300 <= status_code < 400 and redirect_url:
                if hop >= MAX_REDIRECT_HOPS:
                    raise ValueError("too_many_redirects")
                current_url = urljoin(current_url, redirect_url)
                continue
            if body_path.stat().st_size > max_bytes:
                raise ValueError("response_too_large")
            body = body_path.read_bytes()
            return final_url, body, content_type
    raise RuntimeError("curl redirect loop did not terminate")


class AssetHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_images: list[dict[str, str]] = []
        self.link_icons: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = {k.lower(): v for k, v in attrs}
        tag = tag.lower()
        if tag == "meta":
            prop = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            content = attrs_dict.get("content") or ""
            if prop in {"og:image", "twitter:image"} and content:
                self.meta_images.append({"src": content, "kind": "meta"})
        elif tag == "link":
            rel = (attrs_dict.get("rel") or "").lower()
            href = attrs_dict.get("href") or ""
            if href and ("icon" in rel or "logo" in rel):
                self.link_icons.append({"src": href, "kind": "icon", "rel": rel})
        elif tag == "img":
            src = attrs_dict.get("src") or attrs_dict.get("data-src") or ""
            alt = attrs_dict.get("alt") or ""
            cls = attrs_dict.get("class") or ""
            if src:
                self.images.append({"src": src, "alt": alt, "class": cls, "kind": "image"})
        elif tag == "a":
            href = attrs_dict.get("href") or ""
            text_hint = attrs_dict.get("title") or attrs_dict.get("aria-label") or ""
            if href:
                self.links.append({"href": href, "hint": text_hint})


def extract_inline_svg_logos(base_url: str, html: str, origin: str) -> list[AssetCandidate]:
    """Capture large inline header marks without taking a random screenshot."""
    candidates: list[AssetCandidate] = []
    for match in re.finditer(r"<svg\b[^>]*>.*?</svg>", html or "", flags=re.I | re.S):
        markup = match.group(0)
        prefix = (html or "")[max(0, match.start() - 2200):match.start()].lower()
        in_header = max(prefix.rfind("<header"), prefix.rfind("<nav")) > max(prefix.rfind("</header"), prefix.rfind("</nav"))
        if not in_header:
            continue
        opening = markup.split(">", 1)[0]
        width_match = re.search(r"\bwidth=[\"']([0-9.]+)", opening, re.I)
        height_match = re.search(r"\bheight=[\"']([0-9.]+)", opening, re.I)
        width = float(width_match.group(1)) if width_match else 0
        height = float(height_match.group(1)) if height_match else 0
        if width < 60 or height < 15 or len(markup) < 300:
            continue
        encoded = base64.b64encode(markup.encode("utf-8")).decode("ascii")
        candidates.append(
            AssetCandidate(
                src=f"data:image/svg+xml;base64,{encoded}",
                page=base_url,
                kind="inline-svg",
                alt="brand logo",
                cls=opening,
                origin=origin,
            )
        )
    return candidates[:4]


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def dedupe_candidates(candidates: list[AssetCandidate]) -> list[AssetCandidate]:
    best: dict[str, AssetCandidate] = {}
    for candidate in candidates:
        existing = best.get(candidate.src)
        if existing is None or candidate.score > existing.score:
            best[candidate.src] = candidate
    return list(best.values())


def has_supported_extension(url: str) -> bool:
    if url.startswith("data:image/svg+xml;base64,"):
        return True
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)


def sanitize_extension(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    for ext in IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return ext
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }
    return mapping.get(content_type, ".img")


def same_host(base_url: str, candidate_url: str) -> bool:
    return urlparse(base_url).netloc.lower() == urlparse(candidate_url).netloc.lower()


def normalized_identity_tokens(*values: str) -> set[str]:
    tokens: set[str] = set()
    stopwords = {
        "company", "corporation", "corp", "group", "holdings", "holding", "limited", "ltd",
        "inc", "incorporated", "electronics", "industrial", "industries", "official",
        "website", "the", "and", "of", "co", "com", "www", "www2", "logo", "brand",
        "identity", "image", "images", "icon", "favicon", "header", "navbar", "assets",
        "asset", "static", "media", "content", "inline", "desktop", "mobile", "light", "dark",
        "blue", "green", "red", "white", "black", "primary", "secondary", "horizontal", "vertical",
        "rgb", "color", "colour", "mark", "symbol", "new", "year",
        "png", "jpg", "jpeg", "svg", "webp", "gif", "ico", "cms", "api", "cdn", "src",
    }
    for value in values:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char))
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if len(token) >= 3 and token not in stopwords and not token.isdigit():
                tokens.add(token)
    return tokens


def logo_target(candidate: AssetCandidate) -> str:
    return " ".join([candidate.src, candidate.alt, candidate.cls, candidate.kind, candidate.page]).lower()


def candidate_resource_filename(candidate: AssetCandidate) -> str:
    if candidate.src.startswith("data:image/"):
        return ""
    return Path(urlparse(candidate.src).path).name


def logo_rejection_target(candidate: AssetCandidate) -> str:
    return " ".join([candidate_resource_filename(candidate), candidate.alt, candidate.cls]).lower()


def logo_rejection_reason(candidate: AssetCandidate) -> str:
    target = logo_rejection_target(candidate)
    normalized = unicodedata.normalize("NFKD", target)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    if tokens.intersection(LOGO_REJECT_HINTS):
        return "non_brand_badge_or_banner_hint"
    return ""


def candidate_brand_tokens(candidate: AssetCandidate) -> set[str]:
    tokens = normalized_identity_tokens(candidate_resource_filename(candidate), candidate.alt, candidate.cls)
    return {
        token
        for token in tokens
        if not (len(token) >= 8 and all(char in "0123456789abcdef" for char in token))
    }


def logo_brand_mismatch(candidate: AssetCandidate, buyer_name: str, domain: str) -> bool:
    expected = normalized_identity_tokens(buyer_name, domain)
    observed = candidate_brand_tokens(candidate)
    if not expected or not observed:
        return False
    overlap = expected.intersection(observed)
    return not overlap or bool(observed - expected)


def logo_candidate_rejection_reason(candidate: AssetCandidate, buyer_name: str, domain: str) -> str:
    return logo_rejection_reason(candidate) or (
        "different_or_sub_brand_name" if logo_brand_mismatch(candidate, buyer_name, domain) else ""
    )


def score_logo_candidate(candidate: AssetCandidate, buyer_name: str = "", domain: str = "") -> int:
    target = logo_target(candidate)
    score = 0
    if any(hint in target for hint in LOGO_HINTS):
        score += 12
    if "icon" in target:
        score += 4
    if "header" in target or "navbar" in target:
        score += 3
    if candidate.src.lower().endswith(".svg"):
        score += 2
    if candidate.origin == "official":
        score += 8
    else:
        score -= 4
    if candidate.origin == "maps":
        score -= 8
    if candidate.kind == "inline-svg":
        score += 6
    identity_tokens = normalized_identity_tokens(buyer_name, domain)
    observed_brand_tokens = candidate_brand_tokens(candidate)
    if identity_tokens.intersection(observed_brand_tokens):
        score += 28
    if logo_brand_mismatch(candidate, buyer_name, domain):
        score -= 40
    elif candidate.kind == "inline-svg" and identity_tokens.intersection(normalized_identity_tokens(candidate.page)):
        score += 18
    elif candidate.kind != "inline-svg":
        score -= 8
    if logo_rejection_reason(candidate):
        score -= 100
    return score


def rank_logo_candidates(candidates: list[AssetCandidate], buyer_name: str, domain: str) -> list[AssetCandidate]:
    for item in candidates:
        item.score = score_logo_candidate(item, buyer_name, domain)
    ranked = sorted(
        [
            item
            for item in dedupe_candidates(candidates)
            if has_supported_extension(item.src)
            and not logo_candidate_rejection_reason(item, buyer_name, domain)
            and item.score >= LOGO_MIN_SCORE
        ],
        key=lambda item: item.score,
        reverse=True,
    )
    return ranked


def score_visual_candidate(candidate: AssetCandidate) -> int:
    target = " ".join(
        [candidate.src.lower(), candidate.alt.lower(), candidate.cls.lower(), candidate.kind.lower(), candidate.page.lower()]
    )
    score = 0
    if candidate.kind == "meta":
        score += 8
    if any(hint in target for hint in PRODUCT_HINTS):
        score += 10
    if "hero" in target or "banner" in target:
        score += 4
    if any(hint in target for hint in SCREENSHOT_HINTS):
        score -= 8
    if "thumbnail" in target or "thumb" in target or "avatar" in target:
        score -= 6
    if "logo" in target or "icon" in target:
        score -= 10
    if any(domain in candidate.page.lower() for domain in SOCIAL_SOURCES):
        score += 2
    if any(domain in candidate.page.lower() for domain in MAP_HINTS):
        score -= 2
    return score


def pick_candidate_page_urls(base_url: str, parser: AssetHTMLParser) -> list[str]:
    candidates = []
    for item in parser.links:
        href = item["href"]
        full = urljoin(base_url, href)
        if not same_host(base_url, full):
            continue
        joined_hint = f"{href} {item.get('hint', '')}".lower()
        if any(hint in joined_hint for hint in PAGE_HINTS):
            candidates.append(full)
    return dedupe(candidates)[:MAX_PAGE_CANDIDATES]


def parse_page(base_url: str, html: str, origin: str = "official") -> tuple[list[AssetCandidate], list[AssetCandidate], list[str]]:
    parser = AssetHTMLParser()
    parser.feed(html)

    logo_candidates: list[AssetCandidate] = []
    visual_candidates: list[AssetCandidate] = []

    logo_candidates.extend(extract_inline_svg_logos(base_url, html, origin))

    for item in parser.link_icons:
        logo_candidates.append(AssetCandidate(src=urljoin(base_url, item["src"]), page=base_url, kind=item["kind"], origin=origin))
    for item in parser.images:
        full = urljoin(base_url, item["src"])
        target = " ".join([item.get("src", ""), item.get("alt", ""), item.get("class", "")]).lower()
        if any(hint in target for hint in LOGO_HINTS):
            logo_candidates.append(
                AssetCandidate(src=full, page=base_url, kind=item["kind"], alt=item.get("alt", ""), cls=item.get("class", ""), origin=origin)
            )
        else:
            visual_candidates.append(
                AssetCandidate(src=full, page=base_url, kind=item["kind"], alt=item.get("alt", ""), cls=item.get("class", ""), origin=origin)
            )
    for item in parser.meta_images:
        visual_candidates.insert(0, AssetCandidate(src=urljoin(base_url, item["src"]), page=base_url, kind=item["kind"], origin=origin))

    page_urls = pick_candidate_page_urls(base_url, parser)
    return logo_candidates, visual_candidates, page_urls


def extract_search_links(base_url: str, html: str, domain: str) -> list[str]:
    parser = AssetHTMLParser()
    parser.feed(html)
    candidates: list[str] = []
    for item in parser.links:
        href = item["href"]
        full = urljoin(base_url, href)
        host = urlparse(full).netloc.lower()
        if domain.lower() in host or any(social in host for social in SOCIAL_SOURCES) or any(m in host for m in MAP_HINTS):
            candidates.append(full)
    return candidates


def search_candidate_pages(domain: str, buyer_name: str) -> list[tuple[str, str]]:
    queries = [
        f"site:{domain} {buyer_name} products",
        f"site:{domain} {buyer_name} solutions",
        f"site:{domain} {buyer_name} project",
        f"{buyer_name} official linkedin",
        f"{buyer_name} google maps",
    ]
    pages: list[tuple[str, str]] = []
    for query in queries:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            final_url, body, content_type = fetch_url(url)
        except Exception:
            continue
        if not content_type.startswith("text/html"):
            continue
        html = body.decode("utf-8", errors="ignore")
        for link in extract_search_links(final_url, html, domain):
            host = urlparse(link).netloc.lower()
            origin = "official"
            if any(social in host for social in SOCIAL_SOURCES):
                origin = "social"
            elif any(m in host for m in MAP_HINTS):
                origin = "maps"
            pages.append((link, origin))
    deduped = []
    seen = set()
    for link, origin in pages:
        if link in seen:
            continue
        seen.add(link)
        deduped.append((link, origin))
    return deduped[:MAX_PAGE_CANDIDATES]


def search_candidate_pages_with_notes(domain: str, buyer_name: str) -> tuple[list[tuple[str, str]], list[str]]:
    queries = [
        f"site:{domain} {buyer_name} products",
        f"site:{domain} {buyer_name} solutions",
        f"site:{domain} {buyer_name} project",
        f"{buyer_name} official linkedin",
        f"{buyer_name} google maps",
    ]
    pages: list[tuple[str, str]] = []
    notes: list[str] = []
    for query in queries:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            final_url, body, content_type = fetch_url(url)
        except Exception as exc:
            notes.append(f"search_failed:{query}:{exc.__class__.__name__}")
            continue
        if not content_type.startswith("text/html"):
            notes.append(f"search_not_html:{query}:{content_type}")
            continue
        html = body.decode("utf-8", errors="ignore")
        extracted = extract_search_links(final_url, html, domain)
        notes.append(f"search:{query}:links={len(extracted)}")
        for link in extracted:
            host = urlparse(link).netloc.lower()
            origin = "official"
            if any(social in host for social in SOCIAL_SOURCES):
                origin = "social"
            elif any(m in host for m in MAP_HINTS):
                origin = "maps"
            pages.append((link, origin))
    deduped = []
    seen = set()
    for link, origin in pages:
        if link in seen:
            continue
        seen.add(link)
        deduped.append((link, origin))
    return deduped[:MAX_PAGE_CANDIDATES], notes


def import_playwright() -> Any:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(f"playwright_unavailable:{exc.__class__.__name__}") from exc
    return sync_playwright, PlaywrightTimeoutError


def rendered_payload_to_candidates(
    base_url: str,
    payload: dict[str, Any],
    origin: str,
) -> tuple[list[AssetCandidate], list[AssetCandidate], list[str]]:
    logo_candidates: list[AssetCandidate] = []
    visual_candidates: list[AssetCandidate] = []

    for item in payload.get("icons", []):
        src = item.get("src") or ""
        if not src:
            continue
        logo_candidates.append(
            AssetCandidate(
                src=urljoin(base_url, src),
                page=base_url,
                kind=item.get("kind", "icon"),
                cls=item.get("rel", ""),
                origin=origin,
            )
        )

    for item in payload.get("inlineSvgs", []):
        src = item.get("src") or ""
        if not src:
            continue
        logo_candidates.append(
            AssetCandidate(
                src=src,
                page=base_url,
                kind="inline-svg",
                alt=item.get("alt", "brand logo"),
                cls=item.get("className", ""),
                origin=origin,
            )
        )

    for item in payload.get("images", []):
        src = item.get("src") or ""
        if not src:
            continue
        candidate = AssetCandidate(
            src=urljoin(base_url, src),
            page=base_url,
            kind=item.get("kind", "image"),
            alt=item.get("alt", ""),
            cls=item.get("className", ""),
            origin=origin,
        )
        target = " ".join(
            [
                src,
                item.get("alt", ""),
                item.get("className", ""),
                item.get("id", ""),
                item.get("selectorHint", ""),
            ]
        ).lower()
        if any(hint in target for hint in LOGO_HINTS):
            logo_candidates.append(candidate)
        else:
            visual_candidates.append(candidate)

    for item in payload.get("metaImages", []):
        src = item.get("src") or ""
        if not src:
            continue
        visual_candidates.insert(
            0,
            AssetCandidate(
                src=urljoin(base_url, src),
                page=base_url,
                kind=item.get("kind", "meta"),
                origin=origin,
            ),
        )

    for item in payload.get("backgrounds", []):
        src = item.get("src") or ""
        if not src:
            continue
        visual_candidates.append(
            AssetCandidate(
                src=urljoin(base_url, src),
                page=base_url,
                kind="background",
                cls=" ".join([item.get("className", ""), item.get("selectorHint", "")]).strip(),
                origin=origin,
            )
        )

    page_urls: list[str] = []
    for item in payload.get("links", []):
        href = item.get("href") or ""
        full = urljoin(base_url, href)
        if not same_host(base_url, full):
            continue
        joined_hint = f"{href} {item.get('hint', '')}".lower()
        if any(hint in joined_hint for hint in PAGE_HINTS):
            page_urls.append(full)

    return logo_candidates, visual_candidates, dedupe(page_urls)[:MAX_PAGE_CANDIDATES]


def extract_rendered_payload(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const absolute = (value) => {
            if (!value) return "";
            try {
              return new URL(value, document.baseURI).href;
            } catch (error) {
              return value;
            }
          };
          const pickBackgroundUrl = (value) => {
            if (!value || !value.includes("url(")) return "";
            const match = value.match(/url\\((['"]?)(.*?)\\1\\)/i);
            return match ? absolute(match[2]) : "";
          };
          const icons = [];
          document.querySelectorAll("link[rel]").forEach((el) => {
            const rel = (el.getAttribute("rel") || "").toLowerCase();
            const href = el.getAttribute("href") || "";
            if (href && (rel.includes("icon") || rel.includes("logo"))) {
              icons.push({ src: absolute(href), kind: "icon", rel });
            }
          });
          const metaImages = [];
          document.querySelectorAll("meta[property], meta[name]").forEach((el) => {
            const key = (el.getAttribute("property") || el.getAttribute("name") || "").toLowerCase();
            const content = el.getAttribute("content") || "";
            if (content && (key === "og:image" || key === "twitter:image")) {
              metaImages.push({ src: absolute(content), kind: "meta" });
            }
          });
          const images = [];
          document.querySelectorAll("img").forEach((el) => {
            const src =
              el.currentSrc ||
              el.getAttribute("src") ||
              el.getAttribute("data-src") ||
              el.getAttribute("data-lazy-src") ||
              "";
            if (!src) return;
            images.push({
              src: absolute(src),
              alt: el.getAttribute("alt") || "",
              className: el.getAttribute("class") || "",
              id: el.getAttribute("id") || "",
              selectorHint: [el.tagName, el.closest("header,nav,main,section,figure,a,div")?.tagName || ""].join(" "),
              kind: "image",
            });
          });
          const inlineSvgs = [];
          document.querySelectorAll("header svg, nav svg").forEach((el) => {
            const box = el.getBoundingClientRect();
            if (box.width < 60 || box.height < 15 || box.width * box.height < 1200) return;
            const markup = el.outerHTML || "";
            if (!markup) return;
            let encoded = "";
            try {
              encoded = btoa(unescape(encodeURIComponent(markup)));
            } catch (error) {
              return;
            }
            inlineSvgs.push({
              src: "data:image/svg+xml;base64," + encoded,
              alt: "brand logo",
              className: el.getAttribute("class") || "",
            });
          });
          const backgrounds = [];
          document.querySelectorAll("header, nav, main, section, figure, a, div").forEach((el) => {
            const style = getComputedStyle(el);
            const bg = pickBackgroundUrl(style.backgroundImage || "");
            if (!bg) return;
            backgrounds.push({
              src: bg,
              className: el.getAttribute("class") || "",
              selectorHint: [el.tagName, el.getAttribute("id") || ""].join(" "),
            });
          });
          const links = [];
          document.querySelectorAll("a[href]").forEach((el) => {
            const href = el.getAttribute("href") || "";
            if (!href) return;
            links.push({
              href: absolute(href),
              hint: [
                el.getAttribute("title") || "",
                el.getAttribute("aria-label") || "",
                (el.textContent || "").trim().slice(0, 80),
              ].join(" "),
            });
          });
          return { icons, inlineSvgs, metaImages, images, backgrounds, links };
        }
        """
    )


def render_page(
    page: Any,
    target_url: str,
    origin: str,
    timeout_ms: int,
) -> tuple[str | None, list[AssetCandidate], list[AssetCandidate], list[str], list[str]]:
    return None, [], [], [], ["browser_skip:network_unsafe"]


def discover_assets_for_domain_light(
    domain: str,
    buyer_name: str,
) -> tuple[str | None, list[AssetCandidate], list[AssetCandidate], list[str]]:
    notes: list[str] = []
    for base_url in candidate_base_urls(domain):
        try:
            final_url, body, content_type = fetch_url(base_url)
        except Exception as exc:
            notes.append(f"base_failed:{base_url}:{exc.__class__.__name__}")
            continue
        if not content_type.startswith("text/html"):
            notes.append(f"base_not_html:{base_url}:{content_type}")
            continue

        html = body.decode("utf-8", errors="ignore")
        all_logo_candidates: list[AssetCandidate] = []
        all_visual_candidates: list[AssetCandidate] = []

        logos, visuals, page_urls = parse_page(final_url, html, origin="official")
        all_logo_candidates.extend(logos)
        all_visual_candidates.extend(visuals)
        notes.append(f"base:{final_url}")

        page_pairs = [(url, "official") for url in page_urls]
        # Search engines are the slowest and least reliable source. Crawl
        # official pages first, and only query them when the homepage did not
        # yield a usable logo or any visual candidate.
        if not all_visual_candidates:
            search_pages, search_notes = search_candidate_pages_with_notes(domain, buyer_name)
            notes.extend(search_notes)
            page_pairs.extend(search_pages)
        else:
            notes.append("search_skip:visual_candidate_available")
        for page_url, origin in dedupe(page_pairs)[:3]:
            try:
                page_final_url, page_body, page_content_type = fetch_url(page_url)
            except Exception as exc:
                notes.append(f"page_failed:{page_url}:{exc.__class__.__name__}:origin={origin}")
                continue
            if not page_content_type.startswith("text/html"):
                notes.append(f"page_not_html:{page_url}:{page_content_type}:origin={origin}")
                continue
            page_html = page_body.decode("utf-8", errors="ignore")
            page_logos, page_visuals, _ = parse_page(page_final_url, page_html, origin=origin)
            all_logo_candidates.extend(page_logos)
            all_visual_candidates.extend(page_visuals)
            notes.append(f"page:{page_final_url}:origin={origin}")

        for item in all_visual_candidates:
            item.score = score_visual_candidate(item)

        ranked_logos = rank_logo_candidates(all_logo_candidates, buyer_name, domain)
        for item in all_logo_candidates:
            reason = logo_candidate_rejection_reason(item, buyer_name, domain) or ("low_score" if item.score < LOGO_MIN_SCORE else "")
            if reason:
                notes.append(f"logo_rejected_candidate:{reason}:{item.src}")
        ranked_visuals = sorted(
            [item for item in dedupe_candidates(all_visual_candidates) if has_supported_extension(item.src)],
            key=lambda item: item.score,
            reverse=True,
        )
        return final_url, ranked_logos, ranked_visuals, notes
    return None, [], [], notes


def discover_assets_for_domain_browser(
    domain: str,
    buyer_name: str,
    timeout_ms: int,
) -> tuple[str | None, list[AssetCandidate], list[AssetCandidate], list[str]]:
    return None, [], [], ["browser_skip:network_unsafe"]


def inspect_downloaded_asset(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"bytes": path.stat().st_size}
    suffix = path.suffix.lower()
    if suffix == ".svg":
        info["width"] = None
        info["height"] = None
        info["ratio"] = None
        return info
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        info["width"] = None
        info["height"] = None
        info["ratio"] = None
        return info
    info["width"] = width
    info["height"] = height
    info["ratio"] = round(width / height, 3) if height else None
    return info


def passes_logo_filter(meta: dict[str, Any], path: Path) -> bool:
    if meta["bytes"] > MAX_IMAGE_BYTES:
        return False
    if path.suffix.lower() == ".svg":
        return meta["bytes"] >= 512
    if meta["bytes"] < MIN_LOGO_BYTES:
        return False
    width = meta.get("width") or 0
    height = meta.get("height") or 0
    return width >= MIN_LOGO_WIDTH and height >= MIN_LOGO_HEIGHT


def passes_visual_filter(meta: dict[str, Any], path: Path) -> bool:
    if meta["bytes"] < MIN_IMAGE_BYTES or meta["bytes"] > MAX_IMAGE_BYTES:
        return False
    if path.suffix.lower() == ".svg":
        return False
    width = meta.get("width") or 0
    height = meta.get("height") or 0
    ratio = meta.get("ratio")
    if width < MIN_VISUAL_WIDTH or height < MIN_VISUAL_HEIGHT:
        return False
    if ratio is None:
        return False
    return 0.45 <= ratio <= 4.8


def download_asset(candidate: AssetCandidate, output_path: Path, kind: str) -> tuple[Path | None, dict[str, Any]]:
    try:
        if candidate.src.startswith("data:image/svg+xml;base64,"):
            final_url = "inline-logo.svg"
            body, content_type = decode_data_uri_limited(candidate.src, MAX_IMAGE_BYTES)
        else:
            base_host = urlparse(candidate.page).hostname or ""
            final_url, body, content_type = fetch_url(candidate.src, max_bytes=MAX_IMAGE_BYTES, base_host=base_host)
    except Exception as exc:
        return None, {"reason": f"download_failed:{exc.__class__.__name__}"}
    if not content_type.startswith("image/"):
        return None, {"reason": f"not_image:{content_type}"}
    ext = sanitize_extension(final_url, content_type)
    final_path = output_path.with_suffix(ext)
    final_path.write_bytes(body)
    meta = inspect_downloaded_asset(final_path)
    passed = passes_logo_filter(meta, final_path) if kind == "logo" else passes_visual_filter(meta, final_path)
    if not passed:
        final_path.unlink(missing_ok=True)
        return None, {"reason": "filtered_out", **meta}
    return final_path, meta


def discover_assets_for_domain(
    domain: str,
    buyer_name: str,
    asset_mode: str,
    browser_timeout_ms: int,
) -> tuple[str | None, list[AssetCandidate], list[AssetCandidate], list[str]]:
    if asset_mode == "browser":
        return discover_assets_for_domain_browser(domain, buyer_name, browser_timeout_ms)

    final_url, logo_candidates, visual_candidates, notes = discover_assets_for_domain_light(domain, buyer_name)
    if asset_mode != "auto":
        return final_url, logo_candidates, visual_candidates, notes

    if logo_candidates and visual_candidates:
        notes.append("browser_skip:auto_light_success")
        return final_url, logo_candidates, visual_candidates, notes
    if not get_env_var("BUYER_BOARD_ENABLE_BROWSER_FALLBACK"):
        notes.append("browser_skip:auto_browser_fallback_disabled")
        return final_url, logo_candidates, visual_candidates, notes

    browser_url, browser_logos, browser_visuals, browser_notes = discover_assets_for_domain_browser(
        domain,
        buyer_name,
        browser_timeout_ms,
    )
    notes.extend(browser_notes)
    merged_url = final_url or browser_url
    merged_logos = logo_candidates[:]
    merged_visuals = visual_candidates[:]
    merged_logos.extend(browser_logos)
    merged_visuals.extend(browser_visuals)
    for item in merged_visuals:
        item.score = score_visual_candidate(item)
    ranked_logos = rank_logo_candidates(merged_logos, buyer_name, domain)
    ranked_visuals = sorted(dedupe_candidates(merged_visuals), key=lambda item: item.score, reverse=True)
    return merged_url, ranked_logos, ranked_visuals, notes


def load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {}
    return json.loads(cache_path.read_text(encoding="utf-8-sig"))


def save_cache(cache_path: Path, payload: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def maybe_generate_ai_visual(buyer: dict[str, Any], assets_dir: Path, enabled: bool) -> tuple[str, str]:
    if not enabled:
        return "", "ai_fallback_skipped:disabled"
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key:
        return "", "ai_fallback_skipped:no_api_key"

    try:
        from openai import OpenAI
    except Exception:
        return "", "ai_fallback_skipped:no_openai_sdk"

    prompt = (
        f"Create a clean industrial marketing image for {buyer.get('name', '')}, "
        f"focused on {buyer.get('products', '')}. Show real product elements or industrial equipment, "
        "wide composition, no text, no logo, suitable for a corporate buyer profile slide."
    )
    try:
        client = OpenAI(api_key=api_key)
        result = client.images.generate(
            model=get_env_var("BUYER_VISUAL_MODEL") or "gpt-image-1",
            prompt=prompt,
            size="1536x1024",
        )
        image_b64 = result.data[0].b64_json
        output = assets_dir / f"{slugify(str(buyer.get('name', 'buyer')))}-ai-site.png"
        output.write_bytes(__import__("base64").b64decode(image_b64))
        return str(output), "ai_fallback_generated"
    except Exception as exc:
        return "", f"ai_fallback_failed:{exc.__class__.__name__}"


def logo_confidence(score: int) -> str:
    if score >= 38:
        return "high"
    if score >= 20:
        return "medium"
    if score >= LOGO_MIN_SCORE:
        return "low"
    return "missing"


def display_asset_source(src: str, page: str = "") -> str:
    if src.startswith("data:image/svg+xml;base64,"):
        return f"inline-svg:{page}" if page else "inline-svg"
    return src if len(src) <= 240 else src[:237] + "..."


def remaining_fetch_milliseconds() -> int | None:
    if FETCH_DEADLINE is None:
        return None
    return max(0, int((FETCH_DEADLINE - time.monotonic()) * 1000))


def process_buyer(
    buyer: dict[str, Any],
    assets_dir: Path,
    cache: dict[str, Any],
    enable_ai_visual_fallback: bool,
    asset_mode: str,
    browser_timeout_ms: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    website = str(buyer.get("website", "") or "").strip()
    report: dict[str, Any] = {
        "name": buyer.get("name", ""),
        "website": website,
        "logo_hit": False,
        "logo_confidence": "missing",
        "logo_source": "",
        "logo_url": "",
        "logo_rejected_candidates": [],
        "site_hit": False,
        "site_source": "",
        "asset_mode": asset_mode,
        "asset_logic_version": ASSET_LOGIC_VERSION,
        "notes": [],
    }
    if not website:
        report["notes"].append("No website available for asset fetch.")
        buyer["asset_fetch_notes"] = "No website available for asset fetch."
        return buyer, report

    cache_key = website.lower()
    cached = cache.get(cache_key)
    cached_logo = Path(str(cached.get("logo_path", ""))) if isinstance(cached, dict) and cached.get("logo_path") else None
    cached_site = Path(str(cached.get("site_image_path", ""))) if isinstance(cached, dict) and cached.get("site_image_path") else None
    valid_cache = isinstance(cached, dict) and cached.get("asset_logic_version") == ASSET_LOGIC_VERSION
    cached_logo_present = valid_cache and cached_logo is not None and cached_logo.is_file()
    cached_site_present = valid_cache and cached_site is not None and cached_site.is_file()
    if valid_cache and cached_logo_present and cached_site_present:
        buyer["logo_path"] = cached.get("logo_path", "")
        buyer["site_image_path"] = cached.get("site_image_path", "")
        buyer["asset_fetch_notes"] = cached.get("asset_fetch_notes", "cache_hit")
        report["logo_hit"] = bool(buyer["logo_path"])
        report["logo_confidence"] = cached.get("logo_confidence", "missing")
        report["logo_source"] = cached.get("logo_source", "")
        report["logo_url"] = cached.get("logo_url", "")
        report["site_hit"] = bool(buyer["site_image_path"])
        report["site_source"] = cached.get("site_source", "")
        report["notes"].append("cache_hit")
        return buyer, report

    final_url, logo_candidates, visual_candidates, notes = discover_assets_for_domain(
        website,
        str(buyer.get("name", "")),
        asset_mode,
        browser_timeout_ms,
    )
    slug = slugify(str(buyer.get("name", "buyer")))

    logo_path = str(cached.get("logo_path", "")) if cached_logo_present else ""
    logo_url = str(cached.get("logo_url", "")) if cached_logo_present else ""
    logo_source = str(cached.get("logo_source", "")) if cached_logo_present else ""
    logo_confidence_value = str(cached.get("logo_confidence", "missing")) if cached_logo_present else "missing"
    logo_score = 0
    site_image_path = str(cached.get("site_image_path", "")) if cached_site_present else ""
    site_source = str(cached.get("site_source", "")) if cached_site_present else ""
    trace = list(notes)
    if cached_logo_present:
        trace.append("cache_hit:logo")
        report["logo_hit"] = True
        report["logo_confidence"] = logo_confidence_value
        report["logo_source"] = logo_source
        report["logo_url"] = logo_url
    if cached_site_present:
        trace.append("cache_hit:site")
        report["site_hit"] = True
        report["site_source"] = site_source
    report["logo_rejected_candidates"] = [
        note for note in trace if note.startswith("logo_rejected_candidate:")
    ][:12]
    if final_url:
        trace.append(f"resolved:{final_url}")

    if not logo_path:
        for candidate in logo_candidates[:8]:
            downloaded, meta = download_asset(candidate, assets_dir / f"{slug}-logo", "logo")
            trace.append(f"logo_try:{display_asset_source(candidate.src, candidate.page)}:score={candidate.score}:origin={candidate.origin}")
            if not downloaded:
                trace.append(f"logo_reject:{candidate.src}:{meta}")
            if downloaded:
                logo_path = str(downloaded)
                logo_url = display_asset_source(candidate.src, candidate.page)
                logo_source = candidate.origin
                logo_score = candidate.score
                logo_confidence_value = logo_confidence(candidate.score)
                trace.append(f"logo:{display_asset_source(candidate.src, candidate.page)}")
                trace.append(f"logo_meta:{meta}")
                report["logo_hit"] = True
                report["logo_confidence"] = logo_confidence_value
                report["logo_source"] = candidate.origin
                report["logo_url"] = candidate.src
                break

    if not site_image_path:
        for candidate in visual_candidates[:12]:
            downloaded, meta = download_asset(candidate, assets_dir / f"{slug}-site", "site")
            trace.append(f"site_try:{candidate.src}:score={candidate.score}:origin={candidate.origin}")
            if not downloaded:
                trace.append(f"site_reject:{candidate.src}:{meta}")
                continue
            try:
                prepared = prepare_site_image(downloaded, assets_dir, 1600, 900)
                site_image_path = str(prepared.output_path)
                site_source = candidate.origin
                trace.append(f"site:{candidate.src}")
                trace.append(f"site_meta:{meta}")
                trace.append(f"site_prepare:{prepared.mode}:retention={prepared.retention}:upscale={prepared.upscale}")
                report["site_hit"] = True
                break
            except Exception as exc:
                trace.append(f"site_prepare_failed:{exc.__class__.__name__}")

    if not site_image_path:
        ai_path, ai_note = maybe_generate_ai_visual(buyer, assets_dir, enable_ai_visual_fallback)
        trace.append(ai_note)
        if ai_path:
            prepared = prepare_site_image(Path(ai_path), assets_dir, 1600, 900)
            site_image_path = str(prepared.output_path)
            site_source = "ai"
            report["site_hit"] = True

    if not logo_path:
        trace.append("logo:missing")
    if not site_image_path:
        trace.append("site:missing")

    buyer["logo_path"] = logo_path
    buyer["site_image_path"] = site_image_path
    buyer["asset_fetch_notes"] = "; ".join(trace)

    if logo_path or site_image_path:
        cache[cache_key] = {
            "asset_logic_version": ASSET_LOGIC_VERSION,
            "logo_path": logo_path,
            "site_image_path": site_image_path,
            "logo_confidence": logo_confidence_value if logo_path else "missing",
            "logo_source": logo_source,
            "logo_url": logo_url,
            "site_source": site_source,
            "asset_fetch_notes": buyer["asset_fetch_notes"],
        }
    report["logo_confidence"] = logo_confidence_value if logo_path else "missing"
    report["logo_source"] = logo_source
    report["logo_url"] = logo_url
    report["site_source"] = site_source
    report["notes"] = trace
    return buyer, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch buyer logo and site visuals from public official websites.")
    parser.add_argument("--buyers", required=True, help="buyers.json path")
    parser.add_argument("--output", required=True, help="output buyers.json path")
    parser.add_argument("--assets-dir", required=True, help="directory to store fetched image assets")
    parser.add_argument("--cache-file", required=True, help="cache json file path")
    parser.add_argument("--report-file", required=True, help="asset fetch report json file path")
    parser.add_argument("--enable-ai-visual-fallback", action="store_true", help="generate AI site visual when public assets are unavailable")
    parser.add_argument(
        "--asset-mode",
        choices=("light", "auto", "browser"),
        default="light",
        help="light uses HTML parsing only, auto adds Playwright fallback when needed, browser uses Playwright-first fetching",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=int,
        default=8000,
        help="per-page browser render timeout in milliseconds when Playwright-enhanced asset mode is enabled",
    )
    parser.add_argument(
        "--fetch-timeout-seconds",
        type=int,
        default=8,
        help="per HTTP request timeout for lightweight asset fetching",
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=180,
        help="soft total runtime budget; remaining buyers are skipped after this limit",
    )
    parser.add_argument(
        "--per-buyer-seconds",
        type=int,
        default=35,
        help="hard asset-fetch time limit per buyer; timed-out buyers continue without assets",
    )
    args = parser.parse_args()

    buyers_path = Path(args.buyers)
    output_path = Path(args.output)
    assets_dir = Path(args.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.cache_file)
    report_path = Path(args.report_file)

    global FETCH_TIMEOUT_SECONDS
    FETCH_TIMEOUT_SECONDS = max(3, int(args.fetch_timeout_seconds))
    cache = load_cache(cache_path)
    buyers = load_json(buyers_path)
    enriched = []
    report_items = []
    started = time.monotonic()
    for item in buyers:
        if time.monotonic() - started > max(10, int(args.max_seconds)):
            skipped = dict(item)
            skipped["asset_fetch_notes"] = "skipped:asset_fetch_time_budget_exceeded"
            enriched.append(skipped)
            report_items.append({
                "name": skipped.get("name", ""),
                "website": skipped.get("website", ""),
                "logo_hit": False,
                "logo_confidence": "missing",
                "logo_source": "",
                "logo_url": "",
                "logo_rejected_candidates": [],
                "site_hit": False,
                "site_source": "",
                "asset_mode": args.asset_mode,
                "asset_logic_version": ASSET_LOGIC_VERSION,
                "notes": ["skipped:asset_fetch_time_budget_exceeded"],
                "elapsed_seconds": 0.0,
            })
            continue
        global FETCH_DEADLINE
        FETCH_DEADLINE = time.monotonic() + max(10, int(args.per_buyer_seconds))
        try:
            buyer, report = process_buyer(
                dict(item),
                assets_dir,
                cache,
                args.enable_ai_visual_fallback,
                args.asset_mode,
                args.browser_timeout_ms,
            )
        finally:
            FETCH_DEADLINE = None
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        enriched.append(buyer)
        report_items.append(report)

    save_cache(cache_path, cache)
    save_json(output_path, enriched)
    save_json(report_path, report_items)
    print(output_path)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
