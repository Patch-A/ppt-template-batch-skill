# Buyer Briefing Rules

Use this reference for short "buyer briefing" PPT templates where each slide contains one procurement category and multiple compact buyer entries.

## Page model

- One slide contains one category title, usually only the product category such as `烘焙机械`.
- One slide contains up to 6 buyers by default.
- Each buyer entry has only two text blocks:
  - company intro, including the buyer name
  - procurement category line, formatted as `采购品类：XXXX等`
- Do not add country names to the category title unless the template already does so.
- Do not fill unused fields from long buyer-board decks, such as website, annual procurement scale, logo, or right-side visual.

## Intro copy rules

- Keep the intro as company-description copy, not procurement-judgment copy.
- Include the company name at the beginning.
- Target roughly 40 Chinese characters so the text visually approaches 2 lines in compact templates.
- Avoid very short one-line intros unless the placeholder area is visibly small.
- Keep the sentence factual and compact, for example: `Bonn是印度知名烘焙食品集团，覆盖面包、蛋糕和饼干业务，并在北印度拥有稳定产销网络。`

## Style preservation

For this template family, preserve the original text frame and run structure whenever possible:

- Do not clear and rebuild the whole text frame unless the template has no usable runs.
- Put the buyer name in the first run and the remaining intro in the second run.
- Clear extra runs by setting their text to an empty string, which preserves the original run styles without leaving old text.
- Put procurement categories in the existing first run of the procurement text box.
- Read JSON with `utf-8-sig` and write JSON/PPT inputs with UTF-8 to avoid PowerShell Chinese text corruption.

Use `scripts/fill_buyer_briefing_pages.py` for this flow.

## Default mapping

The bundled script includes the mapping used by the 2026 India buyer-briefing template:

- title: shape 5
- buyer 1: summary shape 15, products shape 23
- buyer 2: group 16 child 2, group 16 child 3
- buyer 3: group 17 child 2, group 17 child 3
- buyer 4: summary shape 19, products shape 26
- buyer 5: summary shape 20, products shape 25
- buyer 6: summary shape 22, products shape 24

If a new template differs, pass `--layout-config` with the same fields as the default mapping.

## Console preset

The local control console has a dedicated Buyer Briefing Form. Do not force users into raw JSON for this preset. The form stores `records.json` as an object with `globals` and `pages`; each page contains `title` and up to 6 `buyers`. The export path should call `scripts/fill_buyer_briefing_pages.py` directly, not the generic filler.

## Export contract

- A page with more than 6 buyers is rejected before the PPTX is saved.
- A page with fewer than 6 buyers is valid. Every unused summary and product slot in the mapping is cleared, including slots beyond a configured `buyers_per_slide` capacity, by setting the existing runs to empty text, so stale template content cannot remain.
- Export reports use `missing_buyers` entries with `page` and `slot`, and `overlong_text` entries with `page`, `slot`, `field`, `length`, and estimated `capacity`.
- Text capacity warnings do not rebuild the text frame or replace its run styles. They are reported for review while the export retains the existing CLI behavior.
