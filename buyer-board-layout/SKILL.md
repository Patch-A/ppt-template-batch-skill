---
name: buyer-board-layout
description: Build and automate buyer-board PowerPoint workflows that start from a PPT template, decompose or generate layout-config rules, research buyers from a country plus procurement need, fill buyer/company content, place logos and website visuals when available, and export a finished deck. Use when Codex needs to turn a manually adjusted PPT buyer-board template into a reusable production workflow, especially for buyer discovery, title/table/logo/image mapping, buyer profile page generation, and template-to-output slide automation.
---

# Buyer Board Layout

## Overview

Use this skill when the goal is not just "edit one PPT", but "turn a buyer-board template into a repeatable pipeline".

The workflow supports two entry modes:

1. Structured mode: the user already has `buyers.json`.
2. Auto-research mode: the user only provides the PPT template, target `country`, and `procurement need`.

Expected production sequence:

1. Input the PPT template or manually adjusted reference deck.
2. Generate or refine `layout-config.json`.
3. Either load existing `buyers.json` or research buyer profiles from `country + procurement need`.
4. Try to fetch public buyer logo and website visuals.
5. Fill buyer text fields into the approved template.
6. Place logos and right-side visuals when assets are available.
7. Export final PPT and previews when the environment supports them.

## Workflow

### 1. Freeze the source of truth

Use the user's manually adjusted PPT as the authoritative reference, not an earlier auto-generated draft.

Preserve these constraints unless the user explicitly changes them:

- Keep the cover structure unless asked to redesign it.
- Keep the footer `AI慧展说明`.
- Do not add extra fields the user did not request.
- Treat `logo` and right-side website image as separate assets and separate sourcing steps.

### 2. Decompose the template before filling content

Extract and document:

- cover title, country tag, font sizes, font color, alignment
- content-page title position and style
- table position, row labels, font size, font color, line wrapping behavior
- footer text and whether it must be preserved
- buyer logo placement logic
- right-side website image placement logic

Keep the durable rule summary in `references/buyer-board-rules.md`, and keep the executable mapping in `layout-config.json`.

If the user only provides a template, use `scripts/generate_layout_config.py` to create a starter config first.

### 3. Build buyer data

The standard buyer page expects these fields:

- `name`
- `country`
- `website`
- `products`
- `bio`
- `logo_path`
- `site_image_path`

If `buyers.json` is missing, use `scripts/discover_buyer_profiles.py` to generate it from:

- `country`
- `procurement need`
- optional `buyer_count`

Auto-research notes:

- prefer real companies with official websites
- prefer actual buyers, distributors, project developers, integrators, manufacturers, or large procurement entities
- output a 120-Chinese-character company bio
- normalize website to domain only
- read `OPENAI_API_KEY` from the current process first, then from Windows User/Machine environment variables when available
- write `pipeline_failure.json` in the workspace when the research stage fails

### 4. Fetch and rank image assets

After buyer data is generated, use `scripts/fetch_buyer_assets.py` to try to fetch:

- official logo assets
- favicon or header-brand assets
- right-side public visuals from `og:image` or product-like page images

Asset-sourcing refinements:

- do not stop at the homepage
- expand into same-domain product, solution, application, project, about, or company pages
- add search-engine candidate pages as a supplement to official-site discovery
- allow fallback candidate pages from public social/profile or map-style listings when the official site is weak or unavailable
- rank candidates before downloading them
- filter candidates by file size, image dimensions, and aspect ratio
- cache per-site asset fetch results so repeated runs do not refetch the same domain
- write a per-buyer sourcing summary to `asset_fetch_report.json`
- optionally generate an AI right-side visual when public assets still fail and the user enables the fallback
- optionally use `BUYER_BOARD_ENABLE_CURL_FALLBACK=1` when Python `urllib` is blocked but curl works

### 5. Fill text first

Fill text before touching images.

Rules:

- keep title text white
- keep body text blue near `#2A49F4`
- prefer `Microsoft YaHei` for Chinese text unless the template clearly uses another font
- do not shrink text aggressively just to force content to fit

### 6. Insert logos and right-side visuals separately

Never crop a logo from the right-side website image.

Logo sourcing priority:

1. official logo asset from the company site or official brand source
2. precise crop from the official site header or brand area
3. user-specified manual crop only if the two options above fail

Right-side image sourcing priority:

1. official product image or official visual with clear product elements
2. official project or brand image
3. official website screenshot
4. AI-generated industry-matched visual only when official sources are unavailable or unusable

Layout rules:

- logo must align to the left edge of the approved logo area so it lines up with the text table below
- logo assets must be fitted into the approved logo-slot aspect ratio before insertion, preserving original logo proportions
- right-side images must be preprocessed before placement, not blindly center-cropped
- trim obvious blank borders before right-side crop decisions
- use content-aware crop first, then fall back to a full-subject blurred-backdrop composition for extreme aspect ratios
- fill the approved right-side box without overflowing into the table or footer area

If image assets are missing in auto mode:

- remove placeholder graphics rather than leaving incorrect old images in place
- allow the PPT to export with text-only completeness

### 7. Use the unified pipeline

Prefer the unified entry script:

- `scripts/run_buyer_board_pipeline.py`

It supports:

- existing `buyers.json` mode
- `country + procurement need` auto-research mode
- auto-generated `layout-config.json` when the user only supplies a template
- workspace-level `asset-cache.json` and `asset_fetch_report.json` outputs
- optional `--enable-ai-visual-fallback` for right-side visual generation

### 8. Diagnose WorkBuddy or Windows issues

When a WorkBuddy run behaves differently from local PowerShell, run:

- `buyer-board-layout/scripts/doctor.py`

Use the report to check:

- whether `OPENAI_API_KEY` is visible to the current runner
- whether required Python modules are installed
- whether public website requests are allowed
- whether PowerPoint COM automation is available

### 9. Verify visually

After export, inspect previews and check:

- is the text color correct
- is the title aligned to the approved template
- is the buyer logo authentic and legible when present
- is the logo left-aligned with the table block
- is the right-side image filled and visually balanced when present
- were placeholder graphics cleared when no image asset was available

## Files To Read

- `references/buyer-board-rules.md`
  Use for the decomposed layout standard and formatting rules.
- `references/sa-example-data.md`
  Use for the expected buyer input structure.
- `scripts/discover_buyer_profiles.py`
  Use when the user only provides country and procurement need and Codex must generate buyer data first.
- `scripts/fill_buyer_board_text.py`
  Use when generating the text-only PPT layer from a template, structured buyer data, and `layout-config.json`.
- `scripts/fetch_buyer_assets.py`
  Use after buyer research when Codex should try to source public buyer logos and right-side visuals automatically.
- `scripts/apply_buyer_board_images.ps1`
  Use when replacing logo and right-side image assets in the PPT and exporting slide previews through PowerPoint COM.
- `scripts/apply_buyer_board_images_fallback.py`
  Use when PowerPoint COM is unavailable and Codex still needs to place logos and right-side visuals into the PPT.
- `scripts/generate_layout_config.py`
  Use when turning a manually adjusted reference PPT into a starter `layout-config.json`.
- `scripts/doctor.py`
  Use when diagnosing WorkBuddy, Windows environment-variable, network, dependency, or PowerPoint COM issues.

## Assets

These bundled assets are reference-grade examples, not universal truth:

- `assets/examples/buyer-manual-reference.pptx`
- `assets/examples/sa-text-draft-input.pptx`
- `assets/examples/sa-images/`
- `assets/examples/sa-layout-config.json`

## Operating Notes

- Prefer `python-pptx` for deterministic text and table filling.
- Prefer PowerPoint COM automation for final image placement and preview export when the environment supports it.
- If PowerPoint COM is unavailable, use the Python fallback image script rather than failing the whole pipeline.
- Auto-research mode depends on the OpenAI Python SDK and `OPENAI_API_KEY`.
- Keep scripts ASCII-friendly where possible to reduce encoding issues in PowerShell and automation.
- Treat the current version as configuration-driven and reusable, but still verify the first run of any new template family before mass production.
