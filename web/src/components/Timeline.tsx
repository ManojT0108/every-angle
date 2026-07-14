import { isHumanAdded, timecode, type Timeline as TL } from "../lib/api";

/**
 * The match timeline — the signature element of the whole app.
 *
 * Below the line: every candidate window the detector opened. Where the machine
 * LOOKED.
 * Above the line: the verified moments. What a human KEPT — chalk for
 * human-added, sodium for AI-proposed — and the rejected proposals, struck
 * through, because the machine being wrong out loud is the honest part.
 *
 * It is not decoration. It is the product argument in one graphic.
 */
export function Timeline({
  data,
  onSeek,
  activeId,
}: {
  data: TL;
  onSeek?: (t: number) => void;
  activeId?: string | null;
}) {
  const { duration, windows, events, rejected } = data;
  const pct = (t: number) => (t / duration) * 100;

  const reviewed = windows.reduce((a, w) => a + (w.t_end - w.t_start), 0);
  const ticks = Array.from({ length: Math.floor(duration / 600) + 1 }, (_, i) => i * 600);

  return (
    <section aria-label="Match timeline">
      <header className="mb-2.5 flex flex-wrap items-baseline justify-between gap-4">
        <span className="eyebrow">Match timeline</span>
        <div className="flex flex-wrap gap-4 font-mono text-[10px] tracking-wide text-chalk-faint">
          <Key swatch="bg-chalk" label="Human-verified" />
          <Key swatch="bg-sodium" label="AI-proposed" />
          <Key swatch="border border-dashed border-chalk-faint" label="Rejected" />
          <Key swatch="bg-sodium-dim" label="Candidate window" />
        </div>
      </header>

      <div className="relative h-[108px] border border-line bg-ink-800 px-3">
        {/* the ground the match is played on */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-35"
          style={{
            background:
              "repeating-linear-gradient(90deg, transparent 0 44px, color-mix(in srgb, var(--color-turf) 7%, transparent) 44px 88px)",
          }}
        />

        {/* WHAT A HUMAN KEPT — above the line */}
        <div className="absolute inset-x-3 top-0 h-[54px]">
          {events.map((e) => {
            const human = isHumanAdded(e);
            const active = activeId === e.id;
            return (
              <button
                key={e.id}
                onClick={() => onSeek?.(e.t_start)}
                style={{ left: `${pct(e.t_start)}%` }}
                title={e.caption}
                className="group absolute bottom-0 flex -translate-x-1/2 flex-col items-center"
                aria-label={`${e.type} at ${timecode(e.t_start)}`}
              >
                {/* Labels collide when moments cluster, so only GOALS are labelled
                    at rest — the rest reveal on hover. The marks stay legible. */}
                <span
                  className={`mb-1 whitespace-nowrap rounded-[1px] bg-ink-800/90 px-1 font-mono text-[9px] uppercase tracking-wider transition-opacity ${
                    e.type === "goal" || active
                      ? "text-chalk opacity-100"
                      : "text-chalk-dim opacity-0 group-hover:opacity-100"
                  }`}
                >
                  {e.type === "goal" ? "Goal" : "Break"} {timecode(e.t_start)}
                </span>
                <span
                  className={`-mb-px border-2 border-ink-800 ${
                    human ? "bg-chalk" : "bg-sodium"
                  } ${e.type === "goal" ? "size-3.5" : "size-2.5"} ${
                    active ? "ring-2 ring-sodium" : ""
                  }`}
                />
                <span className={`h-5 w-0.5 ${human ? "bg-chalk" : "bg-sodium"}`} />
              </button>
            );
          })}

          {/* the machine, wrong, out loud */}
          {rejected.map((r) => (
            <div
              key={r.proposal_id}
              style={{ left: `${pct(r.t_start)}%` }}
              title={`Rejected by a human — ${r.caption}`}
              className="group absolute bottom-0 flex -translate-x-1/2 flex-col items-center opacity-70"
            >
              <span className="mb-1 whitespace-nowrap rounded-[1px] bg-ink-800/90 px-1 font-mono text-[9px] uppercase tracking-wider text-chalk-faint line-through opacity-0 transition-opacity group-hover:opacity-100">
                {timecode(r.t_start)}
              </span>
              <span className="-mb-px size-2.5 border border-dashed border-chalk-faint" />
              <span className="h-5 w-px bg-chalk-faint opacity-50" />
            </div>
          ))}
        </div>

        <div className="absolute inset-x-3 top-[54px] h-px bg-line" />

        {/* WHERE THE MACHINE LOOKED — below the line */}
        <div className="absolute inset-x-3 top-[55px] h-6">
          {windows.map((w) => {
            const cues = [w.motion_peak, w.audio_peak, w.scene_cut].filter(Boolean).length;
            return (
              <div
                key={w.id}
                style={{ left: `${pct(w.t_start)}%`, height: 5 + cues * 4 }}
                title={`${w.id} · ${timecode(w.t_start)}–${timecode(w.t_end)} · ${
                  [
                    w.motion_peak && "motion",
                    w.audio_peak && "crowd audio",
                    w.scene_cut && "scene cut",
                  ]
                    .filter(Boolean)
                    .join(" + ") || "no cue"
                }`}
                className="absolute top-0 w-px bg-sodium-dim"
              />
            );
          })}
        </div>

        <div className="tnum absolute inset-x-3 bottom-1.5 h-3.5 font-mono text-[9px] tracking-wide text-chalk-faint">
          {ticks.map((t) => (
            <span key={t} style={{ left: `${pct(t)}%` }} className="absolute -translate-x-1/2">
              {timecode(t)}
            </span>
          ))}
          <span className="absolute right-0">{timecode(duration)}</span>
        </div>
      </div>

      <p className="mt-3.5 max-w-[66ch] text-[12.5px] text-chalk-faint">
        Ticks below the line are where the detector{" "}
        <b className="font-semibold text-chalk-dim">looked</b> —{" "}
        <span className="tnum">{windows.length}</span> windows,{" "}
        <span className="tnum">{timecode(reviewed)}</span> of{" "}
        <span className="tnum">{timecode(duration)}</span>. Marks above it are what a human{" "}
        <b className="font-semibold text-chalk-dim">kept</b>. The struck-through marks are the
        machine being wrong out loud — nothing reaches a reel without a person behind it.
      </p>
    </section>
  );
}

function Key({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <i className={`inline-block size-2 rounded-[1px] ${swatch}`} />
      {label}
    </span>
  );
}
