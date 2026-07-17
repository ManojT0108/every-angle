# Design decision: Quick Highlights — verification model + curation

## The question (user, 2026-07-15)

One-click "Quick Highlights" that auto-assembles a highlight reel. Should it (a) build only from
**human-verified** (accepted) moments, or (b) let the **AI auto-decide** what goes in (goals,
cards, close chances, attacking-play-but-missed, game-changer goals), possibly with per-moment
"why it matters" analytics?

## FINAL design (verified-first, deterministic — Codex-hardened R1)

Codex verdict: "Verified-first is the right default for a judged demo. The unverified mode should
not be the headline—or ship before the deadline." Adopted, with its four fixes:

- **Source = the promoted (verified) manifest.** Build only from accepted moments. Protects the
  "AI-assisted, human-verified" promise and removes the demo-day risk of a hallucinated event.
- **Deterministic + client-side (Codex P2d).** No runtime LLM ranking — a pure, reliable
  frontend function over the promoted manifest. No new failure path, instant, free.
- **Dedup into incidents (Codex P1).** Real manifests contain overlapping windows for one goal
  and a long celebration. Cluster overlapping / near-adjacent events into incidents and take ONE
  representative per incident (else the reel is 8 replays of the same goal). **Reserve one terminal
  celebration slot** (final-whistle / trophy) so the ending is not dropped.
- **Rank by AVAILABLE fields only (Codex P2a).** Rank by event `type`:
  `goal > penalty > save > counterattack > card`; **all goals equal**; `celebration` handled as the
  reserved terminal slot (not ranked among play). No invented "game-changer" / severity fields.
- **Hard caps (Codex P2c): ≤ 8 incidents AND ≤ 90 s total**, skipping any candidate that would
  exceed the duration budget.
- **Final order = chronological** so the reel tells the match's story.
- **Empty verified pool → button disabled; near-empty → use all available events (Codex P2d).**
- One click → assemble via the existing reel builder. Speed preserved because the demo match is
  pre-verified; a judge also gets it instantly.

## Explicitly OUT of deadline scope (Codex P2d)

- "Why it matters" per-clip blurb (needs an LLM call — future).
- Unverified auto-mode (dilutes the verified-first story; not the headline).
- Real goal analytics (xG, player speed) — no tracking data for broadcast.

## Questions for the reviewer

1. Is verified-first the right DEFAULT for this product and a live judged demo, or does the speed
   story justify an unverified auto-mode as the headline?
2. Is the highlight-worthiness ranking sensible, or is anything mis-ranked for football?
3. Does sourcing highlights from the manifest fit cleanly with the live-Verify write-through
   (single canonical manifest), including an empty/near-empty verified pool (graceful behavior)?
4. Deadline pragmatism: what to cut or simplify. This is one of four features (live-Verify,
   reel replace/merge, reel organizer, quick-highlights) plus a required deploy in ~2 days.
