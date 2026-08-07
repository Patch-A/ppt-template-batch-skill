# Cross-Preset Crawl4AI Asset Recovery

Crawl4AI is an optional website asset recovery capability for the whole PPT template batch skill. It helps generic records and bundled presets discover official Logos and page visuals on JavaScript-rendered sites. It does not decide research conclusions, verify business claims, select buyers, or bypass asset safety checks.

The shared asset engine has four modes:

- `light`: the default bounded HTML fetcher.
- `crawl4ai`: light fetching followed by an explicit Crawl4AI recovery pass when a Logo or visual is missing.
- `auto` and `browser`: compatibility values that keep browser network access disabled and record the safety skip.

## Service boundary

Run Crawl4AI as a separate local service using its official Docker or self-hosting instructions:

<https://github.com/unclecode/crawl4ai/tree/main/deploy/docker>

The desktop client accepts only an `http` loopback endpoint. The default is `http://127.0.0.1:11235/crawl`.

Set `PPT_BATCH_CRAWL4AI_ENDPOINT` for the shared client and `PPT_BATCH_CRAWL4AI_TOKEN` when authentication is required. The older `BUYER_BOARD_CRAWL4AI_ENDPOINT` and `BUYER_BOARD_CRAWL4AI_TOKEN` names remain compatible. Tokens are never written to reports.

Keep the service SSRF and egress protections enabled. Do not enable internal URL access, arbitrary hooks, undetected-browser mode, or unrestricted proxies. The client treats the service response as untrusted and revalidates every returned image URL.

## Generic records

Use custom field mappings for arbitrary PPT records:

```powershell
python scripts/fetch_record_assets.py `
  --records records.json `
  --output records.with-assets.json `
  --assets-dir output/assets `
  --cache-file output/asset-cache.json `
  --report-file output/asset-report.json `
  --url-field official_url `
  --label-field brand `
  --logo-field logo_path `
  --visual-field hero_image_path `
  --asset-mode crawl4ai
```

Buyer-board projects may continue using `ppt-template-batch/scripts/fetch_buyer_assets.py`; both commands share the same discovery and validation engine.

The engine first uses the deterministic light parser. Crawl4AI runs only when a required Logo or visual is still missing. It renders the supplied official homepage and up to two same-site pages selected by product and about-page hints. Returned media and rendered HTML candidates still pass public-URL validation, redirect limits, size limits, image-dimension checks, Logo scoring, cache rules, and PPT placement rules.

Review these report fields after recovery:

- `crawl4ai_used`
- `crawl4ai_pages`
- `crawl4ai_candidate_count`
- `crawl4ai_error`
- `logo_confidence`, `logo_source`, and `logo_rejected_candidates`

This recovery mode is for the desktop Python workflow. The Feishu/Aily package uses the platform native web and image capabilities and does not call the local Crawl4AI service.
