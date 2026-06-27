# Game Fetch Logic Reference (Agent Context)

Last updated: 2026-06-27

This document stores the canonical context provided by the user for game fetch behavior so future agents can quickly align with intended logic.

## Core Priority Rules

1. Both single upload and bulk upload should fetch game info and box art from LaunchBox first.
2. Disc/cart art should be treated as art from the physical disc/cartridge and fetched only from LaunchBox unless a new source is proven reliably equivalent.
3. Spine art should be LaunchBox-first. TheCoverProject may have candidate images, but those include baked full-cover layouts and would require robust cropping to isolate spine-only content.

## Known LaunchBox Partial-Data Cases

Some titles have LaunchBox records but may not include all art categories (disc/cart or spine). These should not fail single or bulk upload.

Examples called out by user:

- Ratchet & Clank: Into The Nexus | PS3
- Uncharted 2: Among Thieves | PS3
- Red Faction: Armageddon | PS3
- Resistance 2 | PS3
- Resistance 3 | PS3
- Borderlands 3 | PS4
- Dark Souls III | PS4
- Red Dead Redemption | PS4

Required behavior:

- If a resource is unavailable, keep the upload/fetch successful.
- Do not fail the whole operation due to missing optional art.
- Surface a status message in existing error/status UI areas indicating which resource was unavailable.

## Popup Art Selection Requirements

Apply the same non-fatal unavailable-resource logic to the art picker popups for:

- Box art
- Disc/cart art
- Spine art

Also include scraped image options for the selected category from fallback resources alongside LaunchBox options.

## TheCoverProject Spine-Cropping Feasibility (Analysis Only)

User requested analysis only (no implementation yet):

- Feasible in principle, but likely high-complexity and fragile because source images vary by perspective, framing, and layout.
- Would require reliable detection/cropping to isolate spine segments per title.
- Should be approached as an experimental, gated fallback with measured quality before production use.

## Why This File Exists

This file is intended as a stable handoff artifact so other coding agents can reference the expected game-fetch contract quickly without reconstructing requirements from prior chat history.
