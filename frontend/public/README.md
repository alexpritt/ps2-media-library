Frontend Public Assets

Static assets in this folder are published by Cloudflare Pages.

- Keep `ps2-intro.en.vtt` here so the boot-video captions are available at `/ps2-intro.en.vtt`.
- The boot screen uses a single hosted R2 intro source across all devices.
- `VITE_BOOT_INTRO_SRC` should point at the full hosted intro, typically `https://media.theavenoircollection.com/ps2-intro.mp4`.
