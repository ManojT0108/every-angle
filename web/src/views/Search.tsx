import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, isHumanAdded, mediaUrl, timecode, type SearchHit } from "../lib/api";
import { Button, ClipThumb, Empty, ErrorNote, Provenance, TypeChip } from "../components/bits";

const GOLDEN = [
  "keeper beaten at close range",
  "goalkeeper comes off his line",
  "fast counter down the middle",
  "attack down the left that breaks down",
];

/**
 * Search — the hero.
 *
 * Runs over VERIFIED captions only, never raw model output. The score shown is
 * the real cosine similarity from Qdrant; we don't dress it up. The only
 * inference on this path is a local embedding of the query, so it cannot fail
 * on a network blip during a live demo.
 */
export function Search({
  matchId,
  onAdd,
  inReel,
}: {
  matchId: string;
  onAdd: (id: string) => void;
  inReel: Set<string>;
}) {
  const [q, setQ] = useState("keeper beaten at close range");
  const [submitted, setSubmitted] = useState("keeper beaten at close range");

  const { data, isFetching, error } = useQuery({
    queryKey: ["search", matchId, submitted],
    queryFn: () => api.search(matchId, submitted),
    enabled: submitted.trim().length > 0,
  });

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
      </div>

      {error && (
        <ErrorNote>
          {(error as { status?: number }).status === 503
            ? "The search index is unreachable. Qdrant may not be running."
            : `Search failed — ${(error as Error).message}`}
        </ErrorNote>
      )}

      {isFetching && <Empty>Searching…</Empty>}

      {!isFetching && data && data.length === 0 && (
        <Empty>Nothing verified matches that yet.</Empty>
      )}

      {!isFetching && data && data.length > 0 && (
        <div className="grid gap-px border border-line bg-line">
          {data.map((hit) => (
            <Hit
              key={hit.id}
              hit={hit}
              matchId={matchId}
              onAdd={onAdd}
              added={inReel.has(hit.id)}
            />
          ))}
        </div>
      )}

      <p className="max-w-[66ch] text-[12.5px] text-chalk-faint">
        Search runs over <b className="font-semibold text-chalk-dim">verified captions only</b> —
        never raw model output. Scores are cosine similarity from Qdrant against the published
        revision.
      </p>
    </div>
  );
}

function Hit({
  hit,
  matchId,
  onAdd,
  added,
}: {
  hit: SearchHit;
  matchId: string;
  onAdd: (id: string) => void;
  added: boolean;
}) {
  return (
    <article className="flex items-center gap-4 bg-ink-800 p-4 transition-colors hover:bg-ink-700">
      <ClipThumb src={mediaUrl(matchId, hit.clip)} t={hit.t_start} />
      <div className="min-w-0 flex-1">
        <p className="mb-2 text-[14px] leading-relaxed">{hit.caption}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          <TypeChip type={hit.type} />
          <Provenance human={isHumanAdded(hit)} />
          <span className="chip tnum">{timecode(hit.t_start)}</span>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-4">
        <span className="tnum font-mono text-[12px] text-sodium">{hit.score.toFixed(3)}</span>
        <Button onClick={() => onAdd(hit.id)} disabled={added}>
          {added ? "In reel" : "Add to reel"}
        </Button>
      </div>
    </article>
  );
}
