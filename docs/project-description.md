# Every Angle — project description

Every Angle turns full-match football footage into moments an editor can trust, find, and publish.
Instead of asking a model to produce a highlight reel in one opaque step, it separates machine
attention from human truth: signal detection narrows the footage, Claude vision proposes notable
moments, a person reviews the evidence, and only accepted events become searchable clips or enter
the final reel.

That boundary is visible throughout the product. Sodium marks machine proposals; chalk marks
human-verified truth. The timeline shows candidate windows, rejected ranges, and playable kept
events together, so an editor can see both what the system found and what a person approved. The
match summary is derived from the same verified timeline and does not invent a score, team, or
scorer when the footage cannot establish one.

The workflow starts with motion-density, audio, and scene-change signals that reduce a long match
to reviewable windows. Claude receives sampled frames from those windows under a structured,
strict caption contract and a hard budget cap. In Review, an editor can play the proposal clip,
keep or reject it, correct its caption or type, and add a missed event when source footage is
available. Accepted events are promoted through a revisioned manifest and indexed in Qdrant with
local FastEmbed embeddings. Search therefore runs over verified captions, never over unreviewed
model output. Quick Highlights applies deterministic incident grouping and duration rules, while
the Reel workspace lets an editor order clips before FFmpeg joins them without another model call.

The result is useful for teams that cannot dedicate an editor to watching every minute of every
match. A grassroots club can turn a fixed-camera recording into searchable, shareable moments;
an editorial team can apply the same review, search, and assembly layer to already-directed
footage. The current pipeline is batch-based rather than live, keeping the submitted system
focused on a reliable end-to-end path.

On a real 45:05 SoccerTrack v2 match half, the detector surfaced both annotated goals for review
(2/2) while reducing the footage queued for a person to 11.2 minutes. Detection ran in 54 seconds
on a laptop CPU. Dataset annotations were used only to measure recall; they were never provided to
the pipeline.

The application is built with React, TypeScript, Vite, and FastAPI. Claude provides visual event
understanding, Qdrant provides semantic retrieval over the promoted manifest, and FFmpeg handles
clip and reel generation. A multi-stage Docker image builds the frontend, preloads the local
embedding model, and serves the UI, API, and media from one origin. The reviewed deployment path
uses Render with Qdrant Cloud.

The public demo ships only edited SoccerTrack v2 footage licensed under CC BY 4.0. Copyrighted
broadcast footage used for local profile testing is excluded from the repository, deploy image,
screenshots, and demo video. That release boundary reflects the same principle as the product:
provenance is part of the system, not a footnote.
