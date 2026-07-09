from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from env_utils import get_env_var


SYSTEM_PROMPT = """你是企业采购买家研究助手。
目标：
1. 根据输入的国家和采购需求，筛选出最相关的潜在买家或采购商。
2. 每个买家输出企业名称、官网、具体采购产品、120个中文字符的企业简介。
3. 优先选择真实存在、官网明确、业务与采购方向高度匹配的企业。
4. 企业简介必须是简体中文，并且恰好120个中文字符，不要少于或多于120个中文字符。
5. 采购产品字段应尽量具体，使用中文顿号分隔。
6. 输出必须是合法JSON，不要输出JSON以外的任何文字。"""


def require_openai() -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: openai. Install it first with `pip install openai`, "
            "and set OPENAI_API_KEY before using auto research mode."
        ) from exc
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is required for auto research mode. "
            "On Windows, set it in the current shell with `$env:OPENAI_API_KEY='...'` "
            "or as a User environment variable, then restart the runner."
        )
    return OpenAI(api_key=api_key)


def normalize_website(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://", "", value, flags=re.I)
    return value.rstrip("/")


def chinese_char_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def pad_or_trim_bio(text: str) -> str:
    raw = re.sub(r"\s+", "", text or "")
    allowed_punctuation = "，。、；："
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
            result += "。"
        return result
    filler = "该企业在当地行业具备稳定采购能力与明确合作需求。"
    result = trimmed
    while chinese_char_count(result) < 120:
        for ch in filler:
            result += ch
            if chinese_char_count(result) >= 120:
                break
    return pad_or_trim_bio(result)


def build_user_prompt(country: str, procurement_need: str, buyer_count: int) -> str:
    return f"""请研究 {country} 市场中与“{procurement_need}”高度相关的潜在买家或采购商，输出 {buyer_count} 家企业。

筛选要求：
- 企业必须真实存在，优先官网明确、业务与采购方向高度匹配的企业。
- 优先终端买家、分销商、项目开发商、集成商、制造商或大型采购主体。
- 避免输出无明确官网、无业务匹配度、或信息过于模糊的企业。

输出 JSON 结构：
{{
  "buyers": [
    {{
      "name": "企业名称",
      "country": "{country}",
      "website": "官网域名",
      "products": "具体采购产品",
      "bio": "120字中文简介",
      "logo_path": "",
      "site_image_path": "",
      "research_notes": "一句话说明为什么匹配该采购需求"
    }}
  ]
}}

注意：
- bio 必须恰好120个中文字符。
- website 仅保留域名，不要带 http 或 https。
- products 必须根据该企业业务合理归纳，不要写泛泛的“相关产品”。
"""


def fetch_buyers(country: str, procurement_need: str, buyer_count: int, model: str | None) -> list[dict[str, Any]]:
    client = require_openai()
    model_name = model or get_env_var("BUYER_RESEARCH_MODEL") or "gpt-4.1"
    request_kwargs = {
        "model": model_name,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(country, procurement_need, buyer_count)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "buyer_research_result",
                "schema": {
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
                                "required": [
                                    "name",
                                    "country",
                                    "website",
                                    "products",
                                    "bio",
                                    "logo_path",
                                    "site_image_path",
                                    "research_notes",
                                ],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["buyers"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        },
    }
    response = None
    last_error = None
    for tool_type in ("web_search", "web_search_preview"):
        try:
            response = client.responses.create(tools=[{"type": tool_type}], **request_kwargs)
            break
        except Exception as exc:
            last_error = exc
    if response is None:
        raise RuntimeError(
            "Auto research request failed for both web_search and web_search_preview tool types. "
            "Check your OpenAI SDK version, model access, and network permissions."
        ) from last_error
    payload = json.loads(response.output_text)
    return payload["buyers"]


def normalize_buyers(buyers: list[dict[str, Any]], country: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in buyers:
        normalized.append(
            {
                "name": (item.get("name") or "").strip(),
                "country": country,
                "website": normalize_website(item.get("website", "")),
                "products": re.sub(r"\s+", "", item.get("products", "")).strip("，、"),
                "bio": pad_or_trim_bio(item.get("bio", "")),
                "logo_path": "",
                "site_image_path": "",
                "research_notes": (item.get("research_notes") or "").strip(),
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
    parser.add_argument("--model", help="Optional OpenAI model override")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    buyers = fetch_buyers(args.country, args.procurement_need, args.buyer_count, args.model)
    normalized = normalize_buyers(buyers, args.country)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    notes = {
        "country": args.country,
        "procurement_need": args.procurement_need,
        "buyer_count": args.buyer_count,
        "model": args.model or get_env_var("BUYER_RESEARCH_MODEL") or "gpt-4.1",
    }
    (workspace / "research-meta.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
