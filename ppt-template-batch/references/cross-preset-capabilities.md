# Cross-Preset Capabilities

Use this reference when any PPT template needs natural-language content work or official website assets. These capabilities belong to the main skill. Buyer Board and Buyer Briefing are only two consumers.

## Natural-language content

Use human-writing when available for drafting, editing, tightening, or reducing AI-like phrasing in explicitly approved prose fields. Typical fields include `title`, `subtitle`, `summary`, `intro`, `description`, `body`, `caption`, and `speaker_notes`.

Freeze the verified source data before rewriting. Keep IDs, record order, layout mappings, image paths, product specifications, prices, numbers, dates, URLs, citations, evidence, source status, scores, and confidence outside the editable allowlist. Do not let a writing pass add facts or make uncertain claims sound verified.

For batch work, save polished JSON separately and validate it before filling the PPT. Use the generic profile for ordinary presentation records and the buyer profile for buyer customer copy. Keep each rewritten field within the mapped shape capacity.

## Website assets

Use `scripts/fetch_record_assets.py` for arbitrary records that contain an official website field. Configure the URL, label, Logo output, and visual output field names instead of converting the records to a buyer schema.

Use light mode by default. Enable Crawl4AI only as an explicit recovery mode through an HTTP loopback service. Set `PPT_BATCH_CRAWL4AI_ENDPOINT` and optionally `PPT_BATCH_CRAWL4AI_TOKEN`; older buyer-prefixed names remain compatible.

Crawl4AI may render at most three same-site pages. Treat every returned URL as untrusted. Keep public-address validation, redirect limits, response-size limits, image-dimension filters, exact brand or identity checks, and asset reports enabled. Leave an asset field empty when confidence is insufficient.

The Feishu/Aily package uses its native search and image capabilities instead of the desktop Crawl4AI service, but it follows the same source, identity, and no-fabrication boundaries.
