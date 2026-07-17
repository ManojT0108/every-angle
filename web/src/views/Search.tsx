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

const GOLDEN = [
  "keeper beaten at close range",
  "goalkeeper comes off his line",
  "fast counter down the middle",
  "attack down the left that breaks down",
];

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
        className="flex border border-line bg-ink-800 focus-within:border-sodium"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search verified moments"
          placeholder="Describe the moment you want…"
          className="flex-1 bg-transparent px-4 py-3.5 text-[16px] outline-none placeholder:text-chalk-faint"
        />
        <button
          type="submit"
          className="display cursor-pointer bg-sodium px-6 text-[13px] text-sodium-ink hover:brightness-110"
        >
          Search
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        {GOLDEN.map((g) => (
          <button
            key={g}
            onClick={() => {
              setQ(g);
              setSubmitted(g);
            }}
            className="cursor-pointer border border-dashed border-line px-2.5 py-1.5 font-mono text-[10.5px] text-chalk-faint transition-colors hover:border-chalk-faint hover:text-chalk"
          >
            {g}
          </button>
        ))}
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
    <article className="flex items-center gap-4 bg-ink-800 p-4 transition-colors hover:bg-ink-700">
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
      <div className="flex shrink-0 items-center gap-4">
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
