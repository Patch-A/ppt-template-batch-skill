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
]


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
        self.meta_images: list[str] = []
        self.link_icons: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = {k.lower(): v for k, v in attrs}
        tag = tag.lower()
        if tag == "meta":
            prop = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            content = attrs_dict.get("content") or ""
            if prop in {"og:image", "twitter:image"} and content:
                self.meta_images.append(content)
        elif tag == "link":
            rel = (attrs_dict.get("rel") or "").lower()
            href = attrs_dict.get("href") or ""
            if href and ("icon" in rel or "logo" in rel):
                self.link_icons.append(href)
        elif tag == "img":
            src = attrs_dict.get("src") or attrs_dict.get("data-src") or ""
            alt = (attrs_dict.get("alt") or "").lower()
            cls = (attrs_dict.get("class") or "").lower()
            if src:
                score_prefix = ""
                if "logo" in alt or "logo" in cls or "brand" in alt:
                    score_prefix = "logo:"
                elif any(hint in src.lower() or hint in alt or hint in cls for hint in PRODUCT_HINTS):
                    score_prefix = "product:"
                self.images.append(score_prefix + src)


def parse_assets(base_url: str, html: str) -> tuple[list[str], list[str]]:
    parser = AssetHTMLParser()
    parser.feed(html)

    logos: list[str] = []
    visuals: list[str] = []

    for src in parser.link_icons:
        logos.append(urljoin(base_url, src))
    for src in parser.images:
        if src.startswith("logo:"):
            logos.append(urljoin(base_url, src.split(":", 1)[1]))
        elif src.startswith("product:"):
            visuals.append(urljoin(base_url, src.split(":", 1)[1]))
        else:
            visuals.append(urljoin(base_url, src))
    for src in parser.meta_images:
        visuals.insert(0, urljoin(base_url, src))

    return dedupe(logos), dedupe(visuals)


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


def discover_assets_for_domain(domain: str) -> tuple[str | None, str | None, str | None]:
    for base_url in candidate_base_urls(domain):
        try:
            final_url, body, content_type = fetch_url(base_url)
        except Exception:
            continue
        if not content_type.startswith("text/html"):
            continue
        html = body.decode("utf-8", errors="ignore")
        logos, visuals = parse_assets(final_url, html)
        logo = next((item for item in logos if has_supported_extension(item)), None)
        visual = next((item for item in visuals if has_supported_extension(item)), None)
        return final_url, logo, visual
    return None, None, None


def process_buyer(buyer: dict[str, Any], assets_dir: Path) -> dict[str, Any]:
    website = str(buyer.get("website", "") or "").strip()
    if not website:
        buyer["asset_fetch_notes"] = "No website available for asset fetch."
        return buyer

    final_url, logo_url, visual_url = discover_assets_for_domain(website)
    slug = slugify(str(buyer.get("name", "buyer")))

    logo_path = ""
    site_image_path = ""
    notes: list[str] = []

    if final_url:
        notes.append(f"base:{final_url}")

    if logo_url:
        downloaded = download_asset(logo_url, assets_dir / f"{slug}-logo")
        if downloaded:
            logo_path = str(downloaded)
            notes.append(f"logo:{logo_url}")
    if visual_url:
        downloaded = download_asset(visual_url, assets_dir / f"{slug}-site")
        if downloaded:
            site_image_path = str(downloaded)
            notes.append(f"site:{visual_url}")

    if not logo_path:
        notes.append("logo:missing")
    if not site_image_path:
        notes.append("site:missing")

    buyer["logo_path"] = logo_path
    buyer["site_image_path"] = site_image_path
    buyer["asset_fetch_notes"] = "; ".join(notes)
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
