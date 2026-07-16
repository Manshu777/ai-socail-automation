# AI Social Media Automation

Desktop app for generating human-sounding social posts for LinkedIn, X, Facebook, and Instagram — with scheduling, history, and exports.

## Features

- Modern dark UI (CustomTkinter)
- OpenAI generation with optional NVIDIA NIM fallback
- Offline demo mode when no API keys are set
- Multi-platform previews with character counters
- JSON / Markdown / TXT export
- SQLite history (search, edit, reuse, delete)
- Background scheduler with token-aware publishing stubs
- Settings saved to `.env`
- Quality checks: X limit, hashtag dedupe, readability, uniqueness

## Requirements

- Python **3.12+ with Tkinter** (`_tkinter`)
  - On macOS Homebrew: `brew install python@3.12 python-tk@3.12`
  - Prefer `python3.12` over newer Homebrew builds that ship without Tk
- macOS / Windows / Linux desktop environment

## Quick start

```bash
cd AI-Social-Automation
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Add OPENAI_API_KEY (and optional tokens) in .env or via Settings
python app.py
```

If `import _tkinter` fails, install Tk for your Python version before launching the UI.
## Project layout

| File | Role |
|------|------|
| `app.py` | Entry point |
| `ui.py` | Dashboard & screens |
| `generator.py` | LLM generation / rewrite |
| `prompts.py` | System & user prompts |
| `image_prompt.py` | Image prompt helpers |
| `image_generator.py` | Auto image gen (DALL·E / local poster) |
| `scheduler.py` | Background schedule worker |
| `social_api.py` | Platform publish adapters |
| `database.py` | SQLite models |
| `config.py` | Env + theme config |
| `utils.py` | Export, quality, logging |

Folders: `posts/` (exports), `database/` (SQLite), `logs/`, `assets/`.

## Settings

Open **⚙ Settings** in the app (or edit `.env`):

- `OPENAI_API_KEY` — primary LLM
- `NVIDIA_API_KEY` — optional NIM fallback
- `LINKEDIN_TOKEN` / `FACEBOOK_TOKEN` / `INSTAGRAM_TOKEN` / `X_TOKEN`

Publishing currently queues / simulates live posts when tokens are present. Swap in the official Graph / LinkedIn / X APIs inside `social_api.py` for production posting.

## Usage

1. Go to **Generate Post**
2. Enter a topic, pick industry / tone / language / platforms
3. Click **Generate** (or **AI Rewrite** / **Regenerate**)
4. Preview per platform → **Copy**, **Save**, or **Export**
5. Use **Scheduler** with a saved Post ID, date, and time
6. Browse **History** to search, edit, reuse, or delete

## Notes

- Without API keys the app still runs using a built-in offline demo generator.
- Do not commit your `.env` file.
- Logs are written to `logs/app.log`.

## License

MIT — use and modify freely for your workflows.
