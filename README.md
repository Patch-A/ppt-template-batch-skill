# buyer-board-layout

Codex skill for buyer-board PPT template decomposition, layout-config generation, content filling, image placement, and final export.

## What this repo contains

- `buyer-board-layout/`: the actual Codex skill
- `scripts/run_buyer_board_pipeline.py`: one-click entry script

## Current maturity

This repository already supports:

- template-based buyer-board generation
- layout-config scaffold generation from a reference PPT
- structured buyer text filling
- separate logo and site-image placement
- PowerPoint COM image placement with preview export
- Python fallback image placement when PowerPoint COM is unavailable
- one-click pipeline execution

It is currently strongest when used with:

- a manually adjusted reference PPT
- explicit buyer JSON data
- explicit `layout-config.json`

The workflow is now:

1. Input template or manually adjusted reference PPT
2. Generate or refine `layout-config.json`
3. Prepare `buyers.json`
4. Run the one-click pipeline
5. Inspect exported PPT and preview PNGs

## V3 updates

This version adds:

- left-aligned logo placement that matches the table block
- product-first right-image selection guidance
- crop-to-frame right-image fitting instead of overflow-prone scaling
- AI-generated fallback visuals when official imagery is unavailable
- automatic Python fallback when PowerPoint COM is not available

Right-side image selection now follows a strict priority:

1. official product image or image with clear product elements
2. official project or brand image
3. official website screenshot
4. AI-generated fallback only when public official imagery is unavailable or unusable

## One-click usage

Example:

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "buyer-board-layout/assets/examples/buyer-manual-reference.pptx" ^
  --buyers "buyer-board-layout/assets/examples/sa-buyers.json" ^
  --layout-config "buyer-board-layout/assets/examples/sa-layout-config.json" ^
  --output "output/sa-finished.pptx" ^
  --preview-dir "output/previews" ^
  --workspace "output/workspace"
```

Optional title overrides:

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "buyer-board-layout/assets/examples/buyer-manual-reference.pptx" ^
  --buyers "buyer-board-layout/assets/examples/sa-buyers.json" ^
  --layout-config "buyer-board-layout/assets/examples/sa-layout-config.json" ^
  --output "output/sa-finished.pptx" ^
  --preview-dir "output/previews" ^
  --workspace "output/workspace" ^
  --cover-title "2026南非新能源买家" ^
  --cover-country "国家：南非" ^
  --content-title "南非买家需求"
```

The script generates:

- a text draft PPT
- a final PPT with logos and visuals
- slide preview PNG files when PowerPoint COM is available
- a preview note when the Python fallback path is used

## Example project

This repo now includes a configuration-driven sample project at `examples/sa-power-transmission/`.

It contains:

- `buyers.json`: buyer content and image paths
- `layout-config.json`: extracted placement and field mapping rules
- `images/`: selected logo and right-side visual assets used by the sample
- `self-check-notes.md`: review notes, fallback rationale, and next optimization ideas

The latest refined deliverable produced from this sample is published as a release asset so users can compare the runnable pipeline with a finished output deck.

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
