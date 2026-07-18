---
name: ppt-template-batch
description: General-purpose PowerPoint template decomposition and batch-generation workflow for PPT/PPTX files. Use when Codex needs to analyze any provided PPT template, extract reusable layout rules, create or refine layout-config mappings, batch-fill structured data into slides, preserve template text styles, replace approved image placeholders, duplicate or trim repeated slides, and export finished decks. Includes buyer-board and buyer-briefing presets for buyer research, company profiles, procurement categories, logos, website visuals, and 6-buyers-per-page briefing layouts, but the core skill is not limited to buyer-board projects.
---

# PPT Template Batch Workflow

## Overview

Use this skill when the goal is to turn a PowerPoint template into a repeatable production workflow.

The core workflow is domain-neutral:

1. Input a PPT/PPTX template or a manually adjusted reference deck.
2. Decompose slide structure, text placeholders, tables, images, fixed elements, and style rules.
3. Generate or refine `layout-config.json`.
4. Define the structured data schema needed by the template.
5. Fill one or many PPT files while preserving the template's visual language.
6. Replace images only in approved image slots.
7. Export finished PPT files and verify the output.

Buyer boards and buyer briefings are built-in presets on top of this workflow, not the boundary of the skill.

## Local Control Console

Use the local console when the user wants a project-oriented browser workflow instead of direct command-line execution. Read references/control-console.md before starting it.

From the repository root:

~~~powershell
python scripts/run_control_console.py
~~~

From an installed skill directory:

~~~powershell
python scripts/control_console.py
~~~

Keep the existing native PPTX template pipeline as the export engine. Use the console for preset selection, form entry, buyer research, session-only provider/model configuration, upstream model-list fetching, inspection, export, and run reporting. Treat Generic PPT as the default project type; use Buyer Board and Buyer Briefing only as presets.

## Portable agent package

For Feishu/Aily or another agent with native search, image, and slide capabilities, use the repository-level `feishu-agent-skill/` entrypoint. It is intentionally provider-neutral and does not ask the user for a model API Key or local Python dependencies. Build the Aily-compatible ZIP with `scripts/build_feishu_agent_skill.py`; the package contains a root-level SKILL.md and references/ only. Keep the desktop Python/PPTX engine separate for local runs.

Keep the execution boundary explicit: the desktop path owns the repository's Python/PPTX scripts, local console, deterministic asset fetcher, and optional COM/image fallback. The Feishu/Aily path owns native web search, image search, slide editing, and export; it must not install or invoke Python, `python-pptx`, Playwright, the desktop asset fetcher, or a remote-model CLI. Both paths should return source status and warnings for anything that was not verified.

## Workflow

### 1. Identify the template family

Classify the incoming PPT before filling content:

- Generic batch deck: arbitrary repeated pages, tables, cards, product blocks, report pages, catalogs, or profile pages.
- Buyer-board preset: one buyer per page, table fields, optional logo and right-side visual.
- Buyer-briefing preset: one category per page, six buyer slots per page, compact intro and `采购品类：...` lines.

For generic templates, read `references/generic-ppt-batch-workflow.md` first.
For buyer-board templates, also read `references/buyer-board-rules.md`.
For buyer-briefing templates, also read `references/buyer-briefing-rules.md`.

### 2. Freeze the source of truth

Use the user's latest manually adjusted PPT as the authoritative reference.

Preserve fixed elements unless the user explicitly asks to modify them:

- cover structure and fixed branding
- footers, disclaimers, or compliance text
- page labels, decorative elements, and non-placeholder images
- original typography, color, alignment, spacing, and run-level styling

Do not add fields from a previous project just because a previous template used them.

### 3. Decompose before replacing

Extract and document:

- slide count and repeated slide ranges
- title, subtitle, body, table, footer, and note placeholders
- table row and column mappings
- image placeholders and fixed images
- font family, size, color, bold, alignment, and line wrapping behavior
- whether text replacement should preserve existing runs or rebuild text frames
- whether repeated slides must be duplicated, trimmed, or kept fixed

Keep durable rules in a reference file when the template family will be reused, and keep executable mappings in `layout-config.json`.

Use `scripts/generate_layout_config.py` for a starter config when the template resembles the buyer-board table layout. For other layouts, generate a custom config after inspecting the PPT structure.

For generic templates, prefer the reusable config-driven filler before writing a dedicated script:

```bash
python scripts/run_ppt_batch_pipeline.py ^
  --template "template.pptx" ^
  --records "records.json" ^
  --layout-config "layout-config.json" ^
  --output "output/finished.pptx" ^
  --workspace "output/workspace"
```

### 4. Build the data contract

Prefer explicit JSON input for repeatability:

- `records.json` for generic templates
- `buyers.json` for buyer-board templates
- `briefing-pages.json` for buyer-briefing templates
- optional `assets/` for logos, screenshots, product images, or other visuals
- optional `batch.json` when producing many PPT files from one template

For new template families, test with a small dataset before scaling.

### 5. Fill text first

Fill text before touching images.

Rules:

- preserve existing template styles whenever possible
- replace text in place for multi-run text boxes
- use table cell style copying for table-based templates
- avoid aggressive font shrinking as a substitute for concise content
- use UTF-8-SIG JSON and ASCII intermediate paths on Windows when Chinese path or text encoding issues appear

Use these scripts when the template matches their data model:

- `scripts/fill_buyer_board_text.py` for buyer-board table pages
- `scripts/fill_buyer_briefing_pages.py` for six-slot-per-page briefing pages

For unrelated template families, write a small dedicated filler using the same principles: inspect placeholders, preserve styles, fill data, then verify.

Use `scripts/fill_ppt_from_records.py` for generic text, table, placeholder, image, and repeated-slide mappings. Read `references/layout-config-schema.md` before authoring a new generic `layout-config.json`.

Generic configs use `schema_version: 2`. Prefer `selector: {"name": "...", "role": "..."}` for stable shape matching; selectors resolve before `shape_id`/`shape_name` and the numeric `shape_index` compatibility fallback. Version 1 configs are normalized in memory. The shared generic report includes `ok`, `missing_required_fields`, `missing_assets`, `warnings`, `stale_template_text`, `capacity_warnings`, slide-count status, reopen status, and failed-record details. Outputs are written atomically only after the temporary PPTX can be reopened.

### 6. Insert images only after text is stable

Treat images as a separate pass:

- replace only approved placeholder slots
- Asset fetching should stay bounded: use the controlled light HTML path, extract official inline SVG marks when available, and enforce a per-buyer timeout. `asset_mode=auto` and `asset_mode=browser` remain accepted for CLI compatibility but never start Playwright or browser navigation; they safely skip the browser path and record `browser_skip:network_unsafe` when it is reached. Use `asset_fetch_report.json` to inspect misses instead of waiting indefinitely.
- Asset URLs must be `http` or `https`. Before each request, reject localhost and non-public IP literals or DNS results, including loopback, private, link-local, reserved, multicast, and unspecified addresses; validate the final URL of every redirect and keep redirects on the validated site by default. DNS resolution is bounded, curl pins the validated public address, redirects are capped at 5 hops, and Python, curl, and inline data reads are capped at 8 MiB.
- Never accept a logo solely because its filename contains `logo`: reject certification seals, government badges, sale-notice marks, banners, and low-confidence brand mismatches. Prefer a verified official brand mark, and leave the Logo slot empty when confidence is insufficient.
- Match the exact enterprise, not only the website domain: reject subsidiary and business-unit logos when the requested profile is for the parent company.
- do not overwrite fixed design imagery
- fit logos without distortion
- crop or pad right-side visuals before placement so they do not overflow
- clear stale placeholder graphics when no verified asset is available

For buyer-board asset discovery, use `scripts/fetch_buyer_assets.py --asset-mode light`, then use PowerPoint COM or the Python fallback image placer. Do not install Chromium or expect browser-based recovery; browser-related CLI values are compatibility-only and are safety-skipped.

### 7. Use buyer presets only when relevant

Buyer-board preset expects:

- `name`
- `country`
- `website`
- `products`
- `bio`
- optional `logo_path`
- optional `site_image_path`

If buyer data is missing and the user gives country plus procurement need, use `scripts/discover_buyer_profiles.py` to generate buyer profiles. Buyer research must build a broader candidate pool before scoring and shortlisting. Favor actual procurement accounts: local end users, distributors/importers/resellers, EPC/project developers, integrators, maintenance contractors, or manufacturers with a clear internal-use/component/resale purchase scenario. For component needs such as motors, require a concrete production, equipment, maintenance, project, or resale demand scenario. Prioritize public import, distribution, agency, cross-border sourcing, or trade evidence when available. Do not treat every manufacturer as a buyer by default, and downgrade direct competing OEMs unless they also show internal-use, import, or distribution demand.

Preserve qualification details in buyer records:

- `buyer_type`
- `demand_scenarios`
- `local_presence`
- `import_signal`
- `evidence`
- `source_urls`
- `fit_score`, `demand_score`, `import_score`, `verification_score`, `total_score`

For multi-product research, `products` must be a buyer-specific one-to-three-item subset justified by `demand_scenarios` and `evidence`; never copy the full global procurement request into every buyer. Use equipment-level names such as `切菜机、切肉机`, not category-level phrases such as `商用厨房设备、食品加工设备、中央厨房系统`. If public evidence is insufficient, mark the field for manual verification instead of presenting a broad category as a confirmed purchase.

For buyer-board tables, keep fixed identity rows unchanged and dynamically size the `products` and `bio` rows from actual line count. Preserve the template font and cell margins, update the table shape height, and do not move or overwrite the fixed header/footer. Replace titles and footer prompts inside their original shape/run; style overrides are opt-in only through `content.allow_style_overrides: true` for explicitly approved content fields.
- `confidence`
- `risks`

Use advanced research inputs when the user's target is specialized:

- `preferred_industries`
- `excluded_company_types`
- `custom_requirements`
- `prefer_import_evidence`
- `candidate_multiplier`

For generic templates, use `scripts/import_content_document.py` or the control console to import TXT, Markdown, CSV, JSON, or DOCX content into `records.json`. Keep the original `source_text` and the user's `source_instruction` in globals. Prefer the natural-language layout field for non-technical users, then verify the generated starter mapping against Template Structure.

Buyer-briefing preset expects pages with:

- `title`
- no more than 6 buyers per page; split larger inputs before filling
- buyer `name`
- buyer `summary`
- buyer `products`

The filler clears unused slots on pages with fewer than 6 buyers and preserves their original run styles. Its optional report records `missing_buyers`, `overlong_text`, and `warnings`; it rejects a page that exceeds the six-slot capacity.

For the separate `yitu-quanjie` preset, run `yitu-quanjie/scripts/yitu_quanjie_replace.py --dry-run` to validate mapped shape names, table coordinates, text capacity, table height, and the output path. The command prints JSON only and never creates or overwrites the output. A normal run repeats validation before saving; its report uses `missing_shapes`, `shape_errors`, `table_errors`, and `overflows`.

### 8. Diagnose runtime issues

When a run behaves differently in WorkBuddy, Windows, or a sandboxed environment, run:

- `scripts/doctor.py`
- inspect `asset_fetch_report.json` when a buyer-board PPT completed with missing real website assets

Check:

- Python modules
- PowerPoint COM availability
- network access
- controlled asset-fetch mode and `browser_skip:network_unsafe` notes
- model provider, Base URL, selected model, and API key visibility when research or AI visual fallback is needed

### 9. Verify every output

After export, verify:

- slide count
- required fields present
- no `??` encoding corruption
- fixed text preserved
- style consistency on title/body/table text
- no stale placeholder content from the template
- image placeholders cleared or replaced correctly

For generic exports, treat `stale_template_text`, `capacity_warnings`, `missing_assets`, `slide_count_status`, and `reopen_status` as the preflight review record. For buyer briefing, also review the six-slot and overlong-text warnings; for Yitu dry-runs, resolve every missing shape, table error, and overflow before allowing a normal save.

For batch jobs, write a JSON report listing each output file, slide count, missing required records, and corruption checks.

## Files To Read

- `references/generic-ppt-batch-workflow.md`
  Use for arbitrary PPT template decomposition and batch replacement tasks.
- `references/layout-config-schema.md`
  Use when authoring generic `layout-config.json` mappings for text, tables, images, placeholders, repeated slides, and batch jobs.
- `references/buyer-board-rules.md`
  Use only for buyer-board profile pages with one buyer per slide.
- `references/buyer-briefing-rules.md`
  Use only for compact buyer-briefing pages with one category and six buyer slots per slide.
- `references/buyer-board-workflow-changelog.md`
  Use as a regression checklist when a buyer-board export shows stale template text, incorrect row heights, incomplete repeated pages, or unreliable Logo assets.
- `scripts/generate_layout_config.py`
  Use when turning a reference PPT into a starter `layout-config.json`.
- `scripts/fill_ppt_from_records.py`
  Use for generic config-driven PPT filling that is not buyer-specific.
- `scripts/fill_buyer_board_text.py`
  Use for buyer-board table templates.
- `scripts/fill_buyer_briefing_pages.py`
  Use for compact buyer-briefing templates.
- `scripts/fetch_buyer_assets.py`
  Use for buyer-board public logo and website visual sourcing.
- `scripts/apply_buyer_board_images.ps1`
  Use when PowerPoint COM is available for final image placement and preview export.
- `scripts/apply_buyer_board_images_fallback.py`
  Use when COM is unavailable and image placement still needs to proceed.
- `scripts/discover_buyer_profiles.py`
  Use only when a buyer-oriented task requires buyer research from country plus procurement need.
- `scripts/import_content_document.py`
  Use when a generic PPT task needs TXT, Markdown, CSV, JSON, or DOCX source material converted into `records.json`.
- `scripts/doctor.py`
  Use when diagnosing dependency, network, PowerPoint, or environment-variable problems.

## Assets

Do not bundle real customer decks, real buyer samples, fetched logos, or website screenshots in the public skill. Keep only redacted templates or synthetic examples when examples are needed.

## Operating Notes

- Keep the general PPT automation direction first; keep buyer-board logic as a preset.
- Prefer deterministic `python-pptx` operations for text and table filling.
- Prefer PowerPoint COM for final image placement and preview export when available.
- Use Python fallback image placement when COM is unavailable.
- Keep scripts ASCII-friendly and use ASCII intermediate paths on Windows.
- Do not publish client-specific finished decks, private templates, or generated customer deliverables in the public repo.

