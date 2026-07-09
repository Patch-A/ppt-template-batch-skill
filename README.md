# PPT Template Batch Skill

General Codex skill for decomposing PowerPoint templates, mapping layout rules, filling structured data, replacing approved image slots, and batch-generating finished PPT decks.

This repository is focused on **generic PPT template automation**. Buyer-board and buyer-briefing workflows are bundled presets, not the limit of the skill.

## What this repo contains

- `ppt-template-batch/`: the Codex skill package.
- `ppt-template-batch/scripts/`: reusable PPT decomposition, text filling, image placement, diagnostics, and buyer preset scripts.
- `ppt-template-batch/references/`: workflow rules for generic PPT batch processing and buyer-specific presets.
- `scripts/run_buyer_board_pipeline.py`: buyer-board preset one-click pipeline.
- `scripts/recover_real_assets.py`: buyer-board asset recovery helper when sandboxed runs cannot fetch real web assets.

## Core workflow

Use this skill when you want to turn any PPT/PPTX template into a repeatable batch workflow:

1. Provide a PPT template or manually adjusted reference deck.
2. Decompose slide structure, repeated pages, text boxes, tables, image placeholders, fixed elements, and styling.
3. Generate or refine `layout-config.json`.
4. Define the data contract, such as `records.json`, `buyers.json`, or `briefing-pages.json`.
5. Fill text while preserving template fonts, colors, alignment, and run-level styles where needed.
6. Replace approved image placeholders without touching fixed design elements.
7. Export one or many PPT files.
8. Verify slide count, required fields, missing records, encoding, and obvious layout regressions.

## Supported modes

### Generic PPT batch mode

Use this when the template is not necessarily buyer-related: product catalogs, profile decks, reports, training pages, market snapshots, quote sheets, exhibitor lists, or other repeated PPT layouts.

Recommended artifacts:

- `template.pptx`
- `layout-config.json`
- `records.json`
- optional `assets/`
- optional `batch.json` for multiple output files

The current repo includes the workflow guidance for this mode in:

- `ppt-template-batch/references/generic-ppt-batch-workflow.md`
- `ppt-template-batch/scripts/generate_layout_config.py`

For highly custom layouts, create a small dedicated filler script after decomposing the template. Reuse the same principles: preserve styles, use structured data, avoid stale template content, and verify outputs.

### Buyer-board preset

Use this when each content slide represents one buyer profile and the deck needs company name, country, website, procurement products, company bio, optional logo, and optional website/product visual.

This preset supports:

- template-based buyer-board generation
- layout-config scaffold generation from a reference PPT
- country + procurement-need driven buyer research
- structured buyer text filling
- public website logo and visual fetching
- optional Playwright-enhanced asset fetching
- asset cache reuse through `asset-cache.json`
- per-run asset report through `asset_fetch_report.json`
- PowerPoint COM image placement with Python fallback
- WorkBuddy/Windows diagnostics through `doctor.py`

One-click existing buyer preset data:

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "path/to/template.pptx" ^
  --buyers "path/to/buyers.json" ^
  --layout-config "path/to/layout-config.json" ^
  --output "output/finished.pptx" ^
  --preview-dir "output/previews" ^
  --workspace "output/workspace"
```

One-click buyer research mode:

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "path/to/template.pptx" ^
  --country "南非" ^
  --procurement-need "动力传动" ^
  --buyer-count 10 ^
  --output "output/finished.pptx" ^
  --preview-dir "output/previews" ^
  --workspace "output/workspace"
```

### Buyer-briefing preset

Use this for compact `买家商情` templates where each slide contains one category and 6 buyer entries.

```bash
python ppt-template-batch/scripts/fill_buyer_briefing_pages.py ^
  "path/to/template.pptx" ^
  "path/to/briefing-pages.json" ^
  "output/buyer-briefing.pptx"
```

`briefing-pages.json` should contain pages with `title` and 6 buyers. Each buyer should include `name`, `summary`, and `products`. The script preserves run-level text styles so the output stays close to the original template.

## Dependencies

Install dependencies first:

```bash
pip install -r requirements.txt
```

Optional for browser-enhanced asset discovery:

```bash
playwright install chromium
```

Set your API key only when using buyer research or AI visual fallback:

```powershell
$env:OPENAI_API_KEY="your_key_here"
```

Optional model override:

```bash
set BUYER_RESEARCH_MODEL=gpt-4.1
```

## WorkBuddy and Windows diagnostics

If a run behaves differently after downloading through WorkBuddy, run:

```bash
python ppt-template-batch/scripts/doctor.py
```

The report checks:

- Python modules
- `OPENAI_API_KEY` visibility
- public website access
- Playwright and Chromium runtime
- PowerPoint COM automation

If Python `urllib` requests are blocked but `curl` works, enable:

```powershell
$env:BUYER_BOARD_ENABLE_CURL_FALLBACK="1"
```

## Buyer asset recovery

If a buyer-board run finishes with missing real logos or website visuals because the sandbox blocked network access, rerun only the asset stage locally:

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

## Output artifacts

Depending on the workflow, the workspace may contain:

- `layout-config.generated.json`: starter layout mapping
- `records.json`, `buyers.generated.json`, or `briefing-pages.json`: structured input data
- `buyers.with-assets.json`: buyer data enriched with fetched image paths
- `asset-cache.json`: per-site asset cache
- `asset_fetch_report.json`: per-buyer image hit report
- `pipeline_failure.json`: failure details when a pipeline stage fails
- `assets/`: downloaded public assets
- `previews/`: exported slide previews when available

## Current boundaries

- The generic PPT direction is active, but many bundled scripts still carry buyer-board names for compatibility.
- Arbitrary PPT templates still require first-run decomposition and mapping verification.
- Public website asset fetching is best-effort and depends on local network permissions.
- Browser-enhanced fetching improves dynamic-site coverage but increases runtime and local dependency weight.
- AI right-side visual fallback is opt-in and does not generate logos.
- When no verified image is available, the workflow should clear risky stale placeholders rather than inventing fake brand assets.

## Privacy note

Do not publish client-specific finished decks, private templates, generated previews, or real customer deliverables in this public repo.

When sharing examples, prefer:

- blank or redacted templates
- generic layout-config samples
- sanitized JSON examples
- workflow documentation rather than real customer outputs

## Roadmap

The next direction is to make the generic PPT layer more explicit:

- rename or alias the skill/repo to a generic PPT batch name after compatibility impact is reviewed
- add a generic `run_ppt_batch_pipeline.py` entrypoint
- add a broader layout-config generator for non-buyer templates
- add reusable validators for slide count, field coverage, style preservation, and stale placeholders
- keep buyer-board and buyer-briefing as bundled presets

## Sharing

This repository is public. Other users can clone it, download the ZIP, install the skill, and submit feedback through Issues or Discussions.


