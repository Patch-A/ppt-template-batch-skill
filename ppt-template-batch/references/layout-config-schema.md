# Layout Config Schema

Use this reference when building a generic `layout-config.json` for `fill_ppt_from_records.py` or `run_ppt_batch_pipeline.py`.

## Minimal Shape Fill

```json
{
  "version": 2,
  "schema_version": 2,
  "record_key": "records",
  "required_fields": ["name", "summary"],
  "slides": [
    {
      "slide_index": 1,
      "texts": [
        {
          "selector": {"name": "Deck title", "role": "text"},
          "shape_index": 3,
          "field": "globals.deck_title"
        },
        {"shape_index": 5, "template": "{record.name}|{record.category}"}
      ]
    }
  ]
}
```

## Repeated Slide Fill

Use `repeat` when one source slide should be reused for every record.

```json
{
  "version": 2,
  "schema_version": 2,
  "record_key": "records",
  "required_fields": ["name", "summary", "products"],
  "repeat": {
    "source_slide_index": 2,
    "start_slide_index": 2,
    "template_slide_count": 1,
    "trim_extra_template_slides": true,
    "texts": [
      {
        "selector": {"name": "Buyer name", "role": "text"},
        "shape_index": 4,
        "field": "name",
        "mode": "clear"
      },
      {"shape_index": 8, "field": "summary", "mode": "clear"}
    ],
    "tables": [
      {
        "shape_index": 10,
        "cells": [
          {"row": 0, "col": 1, "field": "website"},
          {"row": 1, "col": 1, "field": "products"}
        ]
      }
    ],
    "images": [
      {"shape_index": 12, "field": "logo_path", "fit": "contain", "clear_if_missing": true},
      {"shape_index": 13, "field": "hero_image_path", "fit": "cover", "clear_if_missing": true}
    ]
  }
}
```

## Supported Mapping Keys

- `schema_version`: current writer version is `2`. Readers normalize version 1
  configs in memory and keep their numeric indexes as a fallback.
- `selector`: optional stable selector with `name` and/or semantic `role`.
  When it matches, it is resolved before `shape_index`; `shape_index` remains a
  compatibility fallback for older templates and configs.
- `texts`: replace a text shape by `selector`, `shape_index`, `shape_id`, or `shape_name`.
- `tables`: replace table cells under a table shape.
- `images`: replace an image placeholder or insert into explicit bounds.
- `placeholders`: replace tokens such as `{{title}}` inside existing text runs.
- `clear_shapes`: remove stale template placeholders.
- `required_fields`: report missing fields before export.

## Value Sources

- `field`: reads from the current record first, then globals, then root data.
- `record.name`: explicit current-record path.
- `globals.deck_title`: explicit global metadata path.
- `data.some_key`: explicit root JSON path.
- `template`: replaces `{record.name}` or `{globals.title}` tokens.
- `value`: static text.

## Image Rules

- Prefer stable `selector` values for reusable configs, while retaining
  `shape_index` on the same mapping for compatibility with older templates.
- Use `fit: contain` for logos and `fit: cover` for right-side hero/product visuals.
- Use `clear_if_missing: true` to remove stale placeholders when no verified asset exists.
- Relative image paths are resolved from the `records.json` folder.

Buyer-board configs may additionally use `content.dynamic_row_height: true`. The buyer-board filler keeps short identity rows fixed and recalculates the `products` and `bio` row heights from the populated text while preserving template typography. `content.allow_style_overrides` defaults to `false`; set it to `true` only when the user explicitly approves changing mapped text colors. Titles, footers, disclaimers, and other fixed elements must always inherit the template's original run styles.

## Batch Input

`records.json` can be a list:

```json
[
  {"name": "Example A", "summary": "Short summary"}
]
```

Or an object:

```json
{
  "globals": {"deck_title": "2026 Market Snapshot"},
  "records": [
    {"name": "Example A", "summary": "Short summary"}
  ]
}
```

## Beginner Console Usage

In the control console, non-technical users should use the example buttons first. The key idea is: `shape_index` is the element number shown in Template Structure; `field` is the data key from `records.json`; `repeat` means duplicate one template slide for many records; `images` means replace an image placeholder while keeping its bounds.

## Shared Preflight Report

Generic fills return a report with stable quality keys:

- `ok`, `missing_required_fields`, `missing_assets`, and `warnings`.
- `stale_template_text` for unresolved tokens or recognizable placeholder text.
- `capacity_warnings` plus `capacity.ok` for text that may exceed its shape.
- `expected_slide_count`, `slide_count`, and `slide_count_status`.
- `reopen_ok` and `reopen_status`, which are set only after the temporary PPTX
  is reopened successfully before atomic replacement.
- `failed_records` lists records skipped in non-strict repeated fills.

With `--strict`, missing required fields stop the fill before the requested
output is written. Without `--strict`, invalid records are reported and
isolated so valid records can still be rendered.
