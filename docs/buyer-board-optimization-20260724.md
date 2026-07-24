# Buyer Board Optimization Notes

This public reference records the generic safeguards added to the buyer-board workflow. It intentionally omits customer names, private paths, internal IDs, personal names, and task-specific buyer lists.

## Auditable selection loop

For a target of `N` buyers:

1. Discover a broader public candidate pool.
2. Verify the official site and an independent public source.
3. Cross-check the candidate against any user-supplied internal buyer records.
4. Apply the requested country as a hard filter.
5. Match the exact enterprise using domain, distinctive name or brand tokens, company context, location, and business evidence. Generic country, industry, or product words cannot prove identity by themselves.
6. Confirm a concrete use, procurement, import, distribution, project, maintenance, or resale scenario.
7. Generate the deck only from the final `accepted` set.
8. Recalculate the gap and search only for the missing number of new candidates until the target is met or the gap is explicitly blocked.

If the internal buyer source is unavailable, the workflow must not claim internal verification or invent identifiers; use `partial` or `pending` status.

## Separation of internal and customer data

The internal verification table records discovery round, public sources, internal source and identifier when available, matching basis, evidence, acceptance status, and exclusion reason. It must remain separate from the customer PPT.

Customer-facing content must not expose internal workflow terms such as `buyer_id`, `accepted`, `internal library`, `public candidate`, `verification`, `matched`, `pending verification`, `weak match`, `excluded`, or scraping-failure notes. The PPT list must exactly equal the accepted set.

## Asset and final-output gates

When the template requires assets, every delivered page needs a verified enterprise Logo and a separate product, facility, project, or application visual. Do not use header crops, favicons, generic icons, partner marks, product images, or AI images as Logos. If a selected candidate lacks reliable assets, replace it with another accepted candidate or block the delivery rather than mislabeling a missing asset.

Before delivery, reopen the final PPTX and compare the displayed names, countries, bio lengths, products, image count, table geometry, row heights, fixed elements, and internal-term scan against the verification data. The verification table itself must never be embedded in the customer deck.
