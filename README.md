# buyer-board-layout

Codex skill for buyer-board PPT template decomposition, content filling, image placement, and final export.

## What this repo contains

- `buyer-board-layout/`: the actual Codex skill
- `scripts/run_buyer_board_pipeline.py`: one-click entry script

## Current maturity

This repository already supports:

- template-based buyer-board generation
- structured buyer text filling
- separate logo and site-image placement
- preview export

It is currently strongest when used with:

- a manually adjusted reference PPT
- explicit buyer JSON data
- explicit image placement config JSON

The next iteration direction is broader template generalization, so more layouts can be decomposed and filled with less manual coordinate setup.

## One-click usage

Example:

```bash
python scripts/run_buyer_board_pipeline.py ^
  --template "buyer-board-layout/assets/examples/buyer-manual-reference.pptx" ^
  --buyers "buyer-board-layout/assets/examples/sa-buyers.json" ^
  --config "buyer-board-layout/assets/examples/sa-image-config.json" ^
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
- slide preview PNG files

## Sharing

This repository is public. Other users can open it, clone it, download the ZIP, and install or adapt the skill.

## Feedback loop

Use:

- `Issues` for bugs and feature requests
- `Discussions` for general feedback, usage reports, and template-sharing
- `Releases` for stable downloadable versions
