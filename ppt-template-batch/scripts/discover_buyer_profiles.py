from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from env_utils import get_env_var


PROVIDER_DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1"},
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-plus"},
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": ""},
    "minimax": {"base_url": "https://api.minimax.chat/v1", "model": ""},
    "siliconflow": {"base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2.5-72B-Instruct"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": ""},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5"},
    "lmstudio": {"base_url": "http://127.0.0.1:1234/v1", "model": "local-model"},
    "compatible": {"base_url": "", "model": ""},
}

SYSTEM_PROMPT = """You are a rigorous B2B buyer research and qualification analyst.
Your task is to build a broad candidate pool, then qualify companies against the user's actual procurement scenario.
Return only valid JSON. Do not include markdown or commentary.
Never treat an industry match as sufficient evidence. A company is relevant only when its manufacturing process, operations, projects, distribution business, installed equipment, maintenance needs, or import activity creates a plausible need for the requested product.
Prefer companies headquartered in or operating materially inside the selected country. Prefer official websites and verifiable business evidence. Import or trade evidence is valuable, but must not be invented.
Distinguish direct end users, manufacturers consuming the product as a component or production input, distributors/importers, EPC/integrators, maintenance contractors, project owners, and competing OEMs.
Downgrade or exclude companies whose only connection is that they manufacture or sell the same product without a credible purchasing scenario.
"""


def clean_provider(value: str | None) -> str:
    provider = (value or get_env_var("BUYER_RESEARCH_PROVIDER") or "deepseek").strip().lower()
    return provider if provider in PROVIDER_DEFAULTS else "compatible"


def clean_base_url(provider: str, value: str | None) -> str:
    base_url = (value or get_env_var("BUYER_RESEARCH_BASE_URL") or get_env_var("OPENAI_BASE_URL") or "").strip().rstrip("/")
    if base_url:
        return base_url
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["compatible"])["base_url"]


def clean_research_mode(value: str | None) -> str:
    mode = (value or get_env_var("BUYER_RESEARCH_MODE") or "model_only").strip().lower()
    return mode if mode in {"model_only", "openai_web_search"} else "model_only"


def require_api_key() -> str:
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("API key is required for auto research mode. Configure it in the console model settings first.")
    return api_key


def should_try_powershell_fallback(exc: BaseException) -> bool:
    if os.name != "nt":
        return False
    if get_env_var("PPT_BATCH_DISABLE_POWERSHELL_FALLBACK"):
        return False
    message = str(exc)
    return "WinError 10013" in message or "access permissions" in message or "\u8bbf\u95ee\u6743\u9650" in message


def powershell_post_json(url: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        payload_path = handle.name
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", suffix=".ps1", delete=False) as handle:
        script_path = handle.name
        handle.write('$ErrorActionPreference = "Stop"\n[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12\n$body = Get-Content -LiteralPath $env:PPT_BATCH_PAYLOAD_FILE -Raw -Encoding UTF8\n$headers = @{\n  "Authorization" = "Bearer $env:PPT_BATCH_FALLBACK_API_KEY"\n  "Accept" = "application/json"\n}\ntry {\n  $response = Invoke-WebRequest -UseBasicParsing -Uri $env:PPT_BATCH_URL -Method Post -Headers $headers -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec $env:PPT_BATCH_TIMEOUT\n  if ($null -ne $response.Content -and $response.Content.Length -gt 0) {\n    Write-Output $response.Content\n  } else {\n    throw "HTTP $($response.StatusCode) returned empty response body."\n  }\n} catch {\n  $status = 0\n  $content = ""\n  if ($_.Exception.Response) {\n    try { $status = [int]$_.Exception.Response.StatusCode } catch {}\n    try {\n      $stream = $_.Exception.Response.GetResponseStream()\n      if ($stream) {\n        $reader = New-Object System.IO.StreamReader($stream)\n        $content = $reader.ReadToEnd()\n      }\n    } catch {}\n  }\n  if ($content) { throw "HTTP ${status}: $content" }\n  throw $_.Exception.Message\n}\n')
    env = os.environ.copy()
    env.update({
        "PPT_BATCH_URL": url,
        "PPT_BATCH_PAYLOAD_FILE": payload_path,
        "PPT_BATCH_FALLBACK_API_KEY": api_key,
        "PPT_BATCH_TIMEOUT": str(max(5, int(timeout))),
    })
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout + 15,
        )
    finally:
        for candidate in (payload_path, script_path):
            try:
                Path(candidate).unlink()
            except OSError:
                pass
    stdout = result.stdout.decode("utf-8-sig", errors="replace").strip()
    stderr = result.stderr.decode("utf-8-sig", errors="replace").strip()
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell fallback failed for {url}: {stderr or stdout}")
    if not stdout:
        raise RuntimeError(f"PowerShell fallback returned empty response for {url}. stderr={stderr or 'empty'}")
    return json.loads(stdout)


def api_post_json(base_url: str, path: str, api_key: str, payload: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:1200]}") from exc
    except URLError as exc:
        if should_try_powershell_fallback(exc):
            try:
                return powershell_post_json(url, api_key, payload, timeout)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Python urllib was blocked for {url}: {exc}. "
                    f"PowerShell fallback also failed: {fallback_exc}"
                ) from fallback_exc
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def normalize_website(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://", "", value, flags=re.I)
    return value.rstrip("/")


def chinese_char_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def pad_or_trim_bio(text: str) -> str:
    raw = re.sub(r"\s+", "", text or "")
    allowed_punctuation = "\uff0c\u3002\u3001\uff1b\uff1a"
    chars = [ch for ch in raw if "\u4e00" <= ch <= "\u9fff" or ch in allowed_punctuation]
    result = "".join(chars).strip("\uff0c\u3001\uff1a")

    # A fixed-length response may already have been cut in the middle of a
    # clause. Keep only complete sentences before adding the required padding.
    if result and result[-1] not in "\u3002\uff1b":
        last_sentence_end = max(result.rfind("\u3002"), result.rfind("\uff1b"))
        if last_sentence_end >= 0:
            result = result[:last_sentence_end + 1]

    # Keep a complete sentence in the 120-130-character window. The previous
    # implementation cut at character 120, which created visibly broken copy.
    if chinese_char_count(result) > 130:
        sentence_ends = [index for index, ch in enumerate(result) if ch in "\u3002\uff1b"]
        usable = [index for index in sentence_ends if 112 <= chinese_char_count(result[:index + 1]) <= 130]
        if usable:
            result = result[:usable[-1] + 1]
        else:
            output: list[str] = []
            for ch in result:
                output.append(ch)
                if chinese_char_count("".join(output)) >= 126:
                    break
            result = "".join(output).rstrip(allowed_punctuation)

    if result and result[-1] not in "\u3002\uff1b":
        result += "\u3002"

    neutral_fact_terms = ("\u4f4d\u4e8e", "\u603b\u90e8", "\u5f53\u5730", "\u4e3b\u8425", "\u63d0\u4f9b", "\u751f\u4ea7", "\u9500\u552e", "\u670d\u52a1", "\u4ea7\u54c1", "\u4e1a\u52a1", "\u7ecf\u8425", "\u8986\u76d6", "\u4e13\u6ce8")
    procurement_claim_terms = ("\u91c7\u8d2d", "\u5408\u4f5c", "\u9700\u6c42", "\u8ba2\u5355", "\u4ea4\u4ed8", "\u552e\u540e", "\u80fd\u529b", "\u8ba1\u5212", "\u610f\u5411")
    fillers: list[str] = []
    for sentence in re.findall(r"[^\u3002\uff1b]+[\u3002\uff1b]", result):
        source_facts = [sentence]
        source_facts.extend(f"{clause}\u3002" for clause in re.split(r"[\uff0c\u3001\uff1b]", sentence.rstrip("\u3002\uff1b")) if clause)
        for fact in source_facts:
            normalized_fact = fact.strip("\uff0c\u3001\uff1b\uff1a")
            if (
                normalized_fact
                and not any(term in normalized_fact for term in procurement_claim_terms)
                and any(term in normalized_fact for term in neutral_fact_terms)
                and normalized_fact not in fillers
            ):
                fillers.append(normalized_fact)

    # Only repeat neutral facts already present in the source; never add a
    # procurement judgment or a business claim that the source did not make.
    filler_index = 0
    while chinese_char_count(result) < 120 and fillers:
        for offset in range(len(fillers)):
            index = (filler_index + offset) % len(fillers)
            filler = fillers[index]
            if chinese_char_count(result + filler) <= 130:
                result += filler
                filler_index = index + 1
                break
        else:
            break

    return result


def normalize_products(value: str, procurement_need: str) -> str:
    product = re.sub(r"\s+", "", value or "")
    product = re.sub(r"^(?:采购产品|采购品类|采购需求)[:：]", "", product)
    product = re.split(r"(?:主要用于|适用于|用于|用以|以满足|进行加工)", product, maxsplit=1)[0]
    product = product.strip("，、；。:：")
    fallback = re.sub(r"\s+", "", procurement_need or "")
    fallback = re.split(r"(?:主要用于|适用于|用于|用以|以满足|进行加工)", fallback, maxsplit=1)[0]
    fallback = fallback.strip("，、；。:：")
    if not product or re.search(r"(?:[三四五六七八九十]轴|联动|精密|数控|高速|重型|大型|小型|智能)$", product):
        return fallback or product
    return product


def split_product_items(value: str) -> list[str]:
    text = re.sub(r"\s+", "", value or "")
    text = re.sub(r"^(?:\u91c7\u8d2d\u4ea7\u54c1|\u91c7\u8d2d\u54c1\u7c7b|\u91c7\u8d2d\u9700\u6c42)[:\uff1a]", "", text)
    text = re.sub(r"\u7b49(?:\u5305\u88c5\u5236\u54c1|\u4ea7\u54c1|\u8bbe\u5907)?$", "", text)
    return [item.strip("\u3001\uff0c,;\uff1b") for item in re.split(r"[\u3001\uff0c,;\uff1b/]+", text) if item.strip("\u3001\uff0c,;\uff1b")]


GENERIC_PRODUCT_TERMS = {
    "\u5546\u7528\u53a8\u623f\u8bbe\u5907", "\u98df\u54c1\u52a0\u5de5\u8bbe\u5907", "\u4e2d\u592e\u53a8\u623f\u7cfb\u7edf",
    "\u9910\u996e\u8bbe\u5907", "\u53a8\u623f\u8bbe\u5907", "\u98df\u54c1\u673a\u68b0", "\u5305\u88c5\u8bbe\u5907",
    "\u5de5\u4e1a\u8bbe\u5907", "\u81ea\u52a8\u5316\u8bbe\u5907", "\u4f20\u52a8\u8bbe\u5907", "\u6db2\u538b\u8bbe\u5907",
    "\u7535\u6c14\u8bbe\u5907", "\u914d\u5957\u8bbe\u5907", "\u6574\u5957\u7cfb\u7edf", "\u53a8\u623f\u7cfb\u7edf",
}
CONCRETE_PRODUCT_HINTS = (
    "\u5207\u83dc\u673a", "\u5207\u8089\u673a", "\u7ede\u8089\u673a", "\u5207\u7247\u673a", "\u6d17\u83dc\u673a", "\u6d17\u7897\u673a",
    "\u548c\u9762\u673a", "\u6405\u62cc\u673a", "\u70e4\u7bb1", "\u84b8\u7bb1", "\u6cb9\u70b8\u673a", "\u5c01\u53e3\u673a",
    "\u8d34\u6807\u673a", "\u5305\u88c5\u673a", "\u8f93\u9001\u673a", "\u51b7\u67dc", "\u5236\u51b7\u673a\u7ec4", "\u6df7\u5408\u673a",
    "\u7535\u673a", "\u6c34\u6cf5", "\u51cf\u901f\u673a", "\u98ce\u673a", "\u8f74\u627f", "\u94fe\u6761",
)


def is_generic_product(item: str) -> bool:
    normalized = item.strip("\u3001\uff0c,;\uff1b")
    return normalized in GENERIC_PRODUCT_TERMS or any(
        normalized == term or normalized.endswith(term) for term in GENERIC_PRODUCT_TERMS
    )


def infer_concrete_products(context: str) -> list[str]:
    evidence = re.sub(r"\s+", "", context or "")
    hits = [item for item in CONCRETE_PRODUCT_HINTS if item in evidence]
    if hits:
        return hits[:3]
    rules = (
        (("\u4e2d\u592e\u53a8\u623f", "\u9910\u996e\u96c6\u56e2", "\u9910\u996e\u670d\u52a1", "\u9910\u5385"), ("\u5207\u83dc\u673a", "\u5207\u8089\u673a")),
        (("\u8089\u5236\u54c1", "\u5c60\u5bb0", "\u9c9c\u8089"), ("\u7ede\u8089\u673a", "\u5207\u8089\u673a")),
        (("\u852c\u83dc", "\u51c0\u83dc"), ("\u5207\u83dc\u673a", "\u6d17\u83dc\u673a")),
        (("\u70d8\u7119", "\u9762\u5305", "\u7cd5\u70b9"), ("\u548c\u9762\u673a", "\u70e4\u7bb1")),
    )
    for keywords, products in rules:
        if any(keyword in evidence for keyword in keywords):
            return list(products)
    return []


BUYER_EVIDENCE_FIELDS = ("bio", "demand_scenarios", "research_notes", "evidence")


def buyer_evidence_context(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(key, "") or "") for key in BUYER_EVIDENCE_FIELDS)


def refine_buyer_products(value: str, procurement_need: str, context: str = "") -> str:
    """Keep buyer products concrete and prevent global/category-level copy-through."""
    product = normalize_products(value, procurement_need)
    requested = split_product_items(procurement_need)
    returned = split_product_items(product)
    specific_returned = [item for item in returned if not is_generic_product(item)]
    if not returned:
        inferred = infer_concrete_products(context)
        return "\u3001".join(inferred) if inferred else "\u9700\u6838\u5b9e\u5177\u4f53\u8bbe\u5907"
    if all(is_generic_product(item) for item in returned):
        inferred = infer_concrete_products(context)
        return "\u3001".join(inferred) if inferred else "\u9700\u6838\u5b9e\u5177\u4f53\u8bbe\u5907"

    copies_global_request = bool(returned) and bool(requested) and set(returned).issubset(set(requested))
    if copies_global_request:
        evidence = re.sub(r"\s+", "", context or "")
        ranked = sorted(
            ((item, evidence.count(item)) for item in specific_returned),
            key=lambda pair: pair[1],
            reverse=True,
        )
        selected = [item for item, hits in ranked if hits > 0][:3]
        return "\u3001".join(selected) if selected else "\u9700\u6838\u5b9e\u5177\u4f53\u8bbe\u5907"

    if specific_returned and len(specific_returned) != len(returned):
        return "\u3001".join(specific_returned[:3])
    if len(requested) <= 3 or not requested:
        return product
    return product


def build_strategy_text(strategy: dict[str, Any] | None) -> str:
    strategy = strategy or {}
    preferred_industries = str(strategy.get("preferred_industries", "") or "").strip()
    excluded_company_types = str(strategy.get("excluded_company_types", "") or "").strip()
    custom_requirements = str(strategy.get("custom_requirements", "") or "").strip()
    prefer_import_evidence = bool(strategy.get("prefer_import_evidence", True))
    return f"""Research strategy:
- Preferred industries or application scenarios: {preferred_industries or "Infer from the procurement need"}
- Excluded company types: {excluded_company_types or "Direct competitors without a credible buying scenario"}
- Prioritize import/trade evidence: {"yes" if prefer_import_evidence else "no"}
- Additional user requirements: {custom_requirements or "None"}
"""


def build_user_prompt(
    country: str,
    procurement_need: str,
    buyer_count: int,
    allow_no_live_search: bool = False,
    strategy: dict[str, Any] | None = None,
    stage: str = "candidate_pool",
    candidates: list[dict[str, Any]] | None = None,
) -> str:
    no_search_note = "If the current model cannot browse the web, use known public information and mark research_notes as requiring manual website verification." if allow_no_live_search else ""
    strategy_text = build_strategy_text(strategy)
    if stage == "shortlist":
        return f"""Target country or region: {country}
Procurement need: {procurement_need}
Required final buyer count: {buyer_count}
{strategy_text}

Evaluate the candidate pool below. Remove weak, duplicate, unverifiable, non-local, and competitor-only candidates. Rank the remaining companies by total_score and return only the strongest {buyer_count}.

Scoring dimensions, each from 0 to 100:
- fit_score: how directly the company's business creates a need for the requested product
- demand_score: how necessary or recurring the product is in manufacturing, operations, maintenance, projects, or resale
- import_score: strength of public import, distribution, foreign sourcing, or cross-border procurement signals
- verification_score: quality of official-site and public-source evidence
- total_score: weighted overall score, emphasizing fit and demand

For motors, for example, prioritize local manufacturers whose products or production lines require motors, factories with motor-driven machinery, utilities, mines, logistics facilities, EPC/integrators, industrial maintenance companies, and verified importers/distributors. Do not select a company merely because it operates in a broad industrial category.

The products field must name equipment at purchasing level, not an umbrella category. Use concrete items such as "\u5207\u83dc\u673a、\u5207\u8089\u673a", "\u7ede\u8089\u673a、\u548c\u9762\u673a", "\u5546\u7528\u70e4\u7bb1、\u6d17\u7897\u673a", or "\u8d34\u6807\u673a、\u5c01\u53e3\u673a". Do not return only phrases such as "\u5546\u7528\u53a8\u623f\u8bbe\u5907、\u98df\u54c1\u52a0\u5de5\u8bbe\u5907、\u4e2d\u592e\u53a8\u623f\u7cfb\u7edf". Infer the exact item from the company's facilities, production line, menu/service model, maintenance scope, or distribution catalog; if evidence is insufficient, mark the item for manual verification instead of presenting a broad category as a confirmed purchase.

Candidate pool:
{json.dumps(candidates or [], ensure_ascii=False)}

Return the required JSON structure. Each shortlisted buyer must include concrete demand_scenarios, evidence, source_urls, score fields, confidence, and risks. Never invent import evidence; use an empty import_signal and a low import_score when it is unavailable.
"""
    return f"""Target country or region: {country}
Procurement need: {procurement_need}
Candidate pool size: {buyer_count}
{no_search_note}
{strategy_text}

Selection rules:
- Choose real companies with clear official website domains and strong business fit.
- Build a diverse candidate pool before ranking. Include multiple buyer types when appropriate.
- Confirm the company is local to, headquartered in, or materially operating in the target country.
- The target is actual buyers/procurement accounts: end users that consume the product in operations, distributors/importers/resellers that buy for resale, EPC/project developers/integrators/maintenance contractors that buy for projects, or large groups with centralized procurement.
- For capital equipment such as CNC machines, laser machines, packaging equipment, textile machinery, food-processing equipment, or machine tools, prioritize factories and service providers that use the equipment to make their own products or provide contract manufacturing. Also consider local importers, distributors, machine-tool dealers, industrial equipment integrators, maintenance/service companies, technical training centers, and large industrial groups with machining workshops.
- Do not list a manufacturer only because it is in the same industry. A manufacturer is valid only when it likely purchases the requested product as production equipment, process equipment, components, consumables, spare parts, or resale inventory.
- Exclude or downgrade direct competing OEMs whose main business is making and selling the same requested product, unless public business fit suggests importing/distribution or internal use.
- The products field must be one to three concrete product names separated by Chinese commas, such as "五轴联动加工中心、五轴精密铣削中心". Never include verbs, "用于", processing scenarios, or a full sentence in this field.
- Product names must be equipment-level and specific. Reject a result that contains only umbrella terms such as "\u5546\u7528\u53a8\u623f\u8bbe\u5907、\u98df\u54c1\u52a0\u5de5\u8bbe\u5907、\u4e2d\u592e\u53a8\u623f\u7cfb\u7edf"; replace them with concrete machines justified by the buyer's own operations, such as "\u5207\u83dc\u673a、\u5207\u8089\u673a" or "\u7ede\u8089\u673a、\u548c\u9762\u673a".
- Do not copy the full Procurement need into every buyer. For each company, select only the one to three products that its factories, operations, projects, maintenance work, or resale business would actually buy. The product list must vary when the business scenarios differ.
- The demand_scenarios and evidence must justify the exact products selected for that company; a generic statement that it needs packaging or equipment is insufficient.
- demand_scenarios must explain exactly where and why the requested product is needed.
- import_signal must summarize public import/distribution/foreign-sourcing evidence, or be empty when no evidence is available.
- evidence must summarize the strongest qualification evidence.
- source_urls must contain public pages that support the qualification when live search is available.
- research_notes must state buyer type, procurement rationale, and verification caveats.
- Avoid entities with vague websites, weak procurement relevance, or unclear purchase scenario.

Return JSON in this exact structure:
{{
  "buyers": [
    {{
      "name": "Company legal or common full name",
      "country": "{country}",
      "website": "official-domain.example",
      "products": "One to three concrete procurement product names in Chinese only",
      "bio": "A complete 120-130 Chinese-character Simplified Chinese company introduction, ending with a full sentence",
      "logo_path": "",
      "site_image_path": "",
      "research_notes": "Buyer type, procurement rationale, and caveats",
      "buyer_type": "end_user_factory|component_user_manufacturer|importer_distributor|epc_integrator|maintenance_contractor|project_owner|other",
      "demand_scenarios": "Concrete operational or manufacturing use cases",
      "local_presence": "Evidence of headquarters, facilities, projects, branches, or operations in the target country",
      "import_signal": "Verified import, distribution, foreign sourcing, or trade signal; empty if unavailable",
      "evidence": "Concise evidence summary",
      "source_urls": ["https://official-or-public-source.example/page"]
    }}
  ]
}}

The website value must be a domain only, without http or https.
"""


def extract_json_object(text: str) -> str:
    """Return the first complete JSON object while ignoring braces in strings."""
    text = (text or "").strip().lstrip("\ufeff")
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def repair_common_json_issues(text: str) -> str:
    """Apply only deterministic, non-semantic fixes before requesting model repair."""
    text = extract_json_object(text)
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    text = re.sub(r",\s*([}\]])", r"\1", text)
    output: list[str] = []
    quote = ""
    escaped = False
    for char in text:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            elif char in "\r\n\t":
                output.append({"\r": "\\r", "\n": "\\n", "\t": "\\t"}[char])
                continue
        elif char == '"':
            quote = char
        output.append(char)
    return "".join(output)


def parse_json_payload(text: str) -> dict[str, Any]:
    raw = extract_json_object(text)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = json.loads(repair_common_json_issues(raw))
    if not isinstance(payload, dict):
        raise ValueError("Model result must be a JSON object.")
    return payload


def chat_completion_content(api_key: str, base_url: str, payload: dict[str, Any]) -> str:
    try:
        response = api_post_json(base_url, "/chat/completions", api_key, payload)
    except RuntimeError as exc:
        if not any(token in str(exc) for token in ("response_format", "json_object", "max_tokens")):
            raise
        fallback = dict(payload)
        fallback.pop("response_format", None)
        fallback.pop("max_tokens", None)
        response = api_post_json(base_url, "/chat/completions", api_key, fallback)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices returned by chat completion: {json.dumps(response, ensure_ascii=False)[:1200]}")
    return str(choices[0].get("message", {}).get("content") or "{}")


def repair_model_json(api_key: str, base_url: str, model_name: str, invalid_content: str) -> dict[str, Any]:
    repair_prompt = """Convert the following model output into one valid JSON object. Preserve every buyer field and value when possible. Do not add commentary, markdown, or new facts. Output only JSON with a top-level buyers array.\n\nMalformed output:\n"""
    content = chat_completion_content(api_key, base_url, {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You repair malformed JSON. Return JSON only."},
            {"role": "user", "content": repair_prompt + invalid_content[:60000]},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    })
    return parse_json_payload(content)


def retry_compact_buyer_json(
    api_key: str,
    base_url: str,
    model_name: str,
    user_prompt: str,
    expected_count: int,
) -> dict[str, Any]:
    compact_instruction = f"""
The prior response was incomplete. Start over and return valid JSON only.
Return at most {expected_count} buyers. To keep the response complete, each buyer must include only:
name, country, website, products, bio, research_notes, buyer_type, demand_scenarios, local_presence, import_signal, evidence, source_urls.
Use one source URL per buyer at most. Do not include logo_path, site_image_path, scores, confidence, risks, markdown, or commentary.
"""
    content = chat_completion_content(api_key, base_url, {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + " Return compact valid JSON only."},
            {"role": "user", "content": user_prompt + compact_instruction},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 8192,
    })
    return parse_json_payload(content)


def buyer_result_schema() -> dict[str, Any]:
    buyer_properties = {
        "name": {"type": "string"},
        "country": {"type": "string"},
        "website": {"type": "string"},
        "products": {"type": "string"},
        "bio": {"type": "string"},
        "logo_path": {"type": "string"},
        "site_image_path": {"type": "string"},
        "research_notes": {"type": "string"},
        "buyer_type": {"type": "string"},
        "demand_scenarios": {"type": "string"},
        "local_presence": {"type": "string"},
        "import_signal": {"type": "string"},
        "evidence": {"type": "string"},
        "source_urls": {"type": "array", "items": {"type": "string"}},
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "demand_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "import_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "verification_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "total_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "confidence": {"type": "string"},
        "risks": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": {
            "buyers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": buyer_properties,
                    "required": list(buyer_properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["buyers"],
        "additionalProperties": False,
    }


def candidate_result_schema() -> dict[str, Any]:
    properties = {
        "name": {"type": "string"},
        "country": {"type": "string"},
        "website": {"type": "string"},
        "products": {"type": "string"},
        "bio": {"type": "string"},
        "logo_path": {"type": "string"},
        "site_image_path": {"type": "string"},
        "research_notes": {"type": "string"},
        "buyer_type": {"type": "string"},
        "demand_scenarios": {"type": "string"},
        "local_presence": {"type": "string"},
        "import_signal": {"type": "string"},
        "evidence": {"type": "string"},
        "source_urls": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "properties": {
            "buyers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["buyers"],
        "additionalProperties": False,
    }


def fetch_json_with_openai_responses(
    api_key: str,
    base_url: str,
    model_name: str,
    user_prompt: str,
    schema_name: str,
    strict_shortlist: bool = True,
) -> list[dict[str, Any]]:
    request_payload = {
        "model": model_name,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [{"type": "web_search"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": buyer_result_schema() if strict_shortlist else candidate_result_schema(),
                "strict": True,
            }
        },
    }
    try:
        response = api_post_json(base_url, "/responses", api_key, request_payload)
    except RuntimeError:
        request_payload["tools"] = [{"type": "web_search_preview"}]
        response = api_post_json(base_url, "/responses", api_key, request_payload)
    output_text = response.get("output_text")
    if not output_text:
        parts: list[str] = []
        for item in response.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(str(content["text"]))
        output_text = "".join(parts)
    payload = parse_json_payload(output_text or "{}")
    return payload.get("buyers", [])


def fetch_json_with_chat(
    api_key: str,
    base_url: str,
    model_name: str,
    user_prompt: str,
    expected_count: int,
) -> list[dict[str, Any]]:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 8192,
    }
    content = chat_completion_content(api_key, base_url, payload)
    try:
        result = parse_json_payload(content)
    except (json.JSONDecodeError, ValueError) as exc:
        try:
            result = repair_model_json(api_key, base_url, model_name, content)
        except Exception as repair_exc:
            try:
                result = retry_compact_buyer_json(api_key, base_url, model_name, user_prompt, expected_count)
            except Exception as compact_exc:
                location = f"line {exc.lineno}, column {exc.colno}" if isinstance(exc, json.JSONDecodeError) else str(exc)
                raise RuntimeError(
                    "模型返回的买家资料格式不完整，系统已自动修复和精简重试各一次但仍未成功。"
                    f"原始格式问题：{location}。请重试搜索或更换模型。"
                ) from compact_exc
    buyers = result.get("buyers", [])
    if not isinstance(buyers, list):
        raise RuntimeError("模型返回的 buyers 字段不是列表，已停止回填以保护现有资料。")
    return buyers


def fetch_buyers(
    country: str,
    procurement_need: str,
    buyer_count: int,
    model: str | None,
    provider: str | None,
    base_url: str | None,
    research_mode: str | None = None,
    strategy: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider_name = clean_provider(provider)
    resolved_base_url = clean_base_url(provider_name, base_url)
    model_name = model or get_env_var("BUYER_RESEARCH_MODEL") or PROVIDER_DEFAULTS[provider_name]["model"]
    if not model_name:
        raise RuntimeError("Research model is not configured.")
    api_key = require_api_key()
    resolved_mode = clean_research_mode(research_mode)
    candidate_multiplier = max(2, min(5, int((strategy or {}).get("candidate_multiplier", 3) or 3)))
    # Candidate records contain long Chinese bios and evidence fields. Keep the
    # first pass compact enough that compatible models do not truncate JSON.
    candidate_count = min(16, max(buyer_count, buyer_count + min(candidate_multiplier, 4)))
    candidate_prompt = build_user_prompt(
        country,
        procurement_need,
        candidate_count,
        allow_no_live_search=not (provider_name == "openai" and resolved_mode == "openai_web_search"),
        strategy=strategy,
        stage="candidate_pool",
    )
    if provider_name == "openai" and resolved_mode == "openai_web_search":
        candidates = fetch_json_with_openai_responses(
            api_key,
            resolved_base_url,
            model_name,
            candidate_prompt,
            "buyer_candidate_pool",
            False,
        )
        mode = "openai_web_search"
    else:
        candidates = fetch_json_with_chat(api_key, resolved_base_url, model_name, candidate_prompt, candidate_count)
        mode = "compatible_chat_no_builtin_search" if provider_name != "openai" else "openai_chat_no_builtin_search"
    shortlist_prompt = build_user_prompt(
        country,
        procurement_need,
        buyer_count,
        allow_no_live_search=mode != "openai_web_search",
        strategy=strategy,
        stage="shortlist",
        candidates=candidates,
    )
    if mode == "openai_web_search":
        buyers = fetch_json_with_openai_responses(
            api_key,
            resolved_base_url,
            model_name,
            shortlist_prompt,
            "qualified_buyer_shortlist",
        )
    else:
        buyers = fetch_json_with_chat(api_key, resolved_base_url, model_name, shortlist_prompt, buyer_count)
    if not buyers and candidates:
        buyers = candidates[:buyer_count]
        for item in buyers:
            notes = str(item.get("research_notes", "") or "").strip()
            item["research_notes"] = (notes + "；二阶段筛选返回空，已使用候选池兜底，需人工复核。").strip("；")
            item.setdefault("confidence", "low")
            item.setdefault("risks", "Shortlist stage returned no qualified buyers; verify fit and official sources manually.")
            for score_key in ("fit_score", "demand_score", "import_score", "verification_score", "total_score"):
                item.setdefault(score_key, 50)
    if not buyers:
        raise RuntimeError(
            "Buyer research returned 0 candidates. "
            "Try relaxing excluded company types, adding preferred application industries, "
            "or using OpenAI web search when official/source evidence is required."
        )
    return buyers, {
        "provider": provider_name,
        "base_url": resolved_base_url,
        "model": model_name,
        "mode": mode,
        "research_mode": resolved_mode,
        "candidate_count": len(candidates),
        "shortlist_count": len(buyers),
        "procurement_need": procurement_need,
        "strategy": strategy or {},
    }


def normalize_buyers(buyers: list[dict[str, Any]], country: str, research_meta: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    no_builtin_search = research_meta.get("mode") == "compatible_chat_no_builtin_search"
    for item in buyers:
        notes = (item.get("research_notes") or "").strip()
        if no_builtin_search:
            notes = (notes + "\uff1b\u517c\u5bb9\u6a21\u578b\u672a\u4f7f\u7528\u5185\u7f6e\u8054\u7f51\u641c\u7d22\uff0c\u5efa\u8bae\u4eba\u5de5\u590d\u6838\u5b98\u7f51\u3002").strip("\uff1b")
        scores = {}
        for key in ("fit_score", "demand_score", "import_score", "verification_score", "total_score"):
            try:
                scores[key] = max(0, min(100, int(item.get(key, 0) or 0)))
            except (TypeError, ValueError):
                scores[key] = 0
        source_urls = item.get("source_urls")
        if not isinstance(source_urls, list):
            source_urls = []
        products = refine_buyer_products(
            item.get("products", ""),
            str(research_meta.get("procurement_need", "")),
            buyer_evidence_context(item),
        )
        if products == "\u9700\u6838\u5b9e\u5177\u4f53\u8bbe\u5907":
            notes = (notes + "\uff1b\u5f53\u524d\u516c\u5f00\u8bc1\u636e\u4ec5\u80fd\u786e\u8ba4\u5230\u54c1\u7c7b\u7ea7\uff0c\u9700\u4eba\u5de5\u6838\u5b9e\u5177\u4f53\u91c7\u8d2d\u8bbe\u5907\u3002").strip("\uff1b")
        normalized.append(
            {
                "name": (item.get("name") or "").strip(),
                "country": country,
                "website": normalize_website(item.get("website", "")),
                "products": products,
                "bio": pad_or_trim_bio(item.get("bio", "")),
                "logo_path": "",
                "site_image_path": "",
                "research_notes": notes,
                "buyer_type": str(item.get("buyer_type", "") or "").strip(),
                "demand_scenarios": str(item.get("demand_scenarios", "") or "").strip(),
                "local_presence": str(item.get("local_presence", "") or "").strip(),
                "import_signal": str(item.get("import_signal", "") or "").strip(),
                "evidence": str(item.get("evidence", "") or "").strip(),
                "source_urls": [str(url).strip() for url in source_urls if str(url).strip()],
                **scores,
                "confidence": str(item.get("confidence", "") or "").strip().lower(),
                "risks": str(item.get("risks", "") or "").strip(),
            }
        )
    normalized.sort(key=lambda item: (item["total_score"], item["verification_score"], item["demand_score"]), reverse=True)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Research buyer profiles from country and procurement need.")
    parser.add_argument("--country", required=True, help="Target country")
    parser.add_argument("--procurement-need", required=True, help="Target procurement need or product direction")
    parser.add_argument("--output", required=True, help="Output buyers.json path")
    parser.add_argument("--workspace", required=True, help="Workspace directory for future research artifacts")
    parser.add_argument("--buyer-count", type=int, default=5, help="Number of buyers to generate")
    parser.add_argument("--model", help="Optional model override")
    parser.add_argument("--provider", help="Model provider: openai, deepseek, qwen, zhipu, kimi, siliconflow, openrouter, ollama, lmstudio, or compatible")
    parser.add_argument("--base-url", help="Optional OpenAI-compatible base URL")
    parser.add_argument("--research-mode", help="model_only or openai_web_search")
    parser.add_argument("--preferred-industries", default="", help="Preferred industries or application scenarios")
    parser.add_argument("--excluded-company-types", default="", help="Company types or profiles to exclude")
    parser.add_argument("--custom-requirements", default="", help="Additional natural-language qualification requirements")
    parser.add_argument("--prefer-import-evidence", action="store_true", help="Prioritize companies with public import or trade evidence")
    parser.add_argument("--candidate-multiplier", type=int, default=3, help="Candidate pool multiplier before qualification")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        strategy = {
            "preferred_industries": args.preferred_industries,
            "excluded_company_types": args.excluded_company_types,
            "custom_requirements": args.custom_requirements,
            "prefer_import_evidence": args.prefer_import_evidence,
            "candidate_multiplier": args.candidate_multiplier,
        }
        buyers, research_meta = fetch_buyers(
            args.country,
            args.procurement_need,
            args.buyer_count,
            args.model,
            args.provider,
            args.base_url,
            args.research_mode,
            strategy,
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from None
    normalized = normalize_buyers(buyers, args.country, research_meta)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    notes = {
        "country": args.country,
        "procurement_need": args.procurement_need,
        "buyer_count": args.buyer_count,
        **research_meta,
    }
    (workspace / "research-meta.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
