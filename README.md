# PS2 Media Library

A personal web application that catalogs my physical media collection in a PlayStation 2 Browser-inspired UI. Built to run on a Raspberry Pi and be accessible from anywhere.

## Architecture

| Layer | Technology |
|---|---|
| Frontend | Svelte + TypeScript, built with Vite |
| Backend | Python 3.11, FastAPI, SQLModel |
| Database | SQLite (`backend/media.db`) |

## Features

### UI / Navigation
- PS2-style boot screen with intro video and muted-by-default audio (click anywhere to enable sound)
- Console selection grid for Games; direct library for Music
- Library grid with per-page animations, search bar (collapsible), and player-count filter
- Details popup with rotating disc (Games) or vinyl sleeve (Music), full release date, genre, description, and scrollable notes
- Smooth fade transitions between all stages; fade-to-black when returning to boot screen
- Empty-state memory card graphic when a console has no games

### Supported Consoles
PlayStation 2, PlayStation 3, PlayStation 4, Nintendo DS, Game Boy — plus custom user-defined systems

### Admin Panel
- Password-protected session token login
- Add, edit, and delete Games and Music entries
- Full-date release date picker (day / month / year) — stores `YYYY-MM-DD`, derives year automatically
- Inline edit from the details popup skips the confirm step and refreshes the popup on save
- Admin list pre-filtered to the current library's category and platform on open
- Bulk edit mode (accessed from library admin toolbar) retains standard confirm flow
- Custom console management (add / remove systems)

### Data Model (`MediaItem`)
`id` · `title` · `category` · `platform` · `genre` · `release_date` · `year_released` · `players` · `artist` · `cover_image` · `notes` · `publisher` · `format` · `region` · `tags`

### Backend Utilities
| Script | Purpose |
|---|---|
| `backend/refresh_library_details.py` | Bulk-refresh notes/descriptions from Wikipedia for all entries |
| `backend/refresh_release_dates.py` | Fetch structured release dates from Wikidata (property P577) for all entries |

## Setup

### Requirements
- Python 3.11+
- Node.js 20+

### Backend
```bash
cd backend
python -m venv .venv-1
.venv-1\Scripts\activate        # Windows
# source .venv-1/bin/activate   # macOS / Linux
pip install -e .
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### Frontend (build once, served by backend)
```bash
cd frontend
npm install
npm run build
```

The backend serves the built frontend from `frontend/build/` and the intro video from `frontend/suggestions/ps2-intro.mp4`.

### Admin password
Set `ADMIN_PASSWORD` in `backend/main.py` (default: `foreverandalways`). Change this before exposing the app externally.

## Deployment

Run the backend on a Raspberry Pi (or any always-on machine). For remote access use one of:
- **Cloudflare Tunnel** — no open ports required
- **Tailscale** — zero-config VPN
- **Router port forwarding** — expose port 8000 directly
