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

SYSTEM_PROMPT = """You are a B2B buyer research assistant.
Your task is to find relevant potential buyers or procurement companies for a target country and procurement need.
Return only valid JSON. Do not include markdown or commentary.
Each buyer must include: company name, country, official website domain, specific procurement products, a Simplified Chinese company bio, empty logo_path, empty site_image_path, and one research note.
The bio field must contain exactly 120 Chinese ideographs. Use Simplified Chinese. Products should be concrete and separated with Chinese commas or enumeration punctuation.
Prefer real companies with clear official websites and a strong business fit. Avoid vague or unverifiable entities.
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
    trimmed = "".join(chars)
    count = chinese_char_count(trimmed)
    if count == 120:
        return trimmed
    if count > 120:
        output = []
        total = 0
        for ch in trimmed:
            output.append(ch)
            if "\u4e00" <= ch <= "\u9fff":
                total += 1
                if total >= 120:
                    break
        result = "".join(output).rstrip(allowed_punctuation)
        while chinese_char_count(result) < 120:
            result += "\u3002"
        return result
    filler = "\u8be5\u4f01\u4e1a\u5728\u5f53\u5730\u884c\u4e1a\u5177\u5907\u7a33\u5b9a\u91c7\u8d2d\u80fd\u529b\u4e0e\u660e\u786e\u5408\u4f5c\u9700\u6c42\u3002"
    result = trimmed
    while chinese_char_count(result) < 120:
        for ch in filler:
            result += ch
            if chinese_char_count(result) >= 120:
                break
    return pad_or_trim_bio(result)


def build_user_prompt(country: str, procurement_need: str, buyer_count: int, allow_no_live_search: bool = False) -> str:
    no_search_note = "If the current model cannot browse the web, use known public information and mark research_notes as requiring manual website verification." if allow_no_live_search else ""
    return f"""Target country or region: {country}
Procurement need: {procurement_need}
Buyer count: {buyer_count}
{no_search_note}

Selection rules:
- Choose real companies with clear official website domains and strong business fit.
- The target is actual buyers/procurement accounts: end users that consume the product in operations, distributors/importers/resellers that buy for resale, EPC/project developers/integrators/maintenance contractors that buy for projects, or large groups with centralized procurement.
- Do not list a manufacturer only because it is in the same industry. A manufacturer is valid only when it likely purchases the requested product as production equipment, process equipment, components, consumables, spare parts, or resale inventory.
- Exclude or downgrade direct competing OEMs whose main business is making and selling the same requested product, unless public business fit suggests importing/distribution or internal use.
- The products field must describe what the company would buy, not what it sells.
- research_notes must briefly state buyer_type and procurement_rationale, for example: end_user_factory; uses laser marking for traceability on automotive components.
- Avoid entities with vague websites, weak procurement relevance, or unclear purchase scenario.

Return JSON in this exact structure:
{{
  "buyers": [
    {{
      "name": "Company legal or common full name",
      "country": "{country}",
      "website": "official-domain.example",
      "products": "Specific procurement products in Chinese",
      "bio": "Exactly 120 Chinese ideographs in Simplified Chinese",
      "logo_path": "",
      "site_image_path": "",
      "research_notes": "Short reason for fit"
    }}
  ]
}}

The website value must be a domain only, without http or https.
"""


def parse_json_payload(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first:last + 1]
    return json.loads(text)


def buyer_result_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "buyers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "country": {"type": "string"},
                        "website": {"type": "string"},
                        "products": {"type": "string"},
                        "bio": {"type": "string"},
                        "logo_path": {"type": "string"},
                        "site_image_path": {"type": "string"},
                        "research_notes": {"type": "string"},
                    },
                    "required": ["name", "country", "website", "products", "bio", "logo_path", "site_image_path", "research_notes"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["buyers"],
        "additionalProperties": False,
    }


def fetch_buyers_with_openai_responses(api_key: str, base_url: str, country: str, procurement_need: str, buyer_count: int, model_name: str) -> list[dict[str, Any]]:
    request_payload = {
        "model": model_name,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(country, procurement_need, buyer_count)},
        ],
        "tools": [{"type": "web_search"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "buyer_research_result",
                "schema": buyer_result_schema(),
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


def fetch_buyers_with_chat(api_key: str, base_url: str, country: str, procurement_need: str, buyer_count: int, model_name: str) -> list[dict[str, Any]]:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(country, procurement_need, buyer_count, allow_no_live_search=True)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    try:
        response = api_post_json(base_url, "/chat/completions", api_key, payload)
    except RuntimeError as exc:
        if "response_format" not in str(exc) and "json_object" not in str(exc):
            raise
        payload.pop("response_format", None)
        response = api_post_json(base_url, "/chat/completions", api_key, payload)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices returned by chat completion: {json.dumps(response, ensure_ascii=False)[:1200]}")
    content = choices[0].get("message", {}).get("content") or "{}"
    payload = parse_json_payload(content)
    return payload.get("buyers", [])


def fetch_buyers(country: str, procurement_need: str, buyer_count: int, model: str | None, provider: str | None, base_url: str | None, research_mode: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider_name = clean_provider(provider)
    resolved_base_url = clean_base_url(provider_name, base_url)
    model_name = model or get_env_var("BUYER_RESEARCH_MODEL") or PROVIDER_DEFAULTS[provider_name]["model"]
    if not model_name:
        raise RuntimeError("Research model is not configured.")
    api_key = require_api_key()
    resolved_mode = clean_research_mode(research_mode)
    if provider_name == "openai" and resolved_mode == "openai_web_search":
        buyers = fetch_buyers_with_openai_responses(api_key, resolved_base_url, country, procurement_need, buyer_count, model_name)
        mode = "openai_web_search"
    else:
        buyers = fetch_buyers_with_chat(api_key, resolved_base_url, country, procurement_need, buyer_count, model_name)
        mode = "compatible_chat_no_builtin_search" if provider_name != "openai" else "openai_chat_no_builtin_search"
    return buyers, {"provider": provider_name, "base_url": resolved_base_url, "model": model_name, "mode": mode, "research_mode": resolved_mode}


def normalize_buyers(buyers: list[dict[str, Any]], country: str, research_meta: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    no_builtin_search = research_meta.get("mode") == "compatible_chat_no_builtin_search"
    for item in buyers:
        notes = (item.get("research_notes") or "").strip()
        if no_builtin_search:
            notes = (notes + "\uff1b\u517c\u5bb9\u6a21\u578b\u672a\u4f7f\u7528\u5185\u7f6e\u8054\u7f51\u641c\u7d22\uff0c\u5efa\u8bae\u4eba\u5de5\u590d\u6838\u5b98\u7f51\u3002").strip("\uff1b")
        normalized.append(
            {
                "name": (item.get("name") or "").strip(),
                "country": country,
                "website": normalize_website(item.get("website", "")),
                "products": re.sub(r"\s+", "", item.get("products", "")).strip("\uff0c\u3001"),
                "bio": pad_or_trim_bio(item.get("bio", "")),
                "logo_path": "",
                "site_image_path": "",
                "research_notes": notes,
            }
        )
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
    args = parser.parse_args()

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        buyers, research_meta = fetch_buyers(args.country, args.procurement_need, args.buyer_count, args.model, args.provider, args.base_url, args.research_mode)
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
