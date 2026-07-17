# Every Angle demo video

> **STATUS — SUPERSEDED DRAFT (2026-07-16 PM PDT):** This guide and its matching narration/SRT
> predate the live Broadcast Feed. There is no final screen recording or uploadable MP4. Do not
> record or upload this version unchanged. The next revision must show both source selectors,
> switch to **Broadcast feed**, demonstrate the verified **`trophy lift`** search and clip, and
> update the final credits. See `.ai/HANDOFF.md` for the exact takeover sequence.

Target runtime: **105–115 seconds**. Record only the bundled `match-001` SoccerTrack v2 demo from a
freshly reset session. Do not show local broadcast footage, API keys, terminal windows, or browser
bookmarks.

## Shot list and narration

Use a neutral synthetic documentary voice at roughly 125–135 words per minute. Read the narration
as written; leave short pauses for clip audio and interface actions. The same narration is available
without the shot table in [`demo-narration.txt`](demo-narration.txt) for direct paste into a voice
generator.

A ready-to-import caption track is provided in [`demo-captions.srt`](demo-captions.srt). Adjust
individual cue boundaries after the final edit if clip pauses change the timing.

| Time | Picture and exact action | Narration |
|---|---|---|
| 0:00–0:10 | Open the app at the top of the page. Hold on “Find the moments. Prove every one.” and the four workflow steps. | “A full football match contains a few moments people need, buried inside everything else. Every Angle finds those moments, then makes a human the final authority.” |
| 0:10–0:22 | Scroll just enough to frame the verified match summary and the top of the timeline. Pause on the two displayed goal groups and CC-BY source label. | “The system narrows the footage, Claude proposes what happened, and an editor reviews the evidence. Only verified events reach this match summary, search, or the final reel.” |
| 0:22–0:36 | In the timeline, click **+** once. Scroll to the goal at **23:32**, click its playable marker, let the clip run for 4–5 seconds, then close it with **×**. | “The provenance timeline keeps the whole process visible: candidate windows below, human decisions alongside them, and every available verified clip playable in place.” |
| 0:36–0:56 | Click **Review**. On the pending goal proposal at **43:11**, click the clip, play 3–4 seconds, close it, then click **Keep**. Pause as the row moves to Reviewed. | “Here is the human-in-the-loop step. The model suggests a goal from the visual sequence. The editor can inspect the footage, correct the description, reject it, or keep it. This decision updates the verified manifest.” |
| 0:56–1:14 | Click **Search**. Enter the exact query **keeper comes off his line**, click **Search**, then play the first result for 3–4 seconds and close it. | “Search is grounded in that manifest, not raw model output. A natural-language query finds the verified moment where the keeper comes off his line, with its clip and provenance attached.” |
| 1:14–1:31 | Click **Quick Highlights**, then click the **Reel** tab. Show the ordered moment list and its runtime. Click **Build reel**. | “Quick Highlights groups replay-adjacent incidents and selects a deterministic edit. The organizer can change the order, while FFmpeg assembles the reel without another model call.” |
| 1:31–1:45 | Play 6–8 seconds of the built reel. End on the Reel controls or briefly return to the hero. | “For a club or content team, that turns a long recording into searchable, ready-to-share moments — while keeping the person, the evidence, and the rights boundary in control.” |
| 1:45–1:52 | Cut to the attribution card below. No interface action. | “Every Angle. Find the moments. Prove every one.” |

## Fallback shots

- If Qdrant search is unavailable, clear the query and submit the empty field to return to verified
  browse mode. Show the **15:38** counterattack row, play its clip, and continue with **Quick
  Highlights**. Replace the search narration sentence with: “Browse and reel assembly still read
  only the verified manifest; no unreviewed model output appears here.”
- If the pending **43:11** proposal was already reviewed, restart the deployed service to restore
  the bundled baseline. If a restart is not possible, show an accepted Reviewed row, open its clip,
  and demonstrate **Edit** without saving.
- Before the final recording, capture one clean backup of the **23:32** timeline clip, the search
  result at **15:38**, and a successfully built reel. If a network or FFmpeg delay interrupts the
  main take, cut to those shots rather than showing a spinner or error.
- If timeline scrolling is awkward on the recording machine, use the zoom-minus control once and
  click the **23:32** marker without horizontal scrolling.

## Recording and export

- Browser viewport: 1440×900 or 1600×900, 100% zoom, bookmarks bar hidden, notifications off.
- Capture: 1920×1080, 30 fps, system audio on for short match-clip moments, cursor visible.
- Voice: neutral documentary delivery, no promotional exaggeration, normalized around −16 LUFS.
- Export: MP4, H.264, 1080p, 30 fps, 12–16 Mbps video; AAC, 48 kHz, 192 kbps audio.
- Use straight cuts and brief dissolves only. Do not add stock footage, copyrighted music, a fake
  scoreline, named teams, named scorers, or broadcast footage.
- Add readable captions, then watch the exported file once at normal speed and once muted.

## Final attribution card

Hold for 6–7 seconds on the existing night-pitch background with chalk text and one sodium rule:

> EVERY ANGLE<br>
> Find the moments. Prove every one.<br>
> <br>
> Match footage: SoccerTrack v2 dataset © Atom Scott et al.<br>
> Licensed under CC BY 4.0 · Video edited (cut, cropped, re-encoded)<br>
> https://huggingface.co/datasets/atomscott/soccertrack-v2

## Upload and submission checklist

- [ ] Reset the demo and complete Review → Search → Reel once before recording.
- [ ] Confirm the recording contains only `match-001` CC-BY footage.
- [ ] Verify narration, captions, query spelling, clip playback, and final attribution.
- [ ] Check the final MP4 is 90–120 seconds, 1080p, and understandable with audio muted.
- [ ] Upload the video and test playback from the returned URL in a signed-out window.
- [ ] Add the public GitHub repository, verified working demo URL, project description, and video
      URL to the portal.
- [ ] Open every submitted link once, then submit before **July 17, 2026, 10:00 AM PDT**.
