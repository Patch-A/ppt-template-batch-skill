# Human-Writing Copy Layer

`human-writing` can be used as an optional writing assistant after research and verification. It is not part of the research engine, and it must never decide which buyers are accepted or rewrite evidence.

Source skill: <https://github.com/KKKKhazix/human-writing> (MIT license). Install it separately in Codex when desired. The PPT repository does not vendor the third-party skill or require it at runtime.

## Safe workflow

1. Finish buyer research, exact-entity matching, country checks, product qualification, evidence collection, and accepted-set selection. Save this as the immutable baseline JSON.
2. Invoke `$human-writing` only for approved natural-language fields. For buyer-board data, normally allow only `bio`. For buyer briefing, normally allow only `summary` or `intro`. For generic records, explicitly name the prose fields for that schema.
3. Give the writer the verified field value plus read-only context. Require it to preserve all names, numbers, dates, URLs, product claims, source attribution, uncertainty, and template length limits. It may improve rhythm, remove repetition, and replace stiff model phrasing; it may not add facts or turn a caveat into a claim.
4. Save the rewritten JSON separately. Do not overwrite the verified baseline.
5. Validate before and after JSON files before PPT generation:

```powershell
python scripts/validate_copy_rewrite.py `
  --before output/workspace/buyers.verified.json `
  --after output/workspace/buyers.polished.json `
  --editable-fields bio `
  --report output/workspace/copy-rewrite-report.json
```

The validator rejects changed structure, record order, protected fields, names removed from copy, changed numeric or URL tokens, excessive expansion, and internal workflow terms in customer copy. A passing report is necessary but not sufficient: factual claims in rewritten prose still require an evidence review.

## Batch guidance

- Rewrite one record at a time or in small chunks. Preserve a stable record identifier outside the editable text.
- Use a field allowlist, not a list of fields to protect. Unknown fields are protected automatically.
- Keep `name`, `country`, `website`, `products`, `buyer_type`, `demand_scenarios`, `evidence`, `source_urls`, scores, confidence, risks, and acceptance status immutable.
- Keep output length close to the source and within the mapped PPT text capacity. Short buyer profiles need concise factual prose, not long-form forum style.
- Run the normal accepted-set, forbidden-term, overflow, and final PPT reopen checks after copy validation.

Do not use this layer for raw research output, evidence summaries used for qualification, legal or compliance language that must remain exact, product lists, URLs, citations, IDs, numeric tables, or machine-readable fields.
