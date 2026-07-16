# AI Social Media Automation

Generate human-sounding social posts for LinkedIn, X, Facebook, and Instagram — desktop **or** free web deploy on Render.

## Why Render failed before

Render has **no GUI / no `_tkinter`**. The old CustomTkinter desktop UI cannot run there.

`app.py` now auto-switches to a **FastAPI web UI** on Render (or when Tk is missing).

## Deploy on Render (free)

1. Push this repo to GitHub
2. [Render](https://render.com) → **New → Web Service** → connect repo
3. Settings:
   - **Runtime:** Python 3
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `python app.py`
   - **Python version:** `3.12.8` (env `PYTHON_VERSION`)
4. Add env var: `OPENAI_API_KEY` = your key (optional but recommended)
5. Deploy → open the `.onrender.com` URL

Or use the included `render.yaml` Blueprint.

## Features

- Web UI (Render / cloud) + Desktop UI (local Mac/Windows)
- OpenAI generation with optional NVIDIA NIM fallback
- Offline demo mode when no API keys are set
- Auto image generation (DALL·E or local poster)
- Multi-platform previews, exports, history, scheduler

## Local quick start

```bash
cd AI-Social-Automation
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Desktop UI (needs Tk):
python app.py
# Or force web UI in browser:
python app.py --web
```
## Project layout

| File | Role |
|------|------|
| `app.py` | Entry point (desktop or web) |
| `web_app.py` | FastAPI web UI (Render) |
| `ui.py` | Desktop CustomTkinter UI |
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
