Frontend Public Assets

Static assets in this folder are published by Cloudflare Pages.

- Keep `ps2-intro.en.vtt` here so the boot-video captions are available at `/ps2-intro.en.vtt`.
- The boot screen uses a desktop-first R2 intro source and a separate mobile fallback clip.
- `VITE_BOOT_INTRO_SRC` should point at the full hosted intro for desktop, typically `https://media.theavenoircollection.com/ps2-intro.mp4`.
- `VITE_BOOT_MOBILE_SRC` can point at a smaller mobile-friendly clip, or stay unset to use `/boot.mp4`.
