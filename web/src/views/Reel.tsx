import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, isHumanAdded, timecode, type MomentEvent } from "../lib/api";
import { Button, Empty, ErrorNote } from "../components/bits";
import { pickHighlights } from "../lib/highlights";

/**
 * Reel — deterministic assembly.
 *
 * FFmpeg concat over pre-encoded clips. No model call, no network dependency on
 * a provider: the reel cannot fail live. That is a product decision, not a
 * technical shortcut.
 */
export function Reel({
  matchId,
  events,
  selected,
  setSelected,
  onApplySelection,
}: {
  matchId: string;
  events: MomentEvent[];
  selected: string[];
  setSelected: (ids: string[]) => void;
  onApplySelection: (ids: string[]) => void;
}) {
  const chosen = selected
    .map((id) => events.find((event) => event.id === id))
    .filter((event): event is MomentEvent => Boolean(event));
  const orderedIds = chosen.map((event) => event.id);

  const build = useMutation({
    mutationFn: () => api.reel(matchId, orderedIds),
  });
  const resetBuild = build.reset;

  useEffect(() => {
    resetBuild();
  }, [selected, resetBuild]);

  const runtime = chosen.reduce((a, e) => a + (e.t_end - e.t_start), 0);
  const goals = chosen.filter((e) => e.type === "goal").length;

  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0">
        <div className="relative aspect-video border border-line bg-ink-900">
          {build.data ? (
            <video
              key={build.data.url}
              src={build.data.url}
              controls
              autoPlay
              className="size-full"
            />
          ) : (
            <div className="pitch-bg absolute inset-0 flex items-center justify-center opacity-90">
              <p className="max-w-[36ch] text-center text-[13px] text-chalk">
                {chosen.length === 0
                  ? "Add moments from Search, or keep them in Review."
                  : `${chosen.length} moment${chosen.length > 1 ? "s" : ""} ready. Build the reel.`}
              </p>
            </div>
          )}
        </div>

        {chosen.length > 0 && (
          <div className="timeline-scroll mt-px flex gap-px overflow-x-auto border border-line bg-line">
            {chosen.map((e) => (
              <div
                key={e.id}
                className={`min-w-24 flex-1 border-t-2 bg-ink-800 px-2.5 py-2 ${
                  isHumanAdded(e) ? "border-t-chalk" : "border-t-sodium"
                }`}
              >
                <b className="block font-mono text-[11px] text-chalk">
                  {e.type === "goal" ? "GOAL" : "BREAK"}
                </b>
                <span className="tnum font-mono text-[10px] text-chalk-faint">
                  {timecode(e.t_start)} · {Math.round(e.t_end - e.t_start)}s
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <aside>
        <h3 className="display mb-3 text-[13px] text-chalk-dim">Reel</h3>
        <Row label="Moments" value={String(chosen.length)} />
        <Row label="Runtime" value={timecode(runtime)} />
        <Row label="Goals" value={String(goals)} />
        <Row
          label="Human-verified"
          value={`${chosen.length} / ${chosen.length}`}
        />

        <Button
          tone="primary"
          disabled={events.length === 0}
          onClick={() => onApplySelection(pickHighlights(events))}
        >
          Quick Highlights
        </Button>

        {chosen.length > 0 && (
          <ol className="mt-4 space-y-1 border-y border-line py-2">
            {chosen.map((event, index) => (
              <li key={event.id} className="bg-ink-800 px-2 py-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0 truncate text-[12px] text-chalk-dim">
                    {event.caption}
                  </span>
                  <span className="tnum shrink-0 font-mono text-[10px] text-chalk-faint">
                    {timecode(event.t_start)}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  <Button
                    disabled={index === 0}
                    onClick={() => setSelected(move(orderedIds, index, -1))}
                  >
                    Up
                  </Button>
                  <Button
                    disabled={index === chosen.length - 1}
                    onClick={() => setSelected(move(orderedIds, index, 1))}
                  >
                    Down
                  </Button>
                  <Button
                    tone="drop"
                    onClick={() => setSelected(orderedIds.filter((id) => id !== event.id))}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            ))}
          </ol>
        )}

        <div className="mt-4 space-y-2">
          <Button
            tone="primary"
            disabled={chosen.length === 0 || build.isPending}
            onClick={() => build.mutate()}
          >
            {build.isPending ? "Cutting…" : "Build reel"}
          </Button>
          {chosen.length > 0 && (
            <Button onClick={() => setSelected([])}>Clear</Button>
          )}
        </div>

        {build.error && (
          <div className="mt-3">
            <ErrorNote>Could not build the reel — {(build.error as Error).message}</ErrorNote>
          </div>
        )}

        {build.data && (
          <a
            href={build.data.url}
            download
            className="mt-3 block border border-line px-3 py-2 text-center font-mono text-[10px] uppercase tracking-[0.1em] text-chalk-dim hover:border-chalk-faint hover:text-chalk"
          >
            Download
          </a>
        )}

        <p className="mt-4 text-[12.5px] text-chalk-faint">
          Cut deterministically with FFmpeg from pre-encoded clips — no model call on this path,
          so it cannot fail live.
        </p>
      </aside>

      {events.length === 0 && (
        <div className="lg:col-span-2">
          <Empty>No verified moments yet. Keep some in Review first.</Empty>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-line-soft py-2 text-[13px]">
      <span className="text-chalk-dim">{label}</span>
      <span className="tnum font-mono">{value}</span>
    </div>
  );
}

function move(ids: string[], index: number, offset: -1 | 1): string[] {
  const target = index + offset;
  if (target < 0 || target >= ids.length) return ids;
  const reordered = [...ids];
  [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
  return reordered;
}
