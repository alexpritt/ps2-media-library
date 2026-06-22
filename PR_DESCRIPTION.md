# Pull Request: Bulk Upload Platform Source, Progress, and Error Handling

## Overview
This PR updates bulk upload behavior for Games so platform selection comes from the Library Manager platform filter (not from each line or LaunchBox return labels), and adds a live progress/status experience with clearer error reporting in the bulk upload panel.

## Changelog

### Backend
- Added `platform` to the bulk games request payload.
- `POST /api/bulk/games` now requires a non-empty selected platform.
- Bulk game lines are now parsed as title-only entries (one game title per line).
- LaunchBox metadata is still used for game details/art, but saved item `platform` always uses the selected filter platform.
- Removed the old `Game Title - Platform` parsing requirement from bulk games.

### Frontend
- Bulk Games UI now instructs users to enter one title per line.
- Bulk Games request now sends `{ items, platform }` where `platform` is taken from the selected platform filter above the bulk editor.
- Added guard messaging when trying to bulk upload games with platform filter set to `All`.
- Added live bulk upload progress state:
  - progress bar under upload button
  - status text with processed/remaining/success/failure counts
  - error summary text when any line fails
- Added per-line network and request error handling during upload processing.
- Added CSS styles for bulk progress panel, progress bar, status text, and error text.

### Documentation
- Updated README with:
  - title-only games bulk input format
  - selected-filter platform source-of-truth behavior
  - new progress/status/error UI behavior for bulk upload

## Files Changed
- README.md
- backend/main.py
- frontend/src/App.svelte
- frontend/src/app.css

## Testing
- Frontend build: `npm run build` (success)
- Manual API verification:
  - bulk games accepts title-only lines when platform is supplied
  - saved game platform matches selected app platform (not LaunchBox platform label)

## Notes
- Existing unrelated Svelte accessibility warning about missing captions track on boot video remains unchanged in this PR.
