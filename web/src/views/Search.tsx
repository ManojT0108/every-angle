import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  isHumanAdded,
  mediaUrl,
  timecode,
  type MomentEvent,
  type SearchHit,
} from "../lib/api";
import { Button, ClipThumb, Empty, ErrorNote, Provenance, TypeChip } from "../components/bits";
import { pickHighlights } from "../lib/highlights";

/**
 * Search — the hero.
 *
 * Browse mode reads the verified manifest directly in match order. A submitted
 * query switches to relevance-ranked Qdrant results over the same events.
 */
export function Search({
  matchId,
  events,
  onApplySelection,
  inReel,
}: {
  matchId: string;
  events: MomentEvent[];
  onApplySelection: (ids: string[]) => void;
  inReel: Set<string>;
}) {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const browsing = submitted.trim().length === 0;

  const { data, isFetching, error } = useQuery({
    queryKey: ["search", matchId, submitted],
    queryFn: () => api.search(matchId, submitted),
    enabled: !browsing,
  });
  const rows: MomentEvent[] = browsing ? chronologicalEvents(events) : (data ?? []);

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(q);
        }}
        className="flex min-w-0 border border-line bg-ink-800 focus-within:border-sodium"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search verified moments"
          placeholder="Describe the moment you want…"
          className="min-w-0 flex-1 bg-transparent px-3 py-3.5 text-[15px] outline-none placeholder:text-chalk-faint sm:px-4 sm:text-[16px]"
        />
        <button
          type="submit"
          className="display min-h-12 shrink-0 cursor-pointer bg-sodium px-4 text-[12px] text-sodium-ink hover:brightness-110 sm:px-6 sm:text-[13px]"
        >
          Search
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        <Button
          tone="primary"
          disabled={events.length === 0}
          onClick={() => onApplySelection(pickHighlights(events))}
        >
          Quick Highlights
        </Button>
      </div>

      {error && (
        <ErrorNote>
          {(error as { status?: number }).status === 503
            ? "The search index is unreachable. Qdrant may not be running."
            : `Search failed — ${(error as Error).message}`}
        </ErrorNote>
      )}

      {!browsing && isFetching && <Empty>Searching…</Empty>}

      {!error && !isFetching && rows.length === 0 && (
        <Empty>
          {browsing ? "No verified moments yet." : "Nothing verified matches that yet."}
        </Empty>
      )}

      {!isFetching && rows.length > 0 && (
        <div className="grid gap-px border border-line bg-line">
          {rows.map((hit) => (
            <Hit
              key={hit.id}
              hit={hit}
              matchId={matchId}
              onAdd={(id) => onApplySelection([id])}
              added={inReel.has(hit.id)}
              score={browsing ? undefined : (hit as SearchHit).score}
            />
          ))}
        </div>
      )}

      <p className="max-w-[66ch] text-[12.5px] text-chalk-faint">
        {browsing ? (
          <>
            Browse shows every{" "}
            <b className="font-semibold text-chalk-dim">verified moment</b> in match order.
          </>
        ) : (
          <>
            Search runs over{" "}
            <b className="font-semibold text-chalk-dim">verified captions only</b> — never raw
            model output. Scores are cosine similarity from Qdrant against the published
            revision.
          </>
        )}
      </p>
    </div>
  );
}

function Hit({
  hit,
  matchId,
  onAdd,
  added,
  score,
}: {
  hit: MomentEvent;
  matchId: string;
  onAdd: (id: string) => void;
  added: boolean;
  score?: number;
}) {
  return (
    <article className="flex min-w-0 flex-col items-start gap-4 bg-ink-800 p-4 transition-colors hover:bg-ink-700 sm:flex-row sm:items-center">
      <ClipThumb
        src={hit.clip ? mediaUrl(matchId, hit.clip) : undefined}
        t={hit.t_start}
      />
      <div className="min-w-0 flex-1">
        <p className="mb-2 text-[14px] leading-relaxed">{hit.caption}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          <TypeChip type={hit.type} />
          <Provenance human={isHumanAdded(hit)} />
          <span className="chip tnum">{timecode(hit.t_start)}</span>
        </div>
      </div>
      <div className="flex w-full shrink-0 items-center justify-between gap-4 sm:w-auto sm:justify-start">
        {score !== undefined && (
          <span className="tnum font-mono text-[12px] text-sodium">{score.toFixed(3)}</span>
        )}
        <Button onClick={() => onAdd(hit.id)} disabled={added}>
          {added ? "In reel" : "Add to reel"}
        </Button>
      </div>
    </article>
  );
}

function chronologicalEvents(events: MomentEvent[]): MomentEvent[] {
  return [...events].sort(
    (a, b) => a.t_start - b.t_start || a.id.localeCompare(b.id),
  );
}
