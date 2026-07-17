# Cross-Preset Safety And Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared PPT pipeline and every bundled preset safer, more deterministic, and regression-tested without changing their public CLI contracts.

**Architecture:** Build a standard-library `unittest` harness first. Fix shared asset and data boundaries before preset-specific behavior. Keep generic mapping mode-neutral; keep buyer research rules in buyer modules; keep Yitu and Feishu/Aily contracts separate. Add stable report fields without breaking old inputs or caches.

**Tech Stack:** Python 3.10+, `unittest`, `python-pptx`, existing PowerShell helpers, ZIP contract checks.

---

### Task 1: Cross-Preset Test Harness

**Files:** Create `tests/__init__.py`, `tests/test_buyer_quality.py`, `tests/test_asset_fetching.py`, `tests/test_preset_contracts.py`.

- [ ] **Step 1: Write RED tests for known regressions.** Import modules by adding `ppt-template-batch/scripts` to `sys.path`. Assert that `AssetCandidate(src="https://acme.com/assets/acme-logo-rgb.svg", page="https://acme.com/wholesale-products", alt="Acme logo", cls="brand-mark", origin="official")` is not rejected; `refine_buyer_products("电机、减速机", "电机、减速机", "输送线仅确认使用电机")` returns `电机`; and `pad_or_trim_bio("企业位于当地，提供工业产品和技术服务。")` contains neither `采购计划稳定` nor `具备持续采购能力`. Seed a logo-only cache, count calls to `discover_assets_for_domain()`, and assert the missing site asset triggers discovery.
- [ ] **Step 2: Run the focused tests and verify the expected failures.**

```powershell
$py = "C:\Users\Patch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $py -m unittest tests.test_buyer_quality tests.test_asset_fetching -v
```

Expected: failures in Logo classification, product narrowing, neutral bio padding, and partial-cache retry.

- [ ] **Step 3: Add contract RED tests.** Assert that generic reports contain `ok`, `missing_required_fields`, `missing_assets`, and `warnings`; Buyer Briefing rejects more than six buyers per page and clears unused slots; Yitu dry-run reports missing mapped shapes without saving; and the Feishu ZIP contains only `SKILL.md` plus `references/` files.
- [ ] **Step 4: Run `& $py -m unittest tests.test_preset_contracts -v` and confirm the new behavior fails for implementation reasons, not import errors.**
- [ ] **Step 5: Commit the harness.** `git add tests; git commit -m "test: add cross-preset regression harness"`.

### Task 2: Asset Security, Logo Matching, And Cache Semantics

**Files:** Modify `ppt-template-batch/scripts/fetch_buyer_assets.py`, `scripts/run_buyer_board_pipeline.py`; test `tests/test_asset_fetching.py`.

- [ ] **Step 1: Add RED boundary tests.** Unsupported schemes, loopback/private IP literals, oversized Data URIs, oversized response bodies, and unsafe final redirects must return stable rejection reasons. A cache containing one valid asset must retry only the missing asset and preserve the valid path. Skipped buyers must use the same report keys as normal buyers.
- [ ] **Step 2: Add minimal helpers in `fetch_buyer_assets.py`.** Implement `validate_asset_url(url, base_host="") -> tuple[bool, str]`, `read_response_limited(response, max_bytes) -> bytes`, and `decode_data_uri_limited(src, max_bytes) -> tuple[bytes, str]`. Allow only HTTP(S), reject loopback/link-local/private addresses, validate redirected final URLs, and cap Python, curl, and inline SVG reads before retaining data.
- [ ] **Step 3: Fix Logo ranking.** Build brand tokens from candidate filename/alt/class only. Add neutral tokens for `rgb`, `color`, `mark`, `symbol`, `new`, and year suffixes. Use token matching for broad rejection hints and never scan `candidate.page` for rejection hints.
- [ ] **Step 4: Split cache validity.** Replace the all-or-nothing cache short circuit with independent Logo/site validity checks. Return immediately only when both requested slots are valid; otherwise fetch the missing slot and keep successful paths. Keep failure notes retryable.
- [ ] **Step 5: Run `& $py -m unittest tests.test_asset_fetching -v` and verify GREEN.**
- [ ] **Step 6: Commit with `git add ppt-template-batch/scripts/fetch_buyer_assets.py scripts/run_buyer_board_pipeline.py tests/test_asset_fetching.py; git commit -m "fix: bound asset fetching and retry partial cache"`.

### Task 3: Buyer Data Truthfulness

**Files:** Modify `ppt-template-batch/scripts/discover_buyer_profiles.py` and `ppt-template-batch/scripts/control_console.py`; test `tests/test_buyer_quality.py`.

- [ ] **Step 1: Run the bio and product tests individually and verify each fails on the current behavior.**
- [ ] **Step 2: Replace procurement-claim fillers.** In `pad_or_trim_bio()`, use only neutral facts about location, business scope, products, or services. Put uncertainty in `research_notes` or warnings, not in factual-looking bio text.
- [ ] **Step 3: Narrow copied products for every request size.** When returned products equal the global request, rank requested items by occurrences in buyer evidence and keep at most three. If evidence identifies none, return `需核实具体设备` instead of copying the full request.
- [ ] **Step 4: Keep CLI and console normalization on the same `refine_buyer_products()` path and preserve buyer-specific warnings.**
- [ ] **Step 5: Run `& $py -m unittest tests.test_buyer_quality -v`, then commit with `git add ppt-template-batch/scripts/discover_buyer_profiles.py ppt-template-batch/scripts/control_console.py tests/test_buyer_quality.py; git commit -m "fix: keep buyer copy factual and buyer-specific"`.

### Task 4: Generic Mapping And Preflight

**Files:** Modify `ppt-template-batch/references/layout-config-schema.md`, `ppt-template-batch/scripts/generate_layout_config.py`, `ppt-template-batch/scripts/fill_ppt_from_records.py`, `scripts/run_ppt_batch_pipeline.py`; test `tests/test_preset_contracts.py`.

- [ ] **Step 1: Add RED tests.** A generic mapping must resolve `selector: {"name": "...", "role": "..."}` before numeric `shape_index`; strict mode must reject missing required fields; reports must identify stale template text; non-strict batches must isolate failed records.
- [ ] **Step 2: Add `schema_version: 2` and optional stable selectors.** Readers must normalize version 1 in memory and retain numeric index fallback.
- [ ] **Step 3: Implement shared preflight.** Report missing fields, unresolved placeholders, missing image assets, capacity warnings, slide count, and reopen/corruption status without applying buyer-specific rules.
- [ ] **Step 4: Make generic outputs atomic.** Write each output to a temporary sibling path, reopen with `Presentation`, then replace the requested output. Keep failed record details in the batch report when strict mode is off.
- [ ] **Step 5: Run `& $py -m unittest tests.test_preset_contracts -v`, then commit the four implementation files and test with `git commit -m "feat: strengthen generic PPT mapping and preflight"`.

### Task 5: Buyer Briefing And Yitu Presets

**Files:** Modify `ppt-template-batch/scripts/fill_buyer_briefing_pages.py`, `ppt-template-batch/references/buyer-briefing-rules.md`, `yitu-quanjie/scripts/yitu_quanjie_replace.py`, `yitu-quanjie/SKILL.md`; test `tests/test_preset_contracts.py`.

- [ ] **Step 1: Add RED tests.** Buyer Briefing must report/reject pages with more than six buyers and clear unused slots. Yitu dry-run must report missing shapes, over-capacity text, and table-cell errors without creating output.
- [ ] **Step 2: Normalize Buyer Briefing pages to six slots.** Clear empty summary/product cells, preserve run styles, and report missing buyers and overlong text per page.
- [ ] **Step 3: Split Yitu validation from replacement.** Add `validate_replacement()` and `run_replacement()`. Validate mapped shape names, table coordinates, text capacity, and output path. Add `--dry-run` that prints JSON and never saves.
- [ ] **Step 4: Replace zero-height table behavior.** Use explicit minimum row heights and content-based sizing; report overflow instead of relying on `Emu(0)` auto-fit behavior.
- [ ] **Step 5: Run `& $py -m unittest tests.test_preset_contracts -v`, then commit with `git add ppt-template-batch/scripts/fill_buyer_briefing_pages.py ppt-template-batch/references/buyer-briefing-rules.md yitu-quanjie/scripts/yitu_quanjie_replace.py yitu-quanjie/SKILL.md tests/test_preset_contracts.py; git commit -m "fix: validate briefing and Yitu preset outputs"`.

### Task 6: Feishu/Aily Package And Console Boundaries

**Files:** Modify `feishu-agent-skill/SKILL.md`, `feishu-agent-skill/references/agent-runtime.md`, `feishu-agent-skill/references/input-schema.json`, `scripts/build_feishu_agent_skill.py`, `ppt-template-batch/scripts/control_console.py`, `scripts/run_control_console.py`; test `tests/test_preset_contracts.py`.

- [ ] **Step 1: Add RED tests.** Check required ZIP files, absence of `engine/`, contract version metadata, loopback-only default binding, redacted model settings, and bounded subprocess invocation.
- [ ] **Step 2: Add non-breaking `contract_version`, `sources`, `verification_status`, and `warnings` documentation to the Feishu/Aily input/output contract.** Keep native platform search, image, slide, and export capabilities as the execution path.
- [ ] **Step 3: Validate ZIP contents in the builder.** Fail when required files are missing, forbidden runtime directories are present, or files exist outside `SKILL.md` and `references/`.
- [ ] **Step 4: Harden console boundaries.** Keep `127.0.0.1` default, require explicit opt-in for non-loopback hosts, redact credentials, use atomic JSON writes, and pass bounded timeouts to diagnostic/export subprocesses.
- [ ] **Step 5: Run package/console tests, build `output/ppt-template-batch-agent-skill.zip`, and commit with `git commit -m "feat: harden Feishu package and console boundaries"`.

### Task 7: Documentation And Full Verification

**Files:** Modify `README.md`, `ppt-template-batch/SKILL.md`, `feishu-agent-skill/SKILL.md`, and the approved design document; test all files under `tests/`.

- [ ] **Step 1: Document generic selectors, preflight reports, Buyer Briefing six-slot behavior, Yitu dry-run, asset URL restrictions, and the distinction between desktop and Feishu/Aily execution.**
- [ ] **Step 2: Run the complete suite.**

```powershell
$py = "C:\Users\Patch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $py -m unittest discover -s tests -v
& $py -m compileall -q .
Get-ChildItem -Recurse -File -Filter *.py | ForEach-Object { & $py $_.FullName --help *> $null; if($LASTEXITCODE -ne 0){ throw $_.FullName } }
& $py scripts/build_feishu_agent_skill.py --output output/ppt-template-batch-agent-skill.zip
```

Expected: all tests and CLI help checks pass, compileall exits 0, and the ZIP contains only declared portable files.

- [ ] **Step 3: Inspect final state with `git diff --check`, `git status --short --branch`, and `git diff --stat origin/main...HEAD`; remove merge markers and generated artifacts.**
- [ ] **Step 4: Commit documentation and verification updates with `git add README.md ppt-template-batch/SKILL.md feishu-agent-skill/SKILL.md docs/superpowers/specs tests; git commit -m "docs: document cross-preset quality guarantees"`.

## Self-Review

- Spec coverage: asset security/cache is Task 2; buyer truthfulness is Task 3; generic engine is Task 4; Buyer Briefing and Yitu are Task 5; Feishu/Aily and console are Task 6; tests and documentation are Tasks 1 and 7.
- Every implementation task names concrete files, commands, expected outcomes, and commit boundaries; no placeholder task remains.
- Stable selectors and report fields are optional and backward-compatible; buyer-specific rules remain outside the generic filler.
