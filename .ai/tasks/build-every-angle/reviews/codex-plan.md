# Plan checkpoint review: `build-every-angle`

## Reviewed scope

- `AGENTS.md`
- `README.md`
- `.ai/HANDOFF.md`
- `.ai/tasks/build-every-angle/{brief.md,plan.md}`
- Accepted upstream decisions in `.ai/tasks/ideation/plan.md`
- Official constraints in `docs/hackathon-brief.md`

## Findings

### High — Deployment has no artifact delivery strategy

**Confirmed design gap.** The app reads local pipeline artifacts, while `data/` is gitignored, yet deployment assumes precomputed artifacts will be available.

- `.ai/tasks/build-every-angle/plan.md:9-10`
- `.ai/tasks/build-every-angle/plan.md:46`
- `.ai/tasks/build-every-angle/plan.md:84-85`

**Failure scenario:** Streamlit deploys successfully, but has no manifests or clips. Search may return Qdrant payloads containing relative clip paths, while playback and reel assembly fail because those files never reached the host.

**Recommended fix:** Choose an explicit artifact topology before implementation: either repository-packaged demo assets, object storage with durable URLs/download caching, or an InsForge-backed store. Define how manifests, clips, and source video reach the deployed app, including size/licensing constraints and behavior after host restarts.

### Medium — Gate 1 acceptance omits two required deliverables

**Confirmed plan defect.** M0 and its verification criteria omit the InsForge hello-world and submission-portal checklist required by the task brief and accepted ideation plan.

- `.ai/tasks/build-every-angle/brief.md:11-14`
- `.ai/tasks/build-every-angle/plan.md:93`
- `.ai/tasks/build-every-angle/plan.md:110-112`

**Failure scenario:** M0 is declared green despite neither resolving the deployment decision nor learning the required submission artifacts.

**Recommended fix:** Add both deliverables to M0 acceptance, recording the timeboxed InsForge outcome and portal requirements in durable task documentation.

### Medium — Manifest edits can leave clips and Qdrant stale

**Confirmed underspecification.** Verification writes the source-of-truth manifest, but the plan does not define an atomic publish/rebuild workflow for dependent clips and the Qdrant cache.

- `.ai/tasks/build-every-angle/plan.md:22-31`
- `.ai/tasks/build-every-angle/plan.md:43`
- `.ai/tasks/build-every-angle/plan.md:77`

**Failure scenario:** A reviewer corrects an event’s caption or timestamps; search still returns the old caption and playback uses the old clip.

**Recommended fix:** Define one explicit publish operation: atomically save the manifest, regenerate changed clips, rebuild/upsert the index, and expose the new version only after all steps succeed. A manifest hash or revision can identify stale derivatives.

### Medium — Reproducible runtime and deployment dependencies are absent

**Confirmed planning gap.** The proposed scaffold has no Python dependency manifest, Qdrant development setup, or FFmpeg host installation configuration.

- `.ai/tasks/build-every-angle/plan.md:79-89`

**Failure scenario:** Local development works on one machine, but Streamlit cannot import FastEmbed dependencies or execute FFmpeg.

**Recommended fix:** Add a pinned `requirements.txt`/`pyproject.toml`, local Qdrant setup such as Compose, and deployment-specific FFmpeg/system-package configuration. Include a clean-environment smoke test.

### Low — Verification UI scope is aggressive for the gate

**Suggestion.** Merge, split, manual addition, editing, rejection, and clip regeneration are all scheduled before M2.

- `.ai/tasks/build-every-angle/plan.md:75`
- `.ai/tasks/build-every-angle/plan.md:95`

**Failure scenario:** Complex editor-state work delays the Search/Reel golden path.

**Recommended fix:** Make accept/reject, caption/time edits, and manual addition the MVP. Defer merge/split unless actual footage proves they are necessary.

## Open questions

- Where will deployed manifests and video clips live?
- Must verification changes persist across application restarts, or is the deployed Verify view demo-only?
- What exact event should trigger clip regeneration and Qdrant reindexing?
- Are the Anthropic key and proposed API budget approved before Gate 2?

## Final verdict

**CHANGES REQUIRED.** The local architecture is sensible, but the artifact deployment path and derived-data publication lifecycle must be decided before the plan is implementation-ready. Gate 1 acceptance should also be aligned with the already-approved brief.