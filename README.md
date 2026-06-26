# PS2 Media Library

Small freeware-style app for managing a physical game/music collection today, with room to grow into an emulator boot manager workflow.

## What It Does

- PS2-inspired UI with boot intro, console select, library, and details screens
- Organizes both Games and Music in one catalog
- Search and player-count filtering in the game library
- Per-console visual case/disc styles for a media-shelf look
- Admin mode for add/edit/delete, bulk upload, and console management
- Metadata + artwork helpers (LaunchBox for games, Deezer for music)

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

Optional production build check:

```bash
npm run build
```

## Environment Notes

- Set `VITE_API_BASE_URL` for the frontend to point at your backend.
- Set admin auth via `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH`.
- Optional boot video sources:
  - `VITE_BOOT_INTRO_SRC`
  - `VITE_BOOT_LOOP_SRC`

If intro/loop values are not provided, the app falls back to the legacy single boot-video source behavior.

## Deploy

- Frontend: deploy `frontend/` to Cloudflare Pages
- Backend: deploy `backend/` to Fly.io with `backend/fly.toml`
- Persistent DB on Fly: mount volume and set `DATABASE_PATH=/data/media.db`

## Intended Direction

Use it as a clean personal media library now. If you want, extend it later into a launch flow that boots directly into local emulator targets per title.
