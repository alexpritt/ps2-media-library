# PS2-Style Media Library

A Raspberry Pi-friendly web application for organizing physical media collections in a PlayStation 2 Browser-style UI.

## Architecture

- Frontend: Svelte
- Backend: Python + FastAPI
- Database: SQLite

## Setup

1. Install Python 3.11+ and Node.js 20+.
2. From `ps2-media-library/backend`, create a virtual environment and install dependencies.
3. From `ps2-media-library/frontend`, install node dependencies and build.
4. Run `backend/main.py` to start the app.

## Deployment

- Serve the app from the Pi using the backend.
- For outside access, use Cloudflare Tunnel / Tailscale or router port forwarding.
