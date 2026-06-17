from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


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
LOGO_HINTS = ["logo", "brand", "identity"]


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
            alt = (attrs_dict.get("alt") or "")
            cls = (attrs_dict.get("class") or "")
            if src:
                self.images.append(
                    {
                        "src": src,
                        "alt": alt,
                        "class": cls,
                        "kind": "image",
                    }
                )
        elif tag == "a":
            href = attrs_dict.get("href") or ""
            text_hint = (attrs_dict.get("title") or attrs_dict.get("aria-label") or "")
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


def download_asset(url: str, output_path: Path) -> Path | None:
    try:
        final_url, body, content_type = fetch_url(url)
    except Exception:
        return None
    if not content_type.startswith("image/"):
        return None
    ext = sanitize_extension(final_url, content_type)
    final_path = output_path.with_suffix(ext)
    final_path.write_bytes(body)
    return final_path


def same_host(base_url: str, candidate_url: str) -> bool:
    return urlparse(base_url).netloc.lower() == urlparse(candidate_url).netloc.lower()


def score_logo_candidate(src: str, alt: str = "", cls: str = "", kind: str = "") -> int:
    target = " ".join([src.lower(), alt.lower(), cls.lower(), kind.lower()])
    score = 0
    if any(hint in target for hint in LOGO_HINTS):
        score += 12
    if "icon" in target:
        score += 4
    if "header" in target or "navbar" in target:
        score += 3
    if src.lower().endswith(".svg"):
        score += 2
    return score


def score_visual_candidate(src: str, alt: str = "", cls: str = "", kind: str = "", page_url: str = "") -> int:
    target = " ".join([src.lower(), alt.lower(), cls.lower(), kind.lower(), page_url.lower()])
    score = 0
    if kind == "meta":
        score += 8
    if any(hint in target for hint in PRODUCT_HINTS):
        score += 10
    if "hero" in target or "banner" in target:
        score += 4
    if "thumbnail" in target or "thumb" in target or "avatar" in target:
        score -= 6
    if "logo" in target or "icon" in target:
        score -= 10
    return score


def pick_candidate_page_urls(base_url: str, parser: AssetHTMLParser) -> list[str]:
    candidates = []
    for item in parser.links:
        href = item["href"]
        full = urljoin(base_url, href)
        if not same_host(base_url, full):
            continue
        joined_hint = f"{href} {item.get('hint','')}".lower()
        if any(hint in joined_hint for hint in PAGE_HINTS):
            candidates.append(full)
    return dedupe(candidates)[:6]


def parse_page(base_url: str, html: str) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    parser = AssetHTMLParser()
    parser.feed(html)

    logo_candidates: list[dict[str, str]] = []
    visual_candidates: list[dict[str, str]] = []

    for item in parser.link_icons:
        logo_candidates.append({**item, "src": urljoin(base_url, item["src"]), "page": base_url})
    for item in parser.images:
        full = urljoin(base_url, item["src"])
        target = " ".join([item.get("src", ""), item.get("alt", ""), item.get("class", "")]).lower()
        bucket = logo_candidates if any(hint in target for hint in LOGO_HINTS) else visual_candidates
        bucket.append({**item, "src": full, "page": base_url})
    for item in parser.meta_images:
        visual_candidates.insert(0, {**item, "src": urljoin(base_url, item["src"]), "page": base_url})

    page_urls = pick_candidate_page_urls(base_url, parser)
    return logo_candidates, visual_candidates, page_urls


def rank_logo_candidates(items: list[dict[str, str]]) -> list[dict[str, str]]:
    filtered = [item for item in items if has_supported_extension(item["src"])]
    return sorted(
        filtered,
        key=lambda item: score_logo_candidate(item["src"], item.get("alt", ""), item.get("class", ""), item.get("kind", "")),
        reverse=True,
    )


def rank_visual_candidates(items: list[dict[str, str]]) -> list[dict[str, str]]:
    filtered = [item for item in items if has_supported_extension(item["src"])]
    return sorted(
        filtered,
        key=lambda item: score_visual_candidate(
            item["src"], item.get("alt", ""), item.get("class", ""), item.get("kind", ""), item.get("page", "")
        ),
        reverse=True,
    )


def discover_assets_for_domain(domain: str) -> tuple[str | None, dict[str, str] | None, dict[str, str] | None, list[str]]:
    notes: list[str] = []
    for base_url in candidate_base_urls(domain):
        try:
            final_url, body, content_type = fetch_url(base_url)
        except Exception:
            continue
        if not content_type.startswith("text/html"):
            continue

        html = body.decode("utf-8", errors="ignore")
        all_logo_candidates: list[dict[str, str]] = []
        all_visual_candidates: list[dict[str, str]] = []

        logos, visuals, page_urls = parse_page(final_url, html)
        all_logo_candidates.extend(logos)
        all_visual_candidates.extend(visuals)
        notes.append(f"base:{final_url}")

        for page_url in page_urls:
            try:
                page_final_url, page_body, page_content_type = fetch_url(page_url)
            except Exception:
                continue
            if not page_content_type.startswith("text/html"):
                continue
            page_html = page_body.decode("utf-8", errors="ignore")
            page_logos, page_visuals, _ = parse_page(page_final_url, page_html)
            all_logo_candidates.extend(page_logos)
            all_visual_candidates.extend(page_visuals)
            notes.append(f"page:{page_final_url}")

        ranked_logos = rank_logo_candidates(all_logo_candidates)
        ranked_visuals = rank_visual_candidates(all_visual_candidates)
        logo = ranked_logos[0] if ranked_logos else None
        visual = ranked_visuals[0] if ranked_visuals else None
        return final_url, logo, visual, notes
    return None, None, None, notes


def process_buyer(buyer: dict[str, Any], assets_dir: Path) -> dict[str, Any]:
    website = str(buyer.get("website", "") or "").strip()
    if not website:
        buyer["asset_fetch_notes"] = "No website available for asset fetch."
        return buyer

    final_url, logo_candidate, visual_candidate, notes = discover_assets_for_domain(website)
    slug = slugify(str(buyer.get("name", "buyer")))

    logo_path = ""
    site_image_path = ""
    trace = list(notes)

    if final_url:
        trace.append(f"resolved:{final_url}")

    if logo_candidate:
        downloaded = download_asset(logo_candidate["src"], assets_dir / f"{slug}-logo")
        if downloaded:
            logo_path = str(downloaded)
            trace.append(f"logo:{logo_candidate['src']}")
            trace.append(f"logo_page:{logo_candidate.get('page','')}")
    if visual_candidate:
        downloaded = download_asset(visual_candidate["src"], assets_dir / f"{slug}-site")
        if downloaded:
            site_image_path = str(downloaded)
            trace.append(f"site:{visual_candidate['src']}")
            trace.append(f"site_page:{visual_candidate.get('page','')}")

    if not logo_path:
        trace.append("logo:missing")
    if not site_image_path:
        trace.append("site:missing")

    buyer["logo_path"] = logo_path
    buyer["site_image_path"] = site_image_path
    buyer["asset_fetch_notes"] = "; ".join(trace)
    return buyer


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch buyer logo and site visuals from public official websites.")
    parser.add_argument("--buyers", required=True, help="buyers.json path")
    parser.add_argument("--output", required=True, help="output buyers.json path")
    parser.add_argument("--assets-dir", required=True, help="directory to store fetched image assets")
    args = parser.parse_args()

    buyers_path = Path(args.buyers)
    output_path = Path(args.output)
    assets_dir = Path(args.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)

    buyers = load_json(buyers_path)
    enriched = [process_buyer(dict(item), assets_dir) for item in buyers]

    save_json(output_path, enriched)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
