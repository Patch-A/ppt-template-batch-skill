# Buyer Board Rules

## Core workflow

Use this production order:

1. Input the buyer-board PPT template.
2. Decompose the template into stable layout rules and save them as `layout-config.json`.
3. Fill buyer text content.
4. Apply logos and right-side official visuals.
5. Export PPT and preview images.

## Non-negotiable template rules

- Keep the cover unless the user explicitly asks to redesign it.
- Keep the footer `AI慧展说明`.
- Do not add fields the user did not request.
- Treat buyer `logo` and right-side website image as separate source chains.

## Typography and color

- Content title: white.
- Body text: blue near `#2A49F4`.
- Preferred Chinese font: `微软雅黑`.
- Default body size: `16 pt`.
- Avoid shrinking text excessively to force fit.

## Content-page structure

Expected left table fields:

- `企业`
- `国家`
- `网站`
- `采购产品`
- `简介`

Expected page elements:

- Top title bar
- Left-side buyer table
- Buyer logo above the table
- Right-side website/project visual
- Footer `AI慧展说明`

## Config split

- `layout-config.json` stores template structure, text shape indexes, table row mapping, and image-slot rules.
- `buyers.json` stores buyer text fields plus `logo_path` and `site_image_path`.
- The South Africa example is the current reference implementation of this split.

## Image sourcing rules

### Logo

Preferred order:

1. Official logo file.
2. Precise crop from official header or brand area.
3. User-approved manual crop.

Forbidden:

- Cropping logo from the right-side image
- Random page screenshots
- Reusing one crop for both logo and website image

### Right-side image

Preferred order:

1. Official hero image
2. Official project or brand image
3. Official website screenshot

Avoid decorative art that does not represent the buyer's actual business.

## Validation checklist

- Does the title match the approved style?
- Is the table text blue and readable?
- Is the logo authentic and legible?
- Is the right-side image visually filled and balanced?
- Are there leftover template graphics after logo replacement?
- Was the text-only draft used as input, rather than a previously exported final deck?
