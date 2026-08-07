# Cross-Preset Human-Writing Layer

`human-writing` is an optional writing capability for the whole PPT template batch skill. Use it to draft, edit, tighten, or reduce AI-like phrasing in natural-language presentation content. It supports generic decks, product catalogs, company profiles, market reports, proposals, training materials, speaker notes, and the bundled buyer presets. It is not part of the research, asset, or layout engines.

Source skill: <https://github.com/KKKKhazix/human-writing> (MIT license). Install it separately in Codex when desired. This repository does not vendor the third-party skill or require it at runtime.

## Capability boundary

Use the writing layer only for explicitly approved prose fields. Typical generic fields include `title`, `subtitle`, `summary`, `intro`, `description`, `body`, `caption`, and `speaker_notes`. Keep IDs, record order, layout mappings, image paths, structured labels, product specifications, prices, numbers, dates, URLs, citations, source status, scores, confidence, risks, and other machine or factual fields protected.

For factual content, collect and verify the source first. For creative or fictional content, the user may authorize invention, but invented details must stay within that context and must not be mixed into factual records.

## Safe workflow

1. Finish source collection, research, verification, and any domain-specific selection. Save the result as an immutable baseline JSON.
2. Invoke `$human-writing` only for the approved prose-field allowlist. For buyer-board data, normally allow only `bio`; for buyer briefing, normally allow only `summary` or `intro`.
3. Give the writer the source text plus read-only context. Require it to preserve names, numbers, dates, URLs, claims, attribution, uncertainty, and template length limits.
4. Save the rewritten JSON separately. Do not overwrite the verified baseline.
5. Validate the before and after files before PPT generation.

Generic presentation example:

```powershell
python scripts/validate_copy_rewrite.py `
  --before output/workspace/records.verified.json `
  --after output/workspace/records.polished.json `
  --editable-fields title,summary,description,body `
  --profile generic `
  --report output/workspace/copy-rewrite-report.json
```

Buyer preset example:

```powershell
python scripts/validate_copy_rewrite.py `
  --before output/workspace/buyers.verified.json `
  --after output/workspace/buyers.polished.json `
  --editable-fields bio `
  --profile buyer `
  --report output/workspace/copy-rewrite-report.json
```

The validator rejects changed structure, record order, protected fields, changed numeric or URL tokens, and excessive expansion. Buyer profile mode additionally protects identity anchors and customer-facing workflow terms. A passing report is necessary but not sufficient: factual claims in rewritten prose still require evidence review.

## Batch guidance

- Rewrite one record at a time or in small chunks. Preserve a stable record identifier outside the editable text.
- Use a field allowlist. Unknown fields are protected automatically.
- Keep output length close to the source and within the mapped PPT text capacity.
- Treat short cards, tables, captions, and speaker notes as different formats with different length limits.
- Run normal overflow, stale-placeholder, asset, and final PPT reopen checks after copy validation.

Do not use this layer for raw research output, evidence used for qualification, legal or compliance language that must remain exact, product lists, URLs, citations, IDs, numeric tables, layout mappings, or other machine-readable fields.
