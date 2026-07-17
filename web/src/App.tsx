import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { api, timecode } from "./lib/api";
import { Timeline } from "./components/Timeline";
import { Button, Empty, ErrorNote, Figure, Figures } from "./components/bits";
import { Verify } from "./views/Verify";
import { Search } from "./views/Search";
import { Reel } from "./views/Reel";
import {
  mergeSelection,
  reconcileSelection,
  replaceSelection,
} from "./lib/reelSelection";

type Tab = "verify" | "search" | "reel";
const TAB_LABELS: Record<Tab, string> = {
  verify: "Review",
  search: "Search",
  reel: "Reel",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("search");
  const [reel, setReel] = useState<string[]>([]);
  const [pendingSelection, setPendingSelection] = useState<string[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  const { data: matches, error: matchErr } = useQuery({
    queryKey: ["matches"],
    queryFn: api.matches,
  });
  const matchId = picked ?? matches?.[0]?.video_id;

  const { data: tl } = useQuery({
    queryKey: ["timeline", matchId],
    queryFn: () => api.timeline(matchId as string),
    enabled: Boolean(matchId),
  });
  const { data: proposals } = useQuery({
    queryKey: ["proposals", matchId],
    queryFn: () => api.proposals(matchId as string),
    enabled: Boolean(matchId),
  });

  useEffect(() => {
    if (!tl) return;
    setReel((current) => reconcileSelection(current, tl.events));
    setPendingSelection((current) =>
      current ? reconcileSelection(current, tl.events) : null,
    );
  }, [tl]);

  const reconciledReel = tl ? reconcileSelection(reel, tl.events) : reel;

  const applySelection = (ids: string[]) => {
    const incoming = reconcileSelection(replaceSelection(ids), tl?.events ?? []);
    if (reconciledReel.length === 0) {
      setReel(incoming);
    } else {
      setPendingSelection(incoming);
    }
  };

  const resolveSelection = (mode: "replace" | "merge") => {
    if (!pendingSelection) return;
    const incoming = reconcileSelection(pendingSelection, tl?.events ?? []);
    setReel((current) => {
      const reconciled = reconcileSelection(current, tl?.events ?? []);
      return mode === "replace"
        ? replaceSelection(incoming)
        : mergeSelection(reconciled, incoming);
    });
    setPendingSelection(null);
  };

  const shellProps = {
    matches: matches ?? [],
    matchId,
    onPick: (id: string) => {
      setPicked(id);
      setReel([]);
      setPendingSelection(null);
    },
  };

  if (matchErr)
    return (
      <Shell {...shellProps}>
        <ErrorNote>
          Could not reach the API — is the backend running on :8000?
          <br />
          <span className="font-mono text-[12px]">{(matchErr as Error).message}</span>
        </ErrorNote>
      </Shell>
    );

  if (!matchId || !tl)
    return (
      <Shell {...shellProps}>
        <Empty>Loading match…</Empty>
      </Shell>
    );

  // The proposal-derived figures degrade gracefully if /proposals is slow or
  // errors — the app (Timeline/Search/Reel) must never stall on them, and the
  // tiles show "—" (not a misleading 0) until the data actually arrives.
  const reviewed = tl.windows.reduce((a, w) => a + (w.t_end - w.t_start), 0);
  const proposalsReady = proposals !== undefined;
  const notableProposals = (proposals ?? []).filter((proposal) => proposal.type !== "none");
  const awaitingReview = notableProposals.filter(
    (proposal) => proposal.status === "pending",
  ).length;

  return (
    <Shell {...shellProps} duration={tl.duration}>
      <Figures>
        <Figure
          label="Footage to review"
          value={timecode(reviewed)}
          unit={`of ${timecode(tl.duration)}`}
          hero
        />
        <Figure label="AI proposals" value={proposalsReady ? notableProposals.length : "—"} />
        <Figure label="Verified clips" value={tl.events.length} />
        <Figure label="Awaiting review" value={proposalsReady ? awaitingReview : "—"} />
      </Figures>

      <Timeline matchId={matchId} data={tl} />

      <nav className="mt-9 flex border-b border-line" role="tablist">
        {(["verify", "search", "reel"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`display cursor-pointer border-b-2 px-5 pb-2 pt-2.5 text-[15px] transition-colors ${
              tab === t
                ? "border-b-sodium text-chalk"
                : "border-b-transparent text-chalk-faint hover:text-chalk-dim"
            }`}
          >
            {TAB_LABELS[t]}
            {t === "reel" && reconciledReel.length > 0 && (
              <span className="tnum ml-2 bg-sodium px-1.5 text-[11px] text-sodium-ink">
                {reconciledReel.length}
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="pt-6">
        {tab === "verify" && <Verify matchId={matchId} />}
        {tab === "search" && (
          <Search
            matchId={matchId}
            events={tl.events}
            inReel={new Set(reconciledReel)}
            onApplySelection={applySelection}
          />
        )}
        {tab === "reel" && (
          <Reel
            matchId={matchId}
            events={tl.events}
            selected={reconciledReel}
            setSelected={setReel}
            onApplySelection={applySelection}
          />
        )}
      </div>

      {pendingSelection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-6">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="selection-prompt-title"
            className="w-full max-w-md border border-line bg-ink-800 p-5"
          >
            <h2 id="selection-prompt-title" className="display text-[17px]">
              Update reel selection
            </h2>
            <p className="mt-2 text-[13px] text-chalk-dim">
              Replace the current reel with this selection, or merge in new moments while
              preserving the current order?
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button tone="primary" onClick={() => resolveSelection("replace")}>
                Replace
              </Button>
              <Button onClick={() => resolveSelection("merge")}>Merge</Button>
              <Button onClick={() => setPendingSelection(null)}>Cancel</Button>
            </div>
          </section>
        </div>
      )}
    </Shell>
  );
}

// Attribution is per-source and must be honest: SoccerTrack is CC BY and
// shippable; a broadcast is copyrighted and local-only. Getting this wrong is
// not a cosmetic bug.
const SOURCES: Record<string, { label: string; license: string }> = {
  "match-001": { label: "SoccerTrack v2", license: "CC BY 4.0" },
};
function sourceOf(id: string) {
  return SOURCES[id] ?? { label: "Uploaded footage", license: "local only" };
}

function Shell({
  children,
  matches,
  matchId,
  duration,
  onPick,
}: {
  children: ReactNode;
  matches?: { video_id: string; duration: number }[];
  matchId?: string;
  duration?: number;
  onPick?: (id: string) => void;
}) {
  const src = matchId ? sourceOf(matchId) : null;
  return (
    <div className="mx-auto max-w-[1180px] px-6 pb-24 pt-7">
      <header className="flex flex-wrap items-end justify-between gap-6 border-b border-line pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="display m-0 text-[30px] leading-none">Every&nbsp;Angle</h1>
          <span className="eyebrow">Moment intelligence</span>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {matches && matches.length > 1 && onPick && (
            <div className="flex border border-line">
              {matches.map((m) => (
                <button
                  key={m.video_id}
                  onClick={() => onPick(m.video_id)}
                  aria-pressed={m.video_id === matchId}
                  className={`px-3 py-1.5 font-mono text-[11px] tracking-wide transition-colors ${
                    m.video_id === matchId
                      ? "bg-sodium text-sodium-ink"
                      : "text-chalk-dim hover:text-chalk"
                  }`}
                >
                  {sourceOf(m.video_id).label}
                </button>
              ))}
            </div>
          )}
          {matchId && src && (
            <div className="tnum font-mono text-[11px] tracking-wide text-chalk-dim">
              {duration ? `${timecode(duration)} · ` : ""}
              <b className="font-semibold text-chalk">{src.label}</b> {src.license}
            </div>
          )}
        </div>
      </header>

      <main>{children}</main>

      <footer className="mt-11 flex flex-wrap justify-between gap-4 border-t border-line pt-4 font-mono text-[10.5px] tracking-wide text-chalk-faint">
        <span>
          {matchId ? `${sourceOf(matchId).label} · ${sourceOf(matchId).license}` : ""}
        </span>
        <span>Qdrant · Claude vision · FFmpeg</span>
      </footer>
    </div>
  );
}
