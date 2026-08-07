# Crawl4AI Asset Recovery

The buyer-board asset fetcher has four modes:

- `light`: the default bounded HTML fetcher.
- `crawl4ai`: light fetching followed by an explicit Crawl4AI recovery pass when the Logo or site visual is missing.
- `auto` and `browser`: compatibility values that keep browser network access disabled and record the safety skip.

## Service Boundary

Run Crawl4AI as a separate local service using its official Docker/self-hosting instructions:

<https://github.com/unclecode/crawl4ai/tree/main/deploy/docker>

The buyer-board client accepts only an `http` loopback endpoint. The default is:

```text
http://127.0.0.1:11235/crawl
```

An alternate loopback endpoint can be supplied with `BUYER_BOARD_CRAWL4AI_ENDPOINT`. If the service requires authentication, set `BUYER_BOARD_CRAWL4AI_TOKEN`; the token is never written to the asset report.

Keep the Crawl4AI service's SSRF and egress protections enabled. Do not enable internal URL access, arbitrary hooks, undetected-browser mode, or unrestricted proxies for this workflow. The local client also treats the service response as untrusted and revalidates every image URL before downloading it.

## Run

Start the service, then run the normal pipeline with an explicit mode:

```powershell
python ppt-template-batch/scripts/fetch_buyer_assets.py `
  --buyers buyers.json `
  --output buyers.with-assets.json `
  --assets-dir assets `
  --cache-file asset-cache.json `
  --report-file asset_fetch_report.json `
  --asset-mode crawl4ai
```

The pipeline first uses the deterministic light parser. The Crawl4AI request is made only when one of the two buyer-board visual slots is still missing. It renders the official homepage and up to two same-site pages selected by product/about hints. Returned `media.images` and rendered HTML candidates go through the existing safe downloader, image-size checks, Logo scoring, cache, and PPT placement code.

Review these report fields after a recovery run:

- `crawl4ai_used`
- `crawl4ai_pages`
- `crawl4ai_candidate_count`
- `crawl4ai_error`
- `logo_confidence`, `logo_source`, and `logo_rejected_candidates`

This recovery mode is for the desktop Python workflow only. The Feishu/Aily package continues to use the platform's native web and image capabilities and does not call the local Crawl4AI service.
