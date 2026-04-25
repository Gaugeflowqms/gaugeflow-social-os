<<<<<<< HEAD
# GAUA-17 GaugeFlow Social OS

Local software project for running a weekly Social OS cycle at GaugeFlow: validate initiative graph integrity, score team health signals, generate capacity-aware ritual planning, and export execution artifacts.

## Implemented Scope
- Domain model for members, initiatives, signal events, ritual slots, and weekly plan allocations.
- Validation for ownership, dependency existence, and cycle detection.
- Team health scoring engine from structured social signals.
- Priority and planning engine that allocates initiatives into ritual slots while enforcing slot and owner capacity.
- Exporters for CSV (initiative backlog), Markdown (operating summary), and JSON (weekly plan payload).
- CLI workflow for validate, health scoring, planning, critical-chain analysis, and artifact export.
- Unit tests for validation, planning constraints, scoring bounds, and exports.

## Project Layout
- `pyproject.toml`: package metadata and CLI entrypoint.
- `src/gaugeflow_social_os/models.py`: dataclass domain models.
- `src/gaugeflow_social_os/data.py`: seed GAUA-17 dataset.
- `src/gaugeflow_social_os/engine.py`: validation, scoring, prioritization, planning, critical chain.
- `src/gaugeflow_social_os/exporters.py`: CSV/Markdown/JSON exports.
- `src/gaugeflow_social_os/cli.py`: command-line interface.
- `tests/test_social_os_engine.py`: engine/unit behavior tests.
- `tests/test_social_os_exporters.py`: export tests.

## Quick Start
```bash
PYTHONPATH=src python3 -m gaugeflow_social_os.cli validate
PYTHONPATH=src python3 -m gaugeflow_social_os.cli health
PYTHONPATH=src python3 -m gaugeflow_social_os.cli plan
PYTHONPATH=src python3 -m gaugeflow_social_os.cli critical-chain
PYTHONPATH=src python3 -m gaugeflow_social_os.cli export --outdir outputs
```

## Run Tests
```bash
python3 -m unittest discover -s tests -v
```

## Note
Legacy GAUA-10 `qms_plan` package remains in the workspace and its tests still run under the same test command.
=======
# GaugeFlow Social OS

Automated, low-volume, safety-first social media operating system for
[GaugeFlow QMS](https://gaugeflowqms.com). Posts on LinkedIn, Facebook Page,
and Instagram Business in the voice of Sam Callahan, replies to safe comments
on owned posts, and (with strict limits) drops helpful comments on relevant
manufacturing/quality posts.

This is built for long-term business use. It is *not* a spam bot.

- Uses **official APIs** first (Facebook Graph, Instagram Graph, LinkedIn REST).
- Uses **Playwright with a saved Chrome profile** only as a fallback, never to
  bypass captcha, 2FA, or platform challenges.
- Every outbound message goes through a **safety checker** before posting.
- **Three modes**: `DRY_RUN` (default), `SEMI_AUTO`, `FULL_AUTO`.
- Full **action log + screenshots** so you can always answer "what did the bot
  do today and why".

---

## What it does each day

1. Loads brand memory (Sam Callahan voice, banned topics, content topics).
2. Generates one LinkedIn post, one Facebook Page post, one Instagram caption.
3. Scores each draft (0-100). Blocks risky drafts. Drafts medium-risk content
   for human review. Auto-posts low-risk content (mode-dependent).
4. Pulls comments on owned posts and replies to simple, safe ones.
5. Reads a configured list of relevant external posts and (in FULL_AUTO mode
   only) drops short, helpful comments on the lowest-risk ones, within strict
   daily limits.
6. Logs every action, screenshots every browser action, and sends a Telegram
   summary.

---

## Requirements

- Python 3.11+
- A Telegram bot + chat ID (recommended, optional)
- At least one AI provider key (OpenAI **or** Anthropic Claude)
- Page/Business tokens for the platforms you want to use:
  - Facebook Page access token (`pages_manage_posts`, `pages_read_engagement`)
  - Instagram Graph access token + connected Business account
  - LinkedIn organization access token (`w_organization_social`)
- (Optional) Chrome profile directory for browser fallback

---

## Install

```bash
git clone <your repo> gaugeflow-social-os
cd gaugeflow-social-os
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# Browser fallback only — install Chromium for Playwright
playwright install chromium
```

---

## Configure

Copy `.env.example` to `.env` and fill in what applies:

```bash
cp .env.example .env
```

Minimum to run a useful dry-run:

- `AI_PROVIDER=openai` (or `claude`)
- `OPENAI_API_KEY=...` (or `ANTHROPIC_API_KEY=...`)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional, but recommended)

Add API tokens for the platforms you want to actually publish to.

### Mode

`APP_MODE` is one of:

| Mode | Original posts | Owned-post replies | External comments |
|------|----------------|---------------------|--------------------|
| `DRY_RUN` (default) | drafted | drafted | drafted |
| `SEMI_AUTO` | auto-post if safe | auto-reply if simple+safe | drafted |
| `FULL_AUTO` | auto-post if safe | auto-reply if simple+safe | auto-post if low-risk |

You can also override mode at runtime via Telegram (`/dry_run`, `/semi_auto`,
`/full_auto`) or the dashboard.

---

## Initialize the database

```bash
python main.py init-db
```

Creates `storage/actions.db` with all tables.

---

## Run a dry run

```bash
python main.py dry-run
```

Generates drafts for all configured platforms, scores them, persists everything
to `storage/actions.db`, sends a Telegram summary if configured, and prints the
report to stdout. **Nothing is posted.**

---

## Run the daily workflow once

```bash
python main.py run-once
```

Same as the scheduler firing once. Respects the current mode.

---

## Start the dashboard

```bash
python main.py dashboard
```

Open <http://127.0.0.1:8765> (configurable via `DASHBOARD_HOST` /
`DASHBOARD_PORT`).

You can:
- See today's actions, platform status, and recent posts
- Approve or block individual drafts
- Switch mode
- Pause / resume
- Trigger a workflow run

---

## Start the Telegram bot

```bash
python main.py telegram
```

Available commands (only your `TELEGRAM_CHAT_ID` is authorized):

```
/start_day        run today's full workflow now
/status           show system status
/mode             show current mode
/dry_run          switch to DRY_RUN
/semi_auto        switch to SEMI_AUTO
/full_auto        switch to FULL_AUTO
/pause            pause posting
/resume           resume
/post_now         generate and post one safe post
/draft_comments   draft external comments only (no posting)
/report           send today's report
/limits           show daily limits
/help             show commands
```

---

## Run on a schedule

### systemd (Linux)

Three example unit files in `deploy/`:

- `gaugeflow-social-scheduler.service` — runs the daily workflow at
  `DAILY_RUN_TIME`
- `gaugeflow-social-dashboard.service` — runs the FastAPI dashboard
- `gaugeflow-social-telegram.service` — runs the Telegram bot

```bash
sudo cp deploy/gaugeflow-social-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gaugeflow-social-scheduler.service
sudo systemctl enable --now gaugeflow-social-dashboard.service
sudo systemctl enable --now gaugeflow-social-telegram.service
```

### cron

```cron
30 8 * * * cd /home/sam/gaugeflow-social-os && /home/sam/gaugeflow-social-os/.venv/bin/python main.py run-once >> storage/logs/cron.log 2>&1
```

See `deploy/crontab.example`.

---

## Browser fallback (Playwright)

Browser fallback is **off by default**. Turn it on only if the platform you
care about does not give you full API coverage (LinkedIn comments, e.g.).

```env
BROWSER_ENABLED=true
BROWSER_PROFILE_PATH=/home/sam/.paperclip/browser-profiles/gaugeflow-social
HEADLESS=false
LOGIN_AUTOMATION_ALLOWED=false
```

### One-time manual login

The system never types passwords or solves captchas. Log in **once**, by hand,
into the persistent profile:

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir='/home/sam/.paperclip/browser-profiles/gaugeflow-social',
        headless=False,
    )
    page = ctx.new_page()
    page.goto('https://www.linkedin.com/login')
    print('Log in by hand. Close the window when done.')
    page.wait_for_event('close', timeout=0)
"
```

Repeat for `facebook.com` and `instagram.com`. After that, the saved profile
keeps you signed in across runs.

If a platform later asks for a security check, captcha, or 2FA, the system
**will not try to solve it**. It will:
1. Stop work on that platform.
2. Take a screenshot under `storage/screenshots/`.
3. Mark the platform as `human_required` in the database.
4. Send a Telegram alert.

You then resolve it manually in a real browser using the same profile and the
system resumes normally next run.

---

## Daily limits

Hard-coded ceilings (configurable in `.env`):

- **LinkedIn** — 1 post, 3 external comments, 5 likes, 0 connection requests, 0 cold DMs
- **Instagram** — 1 post, 5 replies, 5 likes, 0 cold DMs
- **Facebook Page** — 1 post, 10 replies, 5 external comments
- **Global** — no duplicate comments, no more than 1 comment per
  target/person/company per day, randomized delays between browser actions,
  hard stop on any blocked / suspicious response

---

## Safety rules (non-negotiable)

The system will **never**:
- Bypass captcha, 2FA, login challenges, or "verify it's you" prompts.
- Mass like / mass follow / mass connect / cold DM.
- Scrape private profiles or private content.
- Post political, religious, medical, legal, or financial-guarantee content.
- Comment on tragedy, layoff, lawsuit, or crisis posts.
- Use buzzwords (`game-changer`, `revolutionary`, `seamless`, `10x`, etc.).
- Use aggressive sales CTAs (`book a demo today`, `DM me now`,
  `limited time`, etc.) without manual approval.

If any of these patterns appear in a draft, the safety checker either drops
the score below the auto-post band (becoming a draft) or hard-blocks the
action.

---

## Stop conditions

When any of these are detected, the system stops the current platform's work,
takes a screenshot, marks the platform as `human_required`, sends a Telegram
alert, and does not retry:

- captcha
- 2FA / two-factor
- password / login prompt
- account restricted / action blocked / try again later
- security check / verify it's you / unusual activity
- API token expired / 401 / 403

---

## Tests

```bash
pip install pytest
pytest -q
```

Tests cover:
- Safety checker (blocks risky content, approves safe content, dedup, browser
  stop-condition detection).
- Database init, action insert/update, daily-limit counting, engagement dedup,
  settings get/set.
- Content writer with a stub AI provider (no API keys needed).

---

## Troubleshooting

**"AI provider missing key"** — Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in
`.env`. The system falls back to a stub provider so dry-runs still work, but
you'll get placeholder content.

**"Telegram not configured"** — Set `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`. Test with `python -c "from connectors.telegram_bot import
send_message; send_message('hi')"`.

**"facebook_not_configured"** — You need a Page access token with
`pages_manage_posts` + `pages_read_engagement`, plus the numeric Page ID.

**"linkedin_api_external_comment_unavailable"** — Most LinkedIn dev tiers
cannot comment on third-party posts via API. Either disable LinkedIn external
comments or enable browser fallback.

**"login_required" / "stop_condition: captcha"** — A platform is asking you to
log in or verify by hand. Open the persistent Chrome profile, complete the
challenge yourself, then re-run.

**"daily_limit_reached"** — The bot already used today's quota for that
action type. Wait until tomorrow or raise the limit in `.env`.

---

## File map

```
gaugeflow-social-os/
├─ agents/
│  ├─ ceo_controller.py     # daily workflow orchestrator
│  ├─ content_writer.py     # original posts
│  ├─ comment_writer.py     # external comments
│  ├─ reply_writer.py       # owned-post replies
│  ├─ media_planner.py      # image/carousel/reel ideas
│  ├─ safety_checker.py     # risk scoring + decision
│  ├─ engagement_finder.py  # candidate posts to comment on
│  ├─ platform_operator.py  # API-first, browser-fallback router
│  └─ report_writer.py      # daily report text
├─ connectors/
│  ├─ ai_provider.py        # provider abstraction
│  ├─ openai_provider.py
│  ├─ claude_provider.py
│  ├─ facebook_page_api.py
│  ├─ instagram_graph_api.py
│  ├─ linkedin_api.py
│  ├─ browser_operator.py   # Playwright fallback
│  └─ telegram_bot.py
├─ memory/
│  ├─ brand_voice.md
│  ├─ sam_callahan_voice.md
│  ├─ company_context.md
│  ├─ banned_topics.md
│  ├─ content_topics.md
│  ├─ engagement_targets.json
│  ├─ recent_posts.json
│  └─ engagement_history.json
├─ storage/
│  ├─ actions.db            # SQLite
│  ├─ screenshots/
│  ├─ logs/
│  └─ exports/
├─ dashboard/               # FastAPI + Jinja UI
├─ deploy/                  # systemd unit files + cron example
├─ tests/
├─ main.py
├─ scheduler.py
├─ db.py
├─ config.py
├─ models.py
├─ requirements.txt
├─ .env.example
└─ README.md
```
>>>>>>> 005aa2b06c34b2aa8020a3d31346e23cdfde4fcb
