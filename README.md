# 🎮 PS2 Media Library

A personal web application that catalogs my physical media collection in a PlayStation 2 Browser-inspired UI. Built to run on a Raspberry Pi and be accessible from anywhere.

## 🏗️ Architecture

| Layer | Technology |
|---|---|
| Frontend | Svelte + TypeScript, built with Vite |
| Backend | Python 3.11, FastAPI, SQLModel |
| Database | SQLite (`backend/media.db`) |

## ✨ Features

### 🆕 Recent Updates
- Multi-source metadata flow for games: LaunchBox first, with approved keyless fallback metadata when LaunchBox is unavailable
- LaunchBox art-option picker for Box Art, Spine Art, and Disc/Cart Art directly in Admin
- Per-system appearance model added (case type + appearance preset + display order) and used by library rendering
- Systems can be reordered with drag-and-drop in System Manager (persisted to backend)
- Details view now includes interactive metadata tags that can instantly apply library search filters
- Console case visuals were expanded and tuned for PS2/PS3/PS4/GameCube/Wii/Xbox/Xbox 360 plus handheld cartridge styles
- Box-front art sizing now uses full-coverage fitting for cleaner per-console case presentation
- Admin popup styling was unified across Admin Access, Hub, System Manager, and Library Manager

### 🧭 UI / Navigation
- PS2-style boot screen with intro video and muted-by-default audio (click anywhere to enable sound)
- Console selection grid for Games; direct library for Music
- Library grid with per-page animations, search bar (collapsible), and player-count filter
- Details popup with rotating disc (Games) or vinyl sleeve (Music), full release date, genre, description, and scrollable notes
- Smooth fade transitions between all stages; fade-to-black when returning to boot screen
- Empty-state memory card graphic when a console has no games
- Refined console header hover behavior with smoother fade-in/fade-out text treatment
- Unified, glass-style select/dropdown visuals in admin and filter flows

### 🕹️ Supported Consoles
PlayStation 2, PlayStation 3, PlayStation 4, Nintendo DS, Nintendo 3DS, Game Boy, GameCube, Wii, Xbox, Xbox 360 — plus custom user-defined systems

### 💿 Game Library Visual System
- Console-specific case banner overlays for PS2/PS3/PS4/GameCube/Wii/Xbox/Xbox 360
- Console-specific disc overlays and disc-back styling for optical media platforms
- Handheld cartridge presentation overlays for Nintendo DS / Nintendo 3DS / Game Boy
- Library-only square icon treatment for handheld case cards (Game Boy, DS, 3DS)
- Wii/Xbox/Xbox 360 overlay set refresh and expanded disc-back asset mapping
- Layered cover/spine rendering with blurred background pass plus foreground art pass
- Full-coverage box-front art fitment for PS2/Wii/Xbox/Xbox 360 case presets

### 🛠️ Admin Panel
- Password-protected session token login
- Add, edit, and delete Games and Music entries
- Full-date release date picker (day / month / year) — stores `YYYY-MM-DD`, derives year automatically
- Inline edit from the details popup skips the confirm step and refreshes the popup on save
- Admin list pre-filtered to the current library's category and platform on open
- Bulk edit mode (accessed from library admin toolbar) retains standard confirm flow
- Custom console management (add / remove systems)
- LaunchBox fetch for Games with automatic population of title metadata and artwork
- Loaded Art panel for Games with upload controls for Box Art, Spine Art, and Disc Art
- LaunchBox art-option picker for selecting alternate Box/Spine/Disc assets before save
- System Manager drag-and-drop order controls persisted via backend reorder endpoint

### 🧱 Data Model (`MediaItem`)
`id` · `title` · `category` · `platform` · `genre` · `genres` · `release_date` · `year_released` · `rating` · `players` · `cooperative` · `artist` · `publisher` · `format` · `region` · `cover_image` · `spine_image` · `disc_image` · `tags` · `notes`

### 🔌 Backend Notes
- FastAPI serves the compiled frontend and suggestions asset directories directly
- Admin authentication uses a bearer token workflow for protected CRUD operations
- Startup migration helpers add new columns to existing SQLite databases automatically
- Game-data endpoint can return persisted cached records when metadata/art is already available
- Game-data fetch includes approved keyless fallback metadata source when LaunchBox cannot provide data
- Game-art options endpoint supports targeted retrieval by art type (`cover`, `spine`, `disc`, `cart`)

## ⚙️ Setup

### ✅ Requirements
- Python 3.11+
- Node.js 20+

### 🐍 Backend
```bash
cd backend
python -m venv .venv-1
.venv-1\Scripts\activate        # Windows
# source .venv-1/bin/activate   # macOS / Linux
pip install -e .
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 🧪 Frontend (build once, served by backend)
```bash
cd frontend
npm install
npm run build
```

The backend serves the built frontend from `frontend/build/` and the intro video from `frontend/suggestions/ps2-intro.mp4`.

### 🔐 Admin password
Set `ADMIN_PASSWORD` in `backend/main.py` (default: `foreverandalways`). Change this before exposing the app externally.

## 🚀 Deployment

Run the backend on a Raspberry Pi (or any always-on machine). For remote access use one of:
- **Cloudflare Tunnel** — no open ports required
- **Tailscale** — zero-config VPN
- **Router port forwarding** — expose port 8000 directly
