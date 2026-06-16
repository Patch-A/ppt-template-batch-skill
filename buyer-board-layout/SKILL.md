---
name: buyer-board-layout
description: Build and automate buyer-board PowerPoint workflows that start from a user template, reverse-engineer the layout rules, generate or refine a layout-config, fill buyer/company content, place logos and website visuals, and export a finished deck. Use when Codex needs to turn a manually adjusted PPT buyer-board template into a repeatable production workflow, especially for title/table/logo/image mapping, buyer profile page generation, and template-to-output slide automation.
---

# Buyer Board Layout

## Overview

Use this skill when the job is not just "edit a PPT", but "standardize a buyer-board production workflow" based on a user-approved template. The expected sequence is:

1. Receive a PPT template or a manually adjusted reference deck.
2. Decompose the template into stable layout rules.
3. Save the executable mapping as `layout-config.json`.
4. Map input buyer/company data into the required fields.
5. Insert buyer logos and official website or brand visuals with separate sourcing logic.
6. Export a finished PPT and, when useful, slide preview images.

## Workflow

### 1. Freeze the source of truth

Use the user's manually adjusted PPT as the authoritative reference, not an earlier auto-generated draft.

Preserve these constraints unless the user explicitly changes them:

- Keep the cover structure unless asked to redesign it.
- Keep the footer `AI慧展说明`.
- Do not add extra fields the user did not request.
- Treat `logo` and right-side website image as separate assets and separate sourcing steps.

If there are multiple candidate PPTs in the workspace, prefer the one the user identified as the manually adjusted reference deck.

### 2. Decompose the template before filling content

Extract and document:

- Cover title, country tag, font sizes, font color, alignment.
- Content-page title position and style.
- Table position, row labels, font size, font color, line wrapping behavior.
- Footer text and whether it must be preserved.
- Buyer logo placement logic.
- Right-side website image placement logic.

Write or update a reusable rule file before trying to mass-produce pages. Use `references/buyer-board-rules.md` as the durable summary, and keep the live template mapping in `layout-config.json`.

### 3. Fill text in layers

Fill text before touching images.

Required text mapping for the standard buyer page:

- `company`
- `country`
- `website`
- `products`
- `bio`

Rules:

- Keep title text white.
- Keep body text blue close to `#2A49F4`.
- Prefer `Microsoft YaHei` for Chinese text unless the template clearly uses another font.
- Expand buyer introductions when the user requires a minimum character count.
- Do not shrink text aggressively just to force content to fit; prefer following the approved template proportions.

### 4. Insert logos and right-side visuals separately

Never crop a logo from the right-side website image.

Logo sourcing priority:

1. Official logo asset from the company site or official brand source.
2. Precise crop from the official site header or brand area.
3. User-specified manual crop only if the two options above fail.

Right-side image sourcing priority:

1. Official site hero image.
2. Official project or brand image.
3. Official website screenshot when a better brand visual is unavailable.

Avoid:

- Random full-page crops.
- Using a decorative illustration unrelated to the buyer's actual business.
- Reusing one image for both logo and site visual.

### 5. Use the two-stage generation pattern

Prefer a two-script or two-step workflow:

1. Generate a text-only PPT from the approved template, `buyers.json`, and `layout-config.json`.
2. Apply image replacement from buyer asset paths and export final PPT plus previews.

This pattern makes debugging much easier and prevents image failures from corrupting the text layer.

### 6. Verify visually

After export, inspect slide previews and check:

- Is the text color correct?
- Is the title still aligned to the approved template?
- Is the buyer logo real and legible?
- Is the right-side image sufficiently filled and visually balanced?
- Did any old template artifacts remain on slides that required logo replacement?

If the preview looks wrong, inspect the actual slide shape positions rather than guessing from code.

## Files To Read

Read these files when using this skill:

- `references/buyer-board-rules.md`
  Use when you need the decomposed layout standard and non-negotiable formatting rules.
- `references/sa-example-data.md`
  Use when you need a concrete sample of buyer input structure.
- `scripts/fill_buyer_board_text.py`
  Use when generating the text-only PPT layer from a template, structured buyer data, and `layout-config.json`.
- `scripts/apply_buyer_board_images.ps1`
  Use when replacing logo and right-side image assets in the PPT and exporting slide previews.
- `scripts/generate_layout_config.py`
  Use when turning a manually adjusted reference PPT into a starter `layout-config.json`.

## Assets

These bundled assets are reference-grade examples, not universal truth:

- `assets/examples/buyer-manual-reference.pptx`
  Example manually adjusted reference deck used to derive rules.
- `assets/examples/sa-text-draft-input.pptx`
  Example text-layer input deck for the image replacement step.
- `assets/examples/sa-images/`
  Example image assets and sourced logo/site visuals used during South Africa buyer-board production.
- `assets/examples/sa-layout-config.json`
  Example layout config that maps the South Africa template structure and image slots.

## Operating Notes

- Prefer `python-pptx` for deterministic text/table filling.
- Prefer PowerPoint COM automation for final image placement and preview export when the environment supports it.
- When shape names are unstable or non-ASCII, inspect slide coordinates and identify targets by position.
- If the latest generated PPT exists in the same folder as the text draft, do not accidentally reuse the generated output as the next input source.
- Keep scripts ASCII-friendly where possible to reduce encoding issues in PowerShell and automation.
- Treat the current version as parameterized and reusable, but not yet universally template-agnostic. For a new layout family, first decompose the template and create or update the matching `layout-config.json`.
