Frontend Public Assets

Static assets in this folder are published by Cloudflare Pages.

- Keep `ps2-intro.en.vtt` here so the boot-video captions are available at `/ps2-intro.en.vtt`.
- Boot video playback supports split sources via frontend env vars:
	- `VITE_BOOT_INTRO_SRC` (one-time intro clip)
	- `VITE_BOOT_LOOP_SRC` (looping ambient clip)
- Recommended hosted targets:
	- `https://media.theavenoircollection.com/ps2-intro-intro.mp4`
	- `https://media.theavenoircollection.com/ps2-intro-loop.mp4`

## Suggested media pipeline

Use ffmpeg to generate a short intro plus a compact loop from the original long source:

```bash
# Intro segment: first 10 minutes
ffmpeg -ss 0 -i ps2-intro-source.mp4 -t 600 \
	-vf "scale=-2:1080" -c:v libx264 -preset veryfast -crf 23 \
	-c:a aac -b:a 128k -movflags +faststart \
	ps2-intro-intro.mp4

# Loop segment: starts at skip point (6s), duration 4 minutes
ffmpeg -ss 6 -i ps2-intro-source.mp4 -t 240 \
	-vf "scale=-2:1080" -c:v libx264 -preset veryfast -crf 24 \
	-c:a aac -b:a 112k -movflags +faststart \
	ps2-intro-loop.mp4
```
