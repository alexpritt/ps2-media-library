# PS2 Media Library

Small freeware-style app for managing a physical game/music collection today, with room to grow into an emulator boot manager workflow.

## What It Does

- PS2-inspired UI with boot intro, console select, library, and details screens
- Organizes both Games and Music in one catalog
- Search and player-count filtering in the game library
- Per-console visual case/disc styles for a media-shelf look
- Admin mode for add/edit/delete, bulk upload, and console management
- Metadata + artwork helpers (LaunchBox for games, Deezer for music)

## Recent Updates

- ⭐ Added star ratings for games (gameplay + plot) and albums, plus star-based filtering.
- 🎬 Hardened boot intro playback: R2-first source, improved failover, iOS inline compatibility, and mobile intro fallback support.
- 🎛️ Refined library HUD and popup controls across desktop/mobile for better consistency and usability.
- 🛠️ Fixed admin game add/edit + bulk upload reliability by improving platform fallback/validation when system options are empty.

## Stack

- Frontend: Svelte + TypeScript + Vite
- Backend: FastAPI + SQLModel (Python 3.11+)
- Database: SQLite
- Hosting model: Cloudflare Pages (frontend) + Fly.io (backend)

## Quick Start

### 1) Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server now proxies `/api/*` to `http://127.0.0.1:8000` by default, so running the backend on port `8000` is enough for local end-to-end testing.

Optional production build check:

```bash
npm run build
```

## Environment Notes

- Local dev uses the Vite proxy automatically. To point the dev server at a different backend, set `VITE_API_PROXY_TARGET`.
- Set admin auth via `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH`.
- Optional boot intro sources: `VITE_BOOT_INTRO_SRC` (full intro) and `VITE_BOOT_MOBILE_SRC` (lighter mobile fallback)

If `VITE_BOOT_INTRO_SRC` is not set, the frontend falls back to the hosted R2 intro at `https://media.theavenoircollection.com/ps2-intro1080.mp4`.

Set `VITE_BOOT_MOBILE_SRC` to a smaller MP4 (for example `https://media.theavenoircollection.com/ps2-intro720.mp4`) so mobile and constrained-network clients can avoid stalling on the full intro.

## Deploy

- Frontend: deploy `frontend/` to Cloudflare Pages
- Backend: deploy `backend/` to Fly.io with `backend/fly.toml`
- Persistent DB on Fly: mount volume and set `DATABASE_PATH=/data/media.db`

## Intended Direction

Use it as a clean personal media library now. If you want, extend it later into a launch flow that boots directly into local emulator targets per title.
