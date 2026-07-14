import { useMutation, useQuery } from "@tanstack/react-query";
import { api, isHumanAdded, timecode, type MomentEvent } from "../lib/api";
import { Button, Empty, ErrorNote } from "../components/bits";

/**
 * Reel — deterministic assembly.
 *
 * FFmpeg concat over pre-encoded clips. No model call, no network dependency on
 * a provider: the reel cannot fail live. That is a product decision, not a
 * technical shortcut.
 */
export function Reel({
  matchId,
  selected,
  setSelected,
}: {
  matchId: string;
  selected: string[];
  setSelected: (ids: string[]) => void;
}) {
  const { data: tl } = useQuery({
    queryKey: ["timeline", matchId],
    queryFn: () => api.timeline(matchId),
  });

  const build = useMutation({
    mutationFn: () => api.reel(matchId, selected),
  });

  const events = tl?.events ?? [];
  const chosen = selected
    .map((id) => events.find((e) => e.id === id))
    .filter((e): e is MomentEvent => Boolean(e));
  const runtime = chosen.reduce((a, e) => a + (e.t_end - e.t_start), 0);
  const goals = chosen.filter((e) => e.type === "goal").length;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div>
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
                  ? "Add moments from Search, or keep them in Verify."
                  : `${chosen.length} moment${chosen.length > 1 ? "s" : ""} ready. Build the reel.`}
              </p>
            </div>
          )}
        </div>

        {chosen.length > 0 && (
          <div className="mt-px flex gap-px border border-line bg-line">
            {chosen.map((e) => (
              <div
                key={e.id}
                className={`flex-1 border-t-2 bg-ink-800 px-2.5 py-2 ${
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
          <Empty>No verified moments yet. Keep some in Verify first.</Empty>
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
