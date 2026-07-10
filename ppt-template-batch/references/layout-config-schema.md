# Layout Config Schema

Use this reference when building a generic `layout-config.json` for `fill_ppt_from_records.py` or `run_ppt_batch_pipeline.py`.

## Minimal Shape Fill

```json
{
  "version": 1,
  "record_key": "records",
  "required_fields": ["name", "summary"],
  "slides": [
    {
      "slide_index": 1,
      "texts": [
        {"shape_index": 3, "field": "globals.deck_title"},
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
  "version": 1,
  "record_key": "records",
  "required_fields": ["name", "summary", "products"],
  "repeat": {
    "source_slide_index": 2,
    "start_slide_index": 2,
    "template_slide_count": 1,
    "trim_extra_template_slides": true,
    "texts": [
      {"shape_index": 4, "field": "name", "mode": "clear"},
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

- `texts`: replace a text shape by `shape_index`, `shape_id`, or `shape_name`.
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

- Prefer `shape_index` placeholders because bounds come from the template.
- Use `fit: contain` for logos and `fit: cover` for right-side hero/product visuals.
- Use `clear_if_missing: true` to remove stale placeholders when no verified asset exists.
- Relative image paths are resolved from the `records.json` folder.

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
