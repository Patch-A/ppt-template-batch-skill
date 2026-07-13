# Buyer Board Rules

## Core workflow

Use this production order:

1. Input the buyer-board PPT template.
2. Decompose the template into stable layout rules and save them as `layout-config.json`.
3. If needed, research buyers from `country + procurement need`.
4. Fill buyer text content.
5. Apply logos and right-side official visuals when assets are available.
6. Export PPT and preview images.

## Non-negotiable template rules

- Keep the cover unless the user explicitly asks to redesign it.
- Keep the footer `AI慧展说明`.
- Do not add fields the user did not request.
- Treat buyer `logo` and right-side website image as separate source chains.

## Typography and color

- Content title: white.
- Body text: blue near `#2A49F4`.
- Preferred Chinese font: `Microsoft YaHei`.
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

- top title bar
- left-side buyer table
- buyer logo above the table
- right-side website or project visual
- footer `AI慧展说明`

## Config split

- `layout-config.json` stores template structure, text shape indexes, table row mapping, and image-slot rules.
- `buyers.json` stores buyer text fields plus `logo_path` and `site_image_path`.
- In auto mode, buyer images may be temporarily blank while text content is still generated.

## Auto-research rules

When the user only provides:

- `country`
- `procurement need`

The workflow should generate `buyers.json` first.

Research rules:

1. Prefer real companies with official sites.
2. Prefer actual buyers: end users, distributors/importers/resellers, project developers, integrators, maintenance contractors, or large procurement entities. Include manufacturers only when they have a clear internal-use, component, spare-part, consumable, or resale procurement scenario.
3. Generate a 120-Chinese-character bio for each buyer.
4. Normalize the website to domain only.
5. Leave image paths empty when no verified asset is available.
6. Write one to three equipment-level procurement products. Do not use umbrella categories such as `商用厨房设备`、`食品加工设备` or `中央厨房系统` when the actual requirement can be expressed as `切菜机`、`切肉机`、`绞肉机`、`和面机` or another concrete machine.

## Dynamic table rows

- Keep company, country, and website rows at the template height.
- Calculate the `采购产品` and `简介` row heights from actual text length, value-column width, font size, and cell margins.
- Shrink short product rows instead of leaving a large blank block; expand only up to the approved content region and never overlap the footer.
- Set `content.dynamic_row_height` to `false` only when the approved template intentionally requires fixed row heights.

## Image sourcing rules

### Logo

Preferred order:

1. official logo file
2. precise crop from official header or brand area
3. user-approved manual crop

Verification rule:

- the candidate file name or alt text should match the target enterprise brand
- reject certification marks, page badges, unrelated business-unit logos, and subsidiary/sub-brand logos when the profile is for the parent company
- invalidate old cached assets whenever Logo verification logic changes

Placement rule:

- align the logo to the left edge of the approved logo box so it lines up with the text table below
- prefer preserving legibility over maximizing size

Forbidden:

- cropping logo from the right-side image
- random page screenshots
- reusing one crop for both logo and website image

### Right-side image

Preferred order:

1. official product image or official image with clear product elements
2. official project, solution, or brand image
3. official website screenshot
4. AI-generated industry-matched visual only when official sources are unavailable or unusable

Fit rule:

- crop to the target frame aspect ratio before placement
- fill the right-side box without overflowing into the table or footer area
- reject candidates that become unreadable or visually broken after cropping

If no asset is available:

- remove the placeholder image
- do not leave the old template graphic on the slide

## Validation checklist

- does the title match the approved style
- is the table text blue and readable
- is the logo authentic and legible when present
- does the logo match the exact profiled enterprise rather than a subsidiary or business-unit brand
- is the logo left-aligned with the table block
- do the procurement products name concrete purchasable machines rather than broad categories
- do product and bio rows fit their actual line count without excessive blank space
- is the right-side image visually filled and balanced when present
- were placeholder graphics removed when no image asset was available
- was the text-only draft used as input, rather than a previously exported final deck
## Model API boundaries

- Buyer research and verification require the research model API key only when the buyer-research capability is enabled.
- Official website and image scraping do not require a model API key.
- AI visual fallback requires the visual model API key only when AI-generated fallback images are enabled.
- Template detection, layout-config generation, text filling, image placement, and PPTX export run locally by default.
- Use one unified key when simplicity matters, or split research and visual keys when cost, permissions, or providers differ.
- Keep template-analysis credentials optional until a template actually requires model-assisted decomposition.
