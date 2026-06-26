# 🎮 PS2 Media Library

A personal web application that catalogs a physical media collection in a PlayStation 2 Browser-inspired UI. Frontend is deployed on Cloudflare Pages and backend API is deployed on Fly.io.

## 🏗️ Architecture

| Layer | Technology |
|---|---|
| Frontend | Svelte + TypeScript, built with Vite |
| Backend | Python 3.11, FastAPI, SQLModel |
| Database | SQLite (`backend/media.db`) |

## ✨ Features

### 🧭 UI / Navigation
- PS2-style boot screen with intro video and muted-by-default audio (click anywhere to enable sound)
- Boot intro is streamed from a range-enabled backend endpoint so skip/resume seek behavior is consistent
- Console selection grid for Games; direct library for Music
- Library grid with per-page animations, search bar (collapsible), and player-count filter
- Library header refinements: search/player filters are right-aligned beside the console header panel, search expands with blue hover fade, and controller icon tint animates on hover
- Details popup with rotating disc (Games) or vinyl sleeve (Music), full release date, genre, description, and scrollable notes
- Smooth fade transitions between all stages; fade-to-black when returning to boot screen
- Empty-state memory card graphic when a console has no games
- Refined console header hover behavior with smoother fade-in/fade-out text treatment
- Unified, glass-style select/dropdown visuals in admin and filter flows

### 🎵 Music Metadata + Art
- Deezer album metadata fetch for music items (album, artist, release date, genre, label, track list)
- Deezer album-art options picker in Admin for selecting alternate covers before save
- Music bulk upload now stores enriched metadata fields (genre, release date/year, label, track list)

### 🕹️ Supported Consoles
PlayStation 2, PlayStation 3, PlayStation 4, Nintendo DS, Nintendo 3DS, Wii, Xbox, Xbox 360 — plus custom user-defined systems

### 💿 Game Library Visual System
- Console-specific case banner overlays for PS2/PS3/PS4/Wii/Xbox/Xbox 360
- Console-specific disc overlays and disc-back styling for optical media platforms
- Handheld cartridge presentation overlays for Nintendo DS / Nintendo 3DS
- Library-only square icon treatment for handheld case cards (DS, 3DS)
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
- Bulk game upload uses the current platform filter selection and title-only lines (no ` - Platform` suffix required)
- Bulk upload panel includes live progress/status and line-level error reporting while requests are processing
- Multi-select and bulk delete support for library items
- Drag-and-drop media ordering in Library Manager (persisted)
- Custom console management (add / remove systems)
- LaunchBox fetch for Games with automatic population of title metadata and artwork
- Loaded Art panel for Games with upload controls for Box Art, Spine Art, and Disc Art
- LaunchBox art-option picker for selecting alternate Box/Spine/Disc assets before save
- Deezer fetch for Music with automatic population of album metadata and cover art
- Loaded Art panel for Music with upload controls and Deezer art-option selection
- System Manager drag-and-drop order controls persisted via backend reorder endpoint

### 🧱 Data Model (`MediaItem`)
`id` · `title` · `category` · `platform` · `genre` · `genres` · `release_date` · `year_released` · `rating` · `players` · `cooperative` · `artist` · `publisher` · `format` · `region` · `cover_image` · `spine_image` · `disc_image` · `tags` · `notes` · `display_order`

### 🔌 Backend Notes
- FastAPI provides API endpoints only (frontend is hosted separately on Cloudflare Pages)
- Legacy `/api/boot-video` remains as a redirect endpoint for older frontend builds
- Admin authentication uses a bearer token workflow for protected CRUD operations
- Startup migration helpers add new columns to existing SQLite databases automatically
- Input validation now blocks clearly invalid/injected game-title and platform payloads for metadata requests
- Game-data endpoint can return persisted cached records when metadata/art is already available
- Game-data fetch includes approved keyless fallback metadata source when LaunchBox cannot provide data
- Game-art options endpoint supports targeted retrieval by art type (`cover`, `spine`, `disc`, `cart`)
- Bulk games endpoint requires a selected platform parameter and applies that platform as source-of-truth when creating items
- Deezer endpoints support admin-side album metadata and art option retrieval: `/api/deezer/album-data`, `/api/deezer/album-art-options`
- Reorder endpoints persist drag-and-drop ordering for systems and media: `/api/systems/reorder`, `/api/media/reorder`

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

### 🧪 Frontend (Cloudflare Pages build)
```bash
cd frontend
npm install
npm run build
```

Set `VITE_API_BASE_URL` in your Pages environment to your Fly.io backend URL.

## Mobile QA Checklist

Run this before shipping UI changes:

- Devices: iPhone SE/12/15, Pixel 5/8, and one small tablet
- Orientation: verify portrait and landscape on phones
- Console view: no clipped headers, no hidden controls, and no horizontal scroll
- Library view: search toggle, players filter, card grid, and pager all usable by touch
- Details view: title/tags/notes readable, actions reachable, no clipping, and smooth scroll
- Admin view: panel, forms, tabs, list actions, and upload pickers fit without overflow
- Touch targets: primary controls (Back/Admin/Pager/Edit/Delete) are comfortably tappable (44px+)
- Final check: `cd frontend && npm run build` succeeds

### Mobile QA Results Template

Use this table after each mobile QA run:

| Date | Build/Commit | Tester | Notes |
|---|---|---|---|
| YYYY-MM-DD | `<hash or build id>` | `<name>` | `<overall summary>` |

| Device | OS/Browser | Orientation | Console | Library | Details | Admin | Touch Targets | Result |
|---|---|---|---|---|---|---|---|---|
| iPhone SE | iOS / Safari | Portrait | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| iPhone SE | iOS / Safari | Landscape | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| iPhone 12/15 | iOS / Safari | Portrait | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| iPhone 12/15 | iOS / Safari | Landscape | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| Pixel 5/8 | Android / Chrome | Portrait | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| Pixel 5/8 | Android / Chrome | Landscape | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| Small tablet | iPadOS or Android | Portrait | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| Small tablet | iPadOS or Android | Landscape | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |

Use this section for failures and follow-ups:

- Issue:
- Device/Orientation:
- Steps to reproduce:
- Expected:
- Actual:
- Fix PR/Commit:

### 🔐 Admin password
Set `ADMIN_PASSWORD` (or `ADMIN_PASSWORD_HASH`) as an environment variable for Fly.io. Change this before exposing the app externally.

## 🚀 Deployment

- Frontend: deploy `frontend/` to Cloudflare Pages
- Backend: deploy `backend/` to Fly.io (using `backend/fly.toml`)
- Persistent DB: Fly volume mounted at `/data` via `DATABASE_PATH=/data/media.db`
