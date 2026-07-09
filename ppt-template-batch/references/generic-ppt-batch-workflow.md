# Generic PPT Batch Workflow

Use this reference when the user's goal is broader than buyer-board production: any PPT template should be decomposed, mapped to structured data, batch-filled, checked, and exported.

## Core intent

The skill is a general PPT template automation workflow. Buyer boards and buyer briefings are presets built on top of the same engine, not the whole product.

The reusable sequence is:

1. Receive a PPT/PPTX template or a manually adjusted reference deck.
2. Decompose slide structure, text boxes, tables, image placeholders, styling, and fixed content.
3. Generate a machine-readable layout config.
4. Define the input data schema for the template.
5. Fill text while preserving template styles and run structure when possible.
6. Replace images only inside approved image slots.
7. Export one or many finished PPT files.
8. Verify slide count, required fields, missing text, encoding, and obvious layout regressions.

## Template decomposition checklist

Always identify:

- which slides are fixed and should not be modified
- which slides are repeated pages
- which text boxes are titles, section labels, body fields, footers, warnings, or decorative text
- which table rows and columns hold field labels and values
- which images are placeholders versus fixed design elements
- font family, size, color, bold, alignment, and line wrapping behavior
- whether text replacement should keep existing runs or rebuild a text frame
- how to duplicate or trim repeated slides to match data count

## Data contract pattern

Prefer explicit JSON data for repeatable runs:

- `records.json` or a domain-specific name such as `buyers.json`
- `layout-config.json`
- optional `assets/` folder for images
- optional `batch.json` when generating multiple PPT files from the same template

For new template families, start with a small manual dataset and verify one output before scaling up.

Read `layout-config-schema.md` when a generic template needs executable mappings. The generic runner supports text shapes, table cells, token placeholders, image slots, repeated slide duplication, extra slide trimming, required-field reporting, and per-job JSON reports.

## Replacement rules

- Preserve template text styles by default.
- For templates with multiple styled runs, replace run text in place instead of clearing the whole text frame.
- For table-style templates, copying the first run style is usually acceptable.
- Keep fixed footer or compliance text unless the user explicitly asks to remove it.
- Do not invent extra fields just because a previous domain used them.
- Avoid over-shrinking text; prefer concise source copy and user-visible review.
- Use ASCII paths for intermediate files on Windows when Chinese paths cause PowerShell/Python encoding issues.

## Generic one-click commands

Single output:

```bash
python scripts/run_ppt_batch_pipeline.py ^
  --template "path/to/template.pptx" ^
  --records "path/to/records.json" ^
  --layout-config "path/to/layout-config.json" ^
  --output "output/finished.pptx" ^
  --workspace "output/workspace"
```

Multiple outputs:

```bash
python scripts/run_ppt_batch_pipeline.py ^
  --batch "path/to/batch.json" ^
  --output-dir "output/decks" ^
  --workspace "output/workspace"
```

Use `ppt-template-batch/scripts/fill_ppt_from_records.py` directly when embedding the filler into another workflow.

## Domain presets

Buyer-board preset:

- one buyer per content slide
- company name, country, website, products, and 120-Chinese-character bio
- optional logo and right-side image sourcing

Buyer-briefing preset:

- one category per slide
- 6 buyers per slide
- short company intro and `采购品类：...` line
- strict run-level style preservation

Future presets can use the same pattern, for example:

- exhibitor lists
- product catalogs
- quote sheets
- training decks
- monthly reports
- country/category market snapshots

