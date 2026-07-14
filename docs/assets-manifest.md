# Asset manifest

Per ideation plan: every media asset used in the product or demo gets an entry here BEFORE use.
Fields: source URL, creator, license + version, attribution text, download date, derivatives allowed, notes.

## match-001 (PRIMARY) — SoccerTrack v2, one match

- **Source:** https://huggingface.co/datasets/atomscott/soccertrack-v2 (canonical; Google Drive mirror exists). Project page: https://atomscott.github.io/SoccerTrack-v2/ · Paper: arXiv:2508.01802
- **Creator:** Atom Scott et al. (SoccerTrack v2 authors)
- **License:** CC BY 4.0 (videos AND annotations — verified on project page 2026-07-13). Code: MIT.
- **Derivatives allowed:** Yes, including commercial, with attribution. No CC-ND/NC restriction.
- **Attribution text (use in app footer, README, demo video credits):**
  > Match footage: SoccerTrack v2 dataset © Atom Scott et al., licensed under CC BY 4.0 (https://huggingface.co/datasets/atomscott/soccertrack-v2). Video edited (cut, cropped, re-encoded).
- **Download date:** pending (tonight — one match only, both halves)
- **Contents:** 10 full amateur (university-level) matches, 4K panoramic MP4 split by half, ~900 min total. Includes ball-action-spotting annotations (12 classes incl. Goal, Shot, Free Kick) and game-state (player position) JSON.
- **Notes / fit assessment:**
  - Players gave informed consent; no names, jersey numbers only → clean ethically, and consistent with our rule that commentary never invents player names.
  - Annotations are **evaluation ground truth only** — the pipeline must propose moments from the video itself, otherwise the "AI-proposed" story is fake. Record this rule in the build plan.
  - Fixed panoramic full-pitch view, not broadcast style. Fits the "Every Angle" name; optional ffmpeg crop/zoom around the action as a polish item.
  - RISK: amateur-match audio may lack crowd-roar peaks → D3 audio gating may underperform; fallback = scene-motion/optical-flow density gate. Validate on first ingest.
  - 4K files are large: download ONE match, transcode a 720p working copy, archive the original.

## match-002 (BACKUP) — YouTube CC-BY amateur/semi-pro match

- **Source:** to be selected via YouTube search with Creative Commons filter (yt-dlp verifies `license: Creative Commons Attribution` in metadata before download).
- **License:** CC BY (YouTube's only CC option). MUST verify per-video via yt-dlp metadata, not the search filter alone; reject anything with Content ID claims or broadcast graphics/commentary.
- **Status:** not yet selected — only needed if match-001 footage proves unusable (e.g., panoramic view unacceptable for demo).

## Rejected sources (do not use)

- **archive.org uploads of Premier League / broadcast matches** — pirated broadcasts, uploader has no right to license them. Clearly-licensed requirement fails regardless of what the item page claims.
- **SoccerNet** — research-only license terms; not suitable for a public hackathon demo.
- **Stock-clip sites (Videezy/Mixkit/Vecteezy)** — b-roll only, no continuous match with real events; license terms vary per clip. Could serve UI polish imagery only; add entries here if actually used.
