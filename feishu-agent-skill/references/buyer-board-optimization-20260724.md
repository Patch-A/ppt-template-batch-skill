# Buyer Board Optimization Notes

## Scope

This reference defines the auditable buyer-selection and delivery safeguards for the `buyer_board` preset. It is intentionally redacted: it contains no customer names, private file paths, internal IDs, personal names, or task-specific buyer lists.

## 1. Auditable Candidate Loop

When the user requests `N` buyers for a country and procurement need, use this order:

1. Discover a broader public candidate pool than the final target.
2. Verify each candidate using the official site plus at least one independent public source.
3. When an internal buyer library or historical record is supplied, cross-check the candidate against it before acceptance.
4. Apply the target-country hard filter. A candidate must be headquartered in, operating materially in, or demonstrably purchasing for the target country.
5. Match the exact enterprise主体 using domain, brand or distinctive name tokens, company description, country/city, and business context. Country words, generic industry words, and product words are supporting evidence only; they cannot prove identity on their own.
6. Confirm a concrete use, procurement, import, distribution, project, maintenance, or resale scenario for the requested product.
7. Put only candidates that pass all required checks into the internal `accepted` set.
8. Calculate the gap `K = N - len(accepted)`. Search only for `K` new candidates, repeat the checks, and stop when the target is met or the remaining gap is blocked with an explicit reason.

If an internal library is unavailable, do not claim library verification or invent `buyer_id` values. Mark the result `partial` or `pending` and list the missing verification source.

## 2. Internal Verification Table

Keep the verification table separate from the customer-facing PPT. For each candidate, record as applicable:

- display name, country, and city
- discovery round and public discovery sources
- official-site and independent evidence summaries
- internal record identifier and source, when supplied by the user
- matching basis: domain, distinctive brand/name tokens, company profile, product fields, or country/city
- concrete procurement or application evidence
- status: `accepted`, `duplicate`, `weak_match`, `country_mismatch`, `not_in_internal_source`, or `blocked`
- acceptance grade and exclusion reason

The customer PPT must be generated from the final `accepted` set only. Excluded, duplicate, weak-match, or pending records must never enter the deck.

## 3. Customer Copy Boundary

Customer-facing text must contain only readable company facts, business context, and evidence-supported procurement needs. Do not expose internal process terms such as:

`buyer_id`, `accepted`, `internal library`, `public candidate`, `verification`, `matched`, `pending verification`, `weak match`, `excluded`, `scraping failed`, or similar workflow language.

Store those details in the separate verification report and source metadata instead of the PPT body.

## 4. Asset Completeness Gate

When the selected template requires a Logo and a right-side visual, treat both as per-page delivery requirements:

- Logo must be the verified enterprise mark, not a header crop, favicon, generic icon, product image, partner mark, or AI-generated substitute.
- The right-side image should be an official product, facility, project, or application visual; use a website screenshot only as a later fallback.
- If a real asset is unavailable, first replace the candidate with another `accepted` candidate whose assets can be verified.
- If the target cannot be completed without inventing or mislabeling an asset, stop with a clear blocked status rather than presenting a falsely complete deck.

## 5. Final PPT Recheck

Read the exported PPTX again before delivery and compare it with the internal verification data. Check:

- the displayed enterprise list equals `accepted` exactly and in the intended order
- every country matches the requested target or has an explicitly documented exception
- bio length, procurement products, and concrete buyer-specific evidence are present
- no internal process terms or stale template text remain
- every required Logo and right-side visual is real, correctly matched, and within its frame
- slide count, table geometry, row heights, margins, alignment, and fixed elements match the approved template
- the file reopens successfully

The verification table may remain internal. Never embed it in the customer deliverable.
