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
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        final_url = response.geturl()
        body = response.read()
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
    if meta["bytes"] < MIN_IMAGE_BYTES or meta["bytes"] > MAX_IMAGE_BYTES:
        return False
    if path.suffix.lower() == ".svg":
        return True
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


def discover_assets_for_domain(domain: str, buyer_name: str) -> tuple[str | None, list[AssetCandidate], list[AssetCandidate], list[str]]:
    notes: list[str] = []
    for base_url in candidate_base_urls(domain):
        try:
            final_url, body, content_type = fetch_url(base_url)
        except Exception:
            continue
        if not content_type.startswith("text/html"):
            continue

        html = body.decode("utf-8", errors="ignore")
        all_logo_candidates: list[AssetCandidate] = []
        all_visual_candidates: list[AssetCandidate] = []

        logos, visuals, page_urls = parse_page(final_url, html, origin="official")
        all_logo_candidates.extend(logos)
        all_visual_candidates.extend(visuals)
        notes.append(f"base:{final_url}")

        search_pages = search_candidate_pages(domain, buyer_name)
        for page_url, origin in dedupe([(u, o) for (u, o) in [(url, "official") for url in page_urls] + search_pages]):
            try:
                page_final_url, page_body, page_content_type = fetch_url(page_url)
            except Exception:
                continue
            if not page_content_type.startswith("text/html"):
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
    api_key = os.environ.get("OPENAI_API_KEY")
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    website = str(buyer.get("website", "") or "").strip()
    report: dict[str, Any] = {
        "name": buyer.get("name", ""),
        "website": website,
        "logo_hit": False,
        "site_hit": False,
        "site_source": "",
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

    final_url, logo_candidates, visual_candidates, notes = discover_assets_for_domain(website, str(buyer.get("name", "")))
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
        buyer, report = process_buyer(dict(item), assets_dir, cache, args.enable_ai_visual_fallback)
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
