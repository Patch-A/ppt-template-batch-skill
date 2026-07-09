# buyer-board-layout

Codex skill for buyer-board PPT template decomposition, buyer research, layout-config generation, content filling, image placement, and final export.

## What this repo contains

- `buyer-board-layout/`: the Codex skill
- `scripts/run_buyer_board_pipeline.py`: one-click unified entry script
- `scripts/recover_real_assets.py`: local rescue script for re-fetching real logos and site images after a sandboxed run

## Current maturity

This repository supports:

- template-based buyer-board generation
- compact buyer-briefing generation with 6 buyers per slide
- layout-config scaffold generation from a reference PPT
- structured buyer text filling
- country + procurement-need driven buyer research
- public-website buyer asset fetching
- optional Playwright-enhanced rendered-page asset fetching
- search-engine candidate page discovery as a supplement to site crawling
- social/profile/map candidate-page fallback discovery
- image candidate ranking plus size, aspect-ratio, and file-size filtering
- asset cache reuse through `asset-cache.json`
- per-run asset fetch reporting through `asset_fetch_report.json`
- smarter right-side visual preprocessing with whitespace trim, content-aware crop, and extreme-ratio fallback
- logo slot aspect fitting so square or wide logos are not distorted inside narrow template slots
- optional AI right-side visual fallback via `--enable-ai-visual-fallback`
- WorkBuddy/Windows runtime diagnostics through `doctor.py`
- PowerPoint COM image placement with Python fallback placement when COM is unavailable

## Input modes

### Mode 1: Existing buyers.json

Use this when you already have buyer data prepared.

### Mode 2: Auto-research mode

Use this when you only have:

- a PPT template
- a target country
- a procurement need

The pipeline will:

1. generate `layout-config.json` if you do not provide one
2. research buyers and generate `buyers.json`
3. try to fetch public logo and right-side visuals from each buyer's public web presence
4. fill the PPT
5. place verified image assets when available
6. remove placeholder images when assets are unavailable

### Mode 3: Buyer briefing mode

Use this for compact `买家商情` templates where each slide contains one category title and 6 buyer entries. This mode preserves the original PowerPoint run-level text styles instead of clearing and rebuilding text boxes.

## Dependencies

Install dependencies first:

```bash
pip install -r requirements.txt
```

Optional but recommended for browser-enhanced asset mode:

```bash
playwright install chromium
```

Set your API key for auto-research mode:

```bash
set OPENAI_API_KEY=your_key_here
```

PowerShell:

```powershell
$env:OPENAI_API_KEY="your_key_here"
```

Optional model override:

```bash
set BUYER_RESEARCH_MODEL=gpt-4.1
```

## One-click usage

### Existing buyers.json mode

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "buyer-board-layout/assets/examples/buyer-manual-reference.pptx" ^
  --buyers "buyer-board-layout/assets/examples/sa-buyers.json" ^
  --layout-config "buyer-board-layout/assets/examples/sa-layout-config.json" ^
  --output "output/finished.pptx" ^
  --preview-dir "output/previews" ^
  --workspace "output/workspace"
```

### Auto-research mode

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "path/to/template.pptx" ^
  --country "南非" ^
  --procurement-need "动力传动" ^
  --output "output/finished.pptx" ^
  --preview-dir "output/previews" ^
  --workspace "output/workspace"
```

Optional controls:

- `--buyer-count 5`
- `--layout-config path/to/layout-config.json`
- `--cover-title "南非动力传动买家"`
- `--cover-country "国家：南非"`
- `--content-title "南非动力传动买家"`
- `--openai-model gpt-4.1`
- `--asset-mode light|auto|browser`
- `--browser-timeout-ms 18000`
- `--enable-ai-visual-fallback`

Asset mode guidance:

- `light`: current lightweight mode, no browser rendering, lowest runtime cost
- `auto`: keep lightweight mode first, then use Playwright only when logo or right-side image is still missing
- `browser`: use Playwright-first rendered-page extraction, highest fetch success rate but heavier runtime

Token and runtime notes:

- `--asset-mode auto` and `--asset-mode browser` do not materially increase OpenAI token usage by themselves
- browser-enhanced modes do increase local runtime, dependency size, memory usage, and network requests
- `--enable-ai-visual-fallback` is the step that may add extra model cost when public right-side images cannot be found

### Buyer briefing mode

```bash
python buyer-board-layout/scripts/fill_buyer_briefing_pages.py ^
  "path/to/template.pptx" ^
  "path/to/briefing-pages.json" ^
  "output/buyer-briefing.pptx"
```

`briefing-pages.json` should contain pages with `title` and 6 buyers. Each buyer should include `name`, `summary`, and `products`. The `products` value may already include `采购品类：`; if it does not, the script adds it automatically.

Important guardrail:

- the current workflow does not AI-generate buyer logos
- AI fallback only applies to the right-side visual, and only when `--enable-ai-visual-fallback` is explicitly enabled

## WorkBuddy and Windows diagnostics

If auto-research, website image fetching, or PowerPoint export behaves differently after downloading the skill through WorkBuddy, run:

```bash
python buyer-board-layout/scripts/doctor.py
```

The report checks:

- whether `OPENAI_API_KEY` is visible from the current runner
- whether required Python modules are installed
- whether Playwright is installed and Chromium can launch successfully
- whether public website requests are allowed
- whether PowerPoint COM automation is available

If Python `urllib` requests are blocked but `curl` works in your environment, enable the optional curl fallback:

```powershell
$env:BUYER_BOARD_ENABLE_CURL_FALLBACK="1"
```

The unified pipeline also writes `pipeline_failure.json` inside `--workspace` when a key stage fails.

## WorkBuddy local rescue for real assets

If a WorkBuddy-downloaded run finishes with missing real website assets, blank logo slots, or AI right-side visuals only, the most common reason is that the WorkBuddy sandbox blocked outbound HTTPS requests during the asset-fetch stage.

Recommended fix: rerun only the asset stage locally in your own PowerShell or terminal, outside the WorkBuddy sandbox.

1. Install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

2. Check local readiness:

```bash
python buyer-board-layout/scripts/doctor.py
```

3. Run local real-asset recovery against the existing workspace:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recover_real_assets.ps1 `
  -Workspace "output/workspace" `
  -AssetMode browser
```

Equivalent Python command:

```bash
python scripts/recover_real_assets.py ^
  --workspace "output/workspace" ^
  --asset-mode browser
```

This recovery pass will:

- reuse `buyers.generated.json` or the best buyers JSON found in the workspace
- refetch official logo and right-side website visuals locally
- regenerate `asset_fetch_report.json`
- rebuild a recovered PPT as `recovered-real-assets.pptx`

If you only want the refreshed JSON and downloaded assets, without regenerating the PPT:

```bash
python scripts/recover_real_assets.py ^
  --workspace "output/workspace" ^
  --asset-mode browser ^
  --skip-ppt-refresh
```

If you no longer have the original workspace folder, rerun the full pipeline locally with the original template, country, and procurement need, and prefer `--asset-mode browser`.

## Workspace outputs

The unified pipeline may produce these reusable artifacts inside `--workspace`:

- `buyers.generated.json`: AI-researched buyer list
- `buyers.with-assets.json`: buyer list enriched with fetched asset paths
- `buyers.recovered-assets.json`: local second-pass buyer list after real-asset recovery
- `layout-config.generated.json`: starter layout config when one is not supplied
- `asset-cache.json`: site-level asset cache to avoid duplicate fetching
- `asset_fetch_report.json`: per-buyer hit report for logo and right-side visual sourcing
- `buyer-board-buyers.recovered.json`: recovered buyers JSON copied into the local workspace for PPT image replacement
- `buyer-board-doctor-report.json`: optional runtime diagnostic report
- `pipeline_failure.json`: failure details when a pipeline stage fails
- `assets/`: downloaded public image assets
- `research/`: intermediate buyer research files

## Current boundary

The current workflow can automatically generate:

- buyer name
- website
- procurement products
- 120-Chinese-character company bio

It can also continue the PPT pipeline even when no verified logo or right-side image is available.

Current limitations:

- public buyer text research is automated but still depends on model quality and source availability
- public website asset fetching is automatic but best-effort and depends on local network permissions
- browser-enhanced asset fetching improves dynamic-site coverage but still depends on local browser runtime and network permissions
- WorkBuddy may complete the PPT while failing the real-asset fetch stage if its sandbox blocks outbound HTTPS
- social/profile/map pages are fallback sources, not the first-choice primary source for brand assets
- AI right-side visual fallback is opt-in and requires a valid OpenAI API key
- when no verified image is available, the workflow clears placeholder graphics instead of inventing a risky fake logo
- if a logo asset is SVG, the Python fallback path still requires a working cairo runtime in addition to `cairosvg`

## Privacy note

Do not publish client-specific finished decks, private sample projects, generated preview outputs, or real customer deliverables in the public repo or release assets.

When sharing this skill publicly, prefer:

- blank or redacted templates
- generic `layout-config.json` samples
- sanitized `buyers.json` examples
- workflow documentation rather than real customer deliverables

## Layout-config generator scaffold

Use the generator when you have a new manually adjusted PPT and want a starter config:

```bash
python buyer-board-layout/scripts/generate_layout_config.py ^
  --template "path/to/reference.pptx" ^
  --output "path/to/layout-config.json" ^
  --cover-title "请替换封面标题" ^
  --cover-country "国家：请替换" ^
  --content-title "请替换内容页标题"
```

The generator currently:

- detects likely cover title and country text boxes
- detects the first content table and row labels
- detects likely content title and footer text boxes
- extracts per-slide logo and right-image slot heuristics

This output is a starter scaffold and should still be visually checked before production use.

## Sharing

This repository is public. Other users can open it, clone it, download the ZIP, and install or adapt the skill.

## Feedback loop

Use:

- `Issues` for bugs and feature requests
- `Discussions` for general feedback, usage reports, and template-sharing
- `Releases` for stable downloadable versions



