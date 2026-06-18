from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

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
SCREENSHOT_HINTS = ["screenshot", "screen", "homepage", "website"]
MAX_PAGE_CANDIDATES = 10
MIN_IMAGE_BYTES = 5 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIN_VISUAL_WIDTH = 240
MIN_VISUAL_HEIGHT = 140
MIN_LOGO_WIDTH = 60
MIN_LOGO_HEIGHT = 20
BROWSER_VIEWPORT_WIDTH = 1440
BROWSER_VIEWPORT_HEIGHT = 1080
BROWSER_WAIT_MS = 1200
BROWSER_PAGE_LIMIT = 6


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


def fetch_url(url: str, timeout: int = 20) -> tuple[str, bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            final_url = response.geturl()
            body = response.read()
        return final_url, body, content_type
    except Exception:
        if not get_env_var("BUYER_BOARD_ENABLE_CURL_FALLBACK"):
            raise
        return fetch_url_with_curl(url, timeout)


def fetch_url_with_curl(url: str, timeout: int = 20) -> tuple[str, bytes, str]:
    import subprocess

    result = subprocess.run(
        [
            "curl",
            "-L",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            "-A",
            USER_AGENT,
            "-w",
            "\n%{url_effective}\n%{content_type}",
            url,
        ],
        capture_output=True,
        timeout=timeout + 5,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    chunks = result.stdout.split(b"\n")
    if len(chunks) < 3:
        raise RuntimeError("curl response did not include metadata")
    content_type = chunks[-1].decode("utf-8", errors="replace").split(";")[0].strip() or "application/octet-stream"
    final_url = chunks[-2].decode("utf-8", errors="replace").strip() or url
    body = b"\n".join(chunks[:-2])
    return final_url, body, content_type


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


def score_logo_candidate(candidate: AssetCandidate) -> int:
    target = " ".join([candidate.src.lower(), candidate.alt.lower(), candidate.cls.lower(), candidate.kind.lower()])
    score = 0
    if any(hint in target for hint in LOGO_HINTS):
        score += 12
    if "icon" in target:
        score += 4
    if "header" in target or "navbar" in target:
        score += 3
    if candidate.src.lower().endswith(".svg"):
        score += 2
    if candidate.origin != "official":
        score -= 4
    return score


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
          return { icons, metaImages, images, backgrounds, links };
        }
        """
    )


def render_page(
    page: Any,
    target_url: str,
    origin: str,
    timeout_ms: int,
) -> tuple[str | None, list[AssetCandidate], list[AssetCandidate], list[str], list[str]]:
    notes: list[str] = []
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 4000))
        except Exception:
            notes.append(f"browser_networkidle_timeout:{target_url}")
        page.wait_for_timeout(BROWSER_WAIT_MS)
        final_url = str(page.url)
        html = page.content()
        logo_candidates, visual_candidates, page_urls = parse_page(final_url, html, origin=origin)
        rendered_payload = extract_rendered_payload(page)
        extra_logos, extra_visuals, extra_pages = rendered_payload_to_candidates(final_url, rendered_payload, origin)
        logo_candidates.extend(extra_logos)
        visual_candidates.extend(extra_visuals)
        page_urls.extend(extra_pages)
        notes.append(f"browser_page:{final_url}:origin={origin}")
        return final_url, logo_candidates, visual_candidates, dedupe(page_urls)[:MAX_PAGE_CANDIDATES], notes
    except Exception as exc:
        notes.append(f"browser_page_failed:{target_url}:{exc.__class__.__name__}:origin={origin}")
        return None, [], [], [], notes


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

        search_pages, search_notes = search_candidate_pages_with_notes(domain, buyer_name)
        notes.extend(search_notes)
        for page_url, origin in dedupe([(u, o) for (u, o) in [(url, "official") for url in page_urls] + search_pages]):
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

        for item in all_logo_candidates:
            item.score = score_logo_candidate(item)
        for item in all_visual_candidates:
            item.score = score_visual_candidate(item)

        ranked_logos = sorted(
            [item for item in dedupe_candidates(all_logo_candidates) if has_supported_extension(item.src)],
            key=lambda item: item.score,
            reverse=True,
        )
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
    notes: list[str] = []
    try:
        sync_playwright, _ = import_playwright()
    except RuntimeError as exc:
        notes.append(str(exc))
        return None, [], [], notes

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": BROWSER_VIEWPORT_WIDTH, "height": BROWSER_VIEWPORT_HEIGHT},
            user_agent=USER_AGENT,
        )
        page = context.new_page()
        try:
            all_logo_candidates: list[AssetCandidate] = []
            all_visual_candidates: list[AssetCandidate] = []
            resolved_url: str | None = None
            page_urls: list[tuple[str, str]] = []

            for base_url in candidate_base_urls(domain):
                final_url, logos, visuals, discovered_pages, base_notes = render_page(page, base_url, "official", timeout_ms)
                notes.extend(base_notes)
                if not final_url:
                    continue
                resolved_url = final_url
                all_logo_candidates.extend(logos)
                all_visual_candidates.extend(visuals)
                page_urls.extend((url, "official") for url in discovered_pages)
                break

            if not resolved_url:
                return None, [], [], notes

            search_pages, search_notes = search_candidate_pages_with_notes(domain, buyer_name)
            notes.extend(search_notes)
            page_urls.extend(search_pages)

            seen = set()
            processed = 0
            for page_url, origin in page_urls:
                if page_url in seen:
                    continue
                seen.add(page_url)
                processed += 1
                if processed > BROWSER_PAGE_LIMIT:
                    notes.append(f"browser_page_limit:{BROWSER_PAGE_LIMIT}")
                    break
                final_url, logos, visuals, _, page_notes = render_page(page, page_url, origin, timeout_ms)
                notes.extend(page_notes)
                if not final_url:
                    continue
                all_logo_candidates.extend(logos)
                all_visual_candidates.extend(visuals)

            for item in all_logo_candidates:
                item.score = score_logo_candidate(item)
            for item in all_visual_candidates:
                item.score = score_visual_candidate(item)

            ranked_logos = sorted(
                [item for item in dedupe_candidates(all_logo_candidates) if has_supported_extension(item.src)],
                key=lambda item: item.score,
                reverse=True,
            )
            ranked_visuals = sorted(
                [item for item in dedupe_candidates(all_visual_candidates) if has_supported_extension(item.src)],
                key=lambda item: item.score,
                reverse=True,
            )
            return resolved_url, ranked_logos, ranked_visuals, notes
        finally:
            context.close()
            browser.close()


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
    if meta["bytes"] < MIN_IMAGE_BYTES:
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
        final_url, body, content_type = fetch_url(candidate.src)
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
    for item in merged_logos:
        item.score = score_logo_candidate(item)
    for item in merged_visuals:
        item.score = score_visual_candidate(item)
    ranked_logos = sorted(dedupe_candidates(merged_logos), key=lambda item: item.score, reverse=True)
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
            model="gpt-image-1",
            prompt=prompt,
            size="1536x1024",
        )
        image_b64 = result.data[0].b64_json
        output = assets_dir / f"{slugify(str(buyer.get('name', 'buyer')))}-ai-site.png"
        output.write_bytes(__import__("base64").b64decode(image_b64))
        return str(output), "ai_fallback_generated"
    except Exception as exc:
        return "", f"ai_fallback_failed:{exc.__class__.__name__}"


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
        "site_hit": False,
        "site_source": "",
        "asset_mode": asset_mode,
        "notes": [],
    }
    if not website:
        report["notes"].append("No website available for asset fetch.")
        buyer["asset_fetch_notes"] = "No website available for asset fetch."
        return buyer, report

    cache_key = website.lower()
    if cache_key in cache:
        cached = cache[cache_key]
        buyer["logo_path"] = cached.get("logo_path", "")
        buyer["site_image_path"] = cached.get("site_image_path", "")
        buyer["asset_fetch_notes"] = cached.get("asset_fetch_notes", "cache_hit")
        report["logo_hit"] = bool(buyer["logo_path"])
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

    logo_path = ""
    site_image_path = ""
    site_source = ""
    trace = list(notes)
    if final_url:
        trace.append(f"resolved:{final_url}")

    for candidate in logo_candidates[:8]:
        downloaded, meta = download_asset(candidate, assets_dir / f"{slug}-logo", "logo")
        trace.append(f"logo_try:{candidate.src}:score={candidate.score}:origin={candidate.origin}")
        if not downloaded:
            trace.append(f"logo_reject:{candidate.src}:{meta}")
        if downloaded:
            logo_path = str(downloaded)
            trace.append(f"logo:{candidate.src}")
            trace.append(f"logo_meta:{meta}")
            report["logo_hit"] = True
            break

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
            "logo_path": logo_path,
            "site_image_path": site_image_path,
            "site_source": site_source,
            "asset_fetch_notes": buyer["asset_fetch_notes"],
        }
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
        default=18000,
        help="per-page browser render timeout in milliseconds when Playwright-enhanced asset mode is enabled",
    )
    args = parser.parse_args()

    buyers_path = Path(args.buyers)
    output_path = Path(args.output)
    assets_dir = Path(args.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.cache_file)
    report_path = Path(args.report_file)

    cache = load_cache(cache_path)
    buyers = load_json(buyers_path)
    enriched = []
    report_items = []
    for item in buyers:
        buyer, report = process_buyer(
            dict(item),
            assets_dir,
            cache,
            args.enable_ai_visual_fallback,
            args.asset_mode,
            args.browser_timeout_ms,
        )
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
