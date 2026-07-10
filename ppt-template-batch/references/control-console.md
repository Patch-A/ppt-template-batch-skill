# Local Control Console

Use the control console when a user wants to manage template projects, enter business data through forms, inspect slide elements, and export PPTX files from a browser.

## Start

From the repository root:

~~~powershell
python scripts/run_control_console.py
~~~

From an installed skill directory:

~~~powershell
python scripts/control_console.py
~~~

The default address is http://127.0.0.1:5310/. If that port is busy, the server searches the next 19 ports.

## Project Presets

Create projects through one of these presets:

- Generic PPT: default mode for arbitrary templates and config-driven PPT filling.
- Buyer Board Preset: specialized one-buyer-per-page workflow with research, buyer form, logo and website visual assets, and buyer-board export.
- Buyer Briefing Preset: compact 6-buyers-per-page workflow with a dedicated briefing form: one category per slide and exactly 6 buyers per slide.

## Buyer Data Workflow

For buyer-board projects:

1. Upload the PPTX template.
2. Open Data Entry and keep Buyer Form selected.
3. Either enter buyers manually or provide country, procurement need, and buyer count.
4. Run buyer research and review the generated company name, official website, procurement products, and 120-Chinese-character bio.
5. Optionally fetch verified public logos and official product or website visuals.
6. Save the buyer form. The console stores records.json and attempts to generate the buyer-board layout config.
7. Export PPTX. Buyer-board projects use the buyer text and image pipeline automatically.

Keep Advanced JSON for debugging, custom fields, and generic non-buyer projects.

## Buyer Briefing Workflow

For buyer-briefing projects:

1. Upload the PPTX template.
2. Open Data Entry and use Buyer Briefing Form.
3. Fill one category title per page, such as `????`, without adding the country name unless the template requires it.
4. Fill exactly 6 buyers per page. Each buyer needs company name, compact company intro, and procurement category line.
5. Keep procurement text as `?????XXXX?`.
6. Export PPTX. The console uses `fill_buyer_briefing_pages.py` and preserves the template run-level typography.



## Capability-Based Model Configuration

Model settings are feature-driven. Do not require a key for inactive features.

- Buyer research: enable only when the user wants country plus procurement-need generation. Default research mode is `model_only`, which calls OpenAI-compatible chat completions.
- AI visual generation: enable only when the user explicitly wants AI-generated fallback visuals. Official website asset fetching does not require this model.
- Intelligent template analysis: keep disabled unless model-assisted arbitrary-template understanding is added for the current task.

Use OpenAI built-in search only when explicitly selected. For domestic or compatible providers, use `model_only` or future external-search-plus-model modes.

## Model API Roles

Configure model keys from Model Settings. Keys remain in process memory and are not written to project.json, records.json, logs, or the repository.

Recommended role split:

- Buyer research and verification: required for country plus procurement-need research. OpenAI can use the built-in web_search path when explicitly selected; domestic and compatible providers use chat-completions JSON generation and should be manually verified or paired with external search when live verification is required.
- AI visual generation: required only when AI fallback images are enabled. Official website scraping and public asset downloading do not need a model key.
- Intelligent template analysis: optional and reserved. Current layout detection, text filling, image placement, and PPTX export run locally without a model key.

Model Settings supports OpenAI, DeepSeek, Qwen, Zhipu GLM, Kimi, Doubao, MiniMax, SiliconFlow, OpenRouter, local Ollama/LM Studio, and custom OpenAI-compatible providers. Each role has provider, Base URL, API Key, and model fields. Fetch models calls the provider `/models` endpoint; if that endpoint fails, use the built-in fallback candidates and keep manual model input available. DeepSeek and compatible buyer research use direct HTTP calls and do not require the Python `openai` package.

Unified mode shares provider and API Key across roles while keeping each role's model name separate. Split mode accepts separate research, visual, and optional layout-analysis keys.

## Project Structure

Each project is isolated in its own directory:

- project.json: project mode, metadata, recent runs, and non-secret settings
- template.pptx: uploaded source template
- records.json: structured records and global values
- layout-config.json: text, table, image, placeholder, and repeated-slide mappings
- assets/: downloaded or supplied images
- output/: generated PPTX files
- workspace/: reports, caches, and temporary files

## Safety And Scope

- Bind to 127.0.0.1 by default.
- Validate uploaded templates as real PPTX ZIP packages.
- Keep all paths inside the configured projects root.
- Never persist API keys in project files.
- Treat the structure panel as a mapping aid, not a pixel-perfect slide preview.
- Keep client projects outside the public repository.
## Generic Layout Mapping Guide

The Layout Mapping tab now includes beginner guidance and example buttons. Use Template Structure to find each shape index, then map fields to `shape_index`. Start with the generic, buyer-board, or buyer-briefing example and only change indexes and field names that differ in the uploaded template.
