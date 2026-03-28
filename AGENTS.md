# AGENTS.md

## Purpose

This repository fetches configured Substack RSS feeds, summarizes new posts with an LLM, stores summaries in `data/articles.json`, and renders a static `index.html` from `template.html`.

The core workflow is:

1. Read configured feeds from `feeds.json`.
2. Fetch RSS entries with `feedparser`.
3. Summarize only unseen posts via Ollama by default, or Google Gemini when `GOOGLE_API_KEY` is set and `google-generativeai` is installed.
4. Persist summaries to `data/articles.json`.
5. Optionally fetch full article pages for subscriber-only Substack posts using an authenticated browser-exported cookie file.
6. Render the static site into `index.html`.
7. Optionally publish the generated site to `gh-pages` via `publish.sh`.

## Repo Map

- `worker.py`: Main application logic. Owns feed loading, prompt generation, article summarization, JSON persistence, static-site rendering, and optional authenticated article fetching.
- `template.html`: Jinja2 template for the generated site. Includes the client-side tab UI, Markdown rendering via `marked`, and local search behavior.
- `feeds.json`: Source of truth for subscribed RSS feeds and per-feed summarization prompts. Empty prompts are backfilled by `worker.py`.
- `data/articles.json`: Generated article cache. This is runtime data, not hand-edited source.
- `publish.sh`: End-to-end deploy script. Restores cached article history, runs `worker.py`, commits prompt updates in `feeds.json`, then force-pushes generated output to `gh-pages`.
- `requirements.txt`: Python dependencies currently used by the runtime.
- `README.md`: User-facing setup and workflow description.

## Environment

- Python version: README says Python 3.8+, but the local repo currently includes a `.venv` based on Python 3.12.
- Primary runtime dependencies:
  - `beautifulsoup4`
  - `feedparser`
  - `Jinja2`
  - `ollama`
  - `requests`
- Optional dependency:
  - `google-generativeai`
- External services:
  - Ollama must be installed and running for the default path.
  - Gemini is used only when `GOOGLE_API_KEY` is present and the optional package imports successfully.

### Optional authenticated Substack access

The worker may optionally use a browser-exported cookie file to fetch full text from subscriber-only Substack posts that are not fully present in RSS.

Supported configuration:

- `SUBSTACK_COOKIES_FILE`: path to a Netscape-format cookie file exported from a Chromium/Chrome-based browser.

This repo should use cookie-based session reuse only. Do not implement interactive login, email/password login, or MFA handling in the worker.

### Optional authenticated Substack access

The worker may optionally use a browser-exported cookie file to fetch full text from subscriber-only Substack posts that are not fully present in RSS.

Supported configuration:

- `SUBSTACK_COOKIES_FILE`: path to a Netscape-format cookie file exported from a Chromium/Chrome-based browser.

This repo should use cookie-based session reuse only. Do not implement interactive login, email/password login, or MFA handling in the worker.

## Common Commands

Set up the environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install requests
pip install google-generativeai  # optional
```

Run the worker locally:

```bash
python worker.py
```

Run the full publish flow:

```bash
bash publish.sh
```

Run with authenticated Substack access:

```bash
export SUBSTACK_COOKIES_FILE="$HOME/.config/substack/cookies.txt"
python worker.py
```

## Code Behavior Notes

- `worker.py` creates `data/` automatically if it does not exist.
- If `feeds.json` is empty, `worker.py` seeds it with two default Substack feeds.
- Prompt generation is stateful: when a feed has an empty `prompt`, `_get_system_prompt()` generates one and writes it back into `feeds.json`.
- New articles are detected by `link`; existing entries are skipped.
- Article text is extracted from RSS `content` or `summary`, HTML-stripped with BeautifulSoup, and truncated to `60000` characters before summarization.
- If RSS content appears truncated, teaser-only, or subscriber-gated, `worker.py` may fetch the article URL directly using an authenticated session built from `SUBSTACK_COOKIES_FILE`.
- Cookie-authenticated page fetch is an enhancement, not the primary discovery mechanism. RSS remains the source of truth for detecting new posts.
- Output articles are sorted descending by `published_date`.
- `template.html` expects `articles_by_feed` and `last_updated` from `render_static_site()`.

## Editing Guidance

- Treat `worker.py` as the main source file. Keep changes localized and avoid introducing framework or packaging overhead unless explicitly requested.
- Do not hand-edit `data/articles.json` or `index.html` unless the task is specifically about generated output or fixture repair. Prefer regenerating them through `worker.py`.
- Be careful editing `feeds.json`. It is both configuration and a runtime write target.
- Do not store browser cookies, raw `Cookie` headers, usernames, passwords, or other secrets in `feeds.json`.
- Keep cookie handling environment-based only.
- Keep `template.html` compatible with the existing plain Jinja render path in `worker.py`.
- If you add Gemini support work, remember that `google-generativeai` is optional and imports must remain guarded.
- If you add authenticated fetch support, prefer `requests.Session()` with a cookie jar loaded from `SUBSTACK_COOKIES_FILE`.
- Avoid adding browser automation, Playwright, Selenium, or scraping frameworks unless explicitly requested.
- If you change deployment behavior, inspect `publish.sh` closely: it assumes the main branch is `master`, uses an orphan branch named `temp-gh-pages`, and force-pushes to `origin gh-pages`.

## Verification

There is no automated test suite in this repository today.

Minimum verification for most changes:

1. Run `python worker.py`.
2. Confirm `index.html` is regenerated without exceptions.
3. Inspect any intended changes in `feeds.json` and `data/articles.json`.
4. When `SUBSTACK_COOKIES_FILE` is set, verify that at least one known subscriber-only post can be fetched without crashing the worker.
5. When `SUBSTACK_COOKIES_FILE` is unset or invalid, verify that the worker falls back cleanly to RSS-derived content.
6. Confirm that no secrets or absolute local cookie paths are written into generated output.
4. When `SUBSTACK_COOKIES_FILE` is set, verify that at least one known subscriber-only post can be fetched without crashing the worker.
5. When `SUBSTACK_COOKIES_FILE` is unset or invalid, verify that the worker falls back cleanly to RSS-derived content.
6. Confirm that no secrets or absolute local cookie paths are written into generated output.

For deploy-script changes:

1. Read `publish.sh` end to end before editing.
2. Validate branch assumptions against the current repo state.
3. Avoid running the publish flow unless the task requires it, because it commits locally and force-pushes `gh-pages`.

## Known Repo-Specific Risks

- `requirements.txt` includes `Flask`, but the current runtime does not use Flask.
- The local editor context referenced `.github/copilot-instructions.md`, but that file is not present in the repository at the time of writing.
- `publish.sh` is intentionally destructive to the deploy branch history and should be treated carefully.
- Generated summaries depend on external model behavior, so output is nondeterministic.
- Substack page structure and auth behavior can change, so authenticated article extraction should be written defensively and degrade gracefully.
- Browser-exported cookie files expire and may stop working without code changes.
- Substack page structure and auth behavior can change, so authenticated article extraction should be written defensively and degrade gracefully.
- Browser-exported cookie files expire and may stop working without code changes.

## Guidance For Future Agents

- Start by reading `worker.py`, `publish.sh`, and `template.html`.
- Check `git status` before making changes because `feeds.json` and generated artifacts may already be dirty.
- Prefer small, direct edits over architectural refactors.
- Preserve the current flat-file workflow unless the user explicitly asks for a larger redesign.
- Keep RSS-based discovery intact even if authenticated page fetch is added.
- Treat cookie files as local operator secrets. Never commit them, print them, or serialize them into application data.
- Keep RSS-based discovery intact even if authenticated page fetch is added.
- Treat cookie files as local operator secrets. Never commit them, print them, or serialize them into application data.
