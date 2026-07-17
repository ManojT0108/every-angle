import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { api, timecode } from "./lib/api";
import { Timeline } from "./components/Timeline";
import { MatchSummary } from "./components/MatchSummary";
import { Button, Empty, ErrorNote } from "./components/bits";
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

const WORKFLOW = [
  {
    number: "01",
    label: "Signal scan",
    detail: "Motion, audio, and scene cues narrow the footage.",
  },
  {
    number: "02",
    label: "AI proposes",
    detail: "Claude describes only the candidate windows it can see.",
  },
  {
    number: "03",
    label: "Human reviews",
    detail: "An editor keeps, rejects, or corrects every notable moment.",
  },
  {
    number: "04",
    label: "Moments ship",
    detail: "Verified clips become searchable and ready for a reel.",
  },
] as const;

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

  const openWorkspace = (nextTab: Tab) => {
    setTab(nextTab);
    requestAnimationFrame(() => {
      document.getElementById("workspace")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
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

  return (
    <Shell {...shellProps} duration={tl.duration}>
      <ProductIntro onNavigate={openWorkspace} />

      <MatchSummary data={tl} />

      <Timeline matchId={matchId} data={tl} />

      <nav
        id="workspace"
        className="mt-9 grid scroll-mt-4 grid-cols-3 border-b border-line"
        role="tablist"
        aria-label="Moment workspace"
      >
        {(["verify", "search", "reel"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`display min-w-0 cursor-pointer border-b-2 px-2 pb-2 pt-2.5 text-[13px] transition-colors sm:px-5 sm:text-[15px] ${
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

function ProductIntro({ onNavigate }: { onNavigate: (tab: Tab) => void }) {
  return (
    <section
      aria-labelledby="product-outcome"
      className="hero-atmosphere relative mt-6 overflow-hidden border border-line bg-ink-800"
    >
      <div className="relative z-10 grid gap-8 px-5 py-8 sm:px-7 md:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)] md:px-9 md:py-10">
        <div className="min-w-0 self-center">
          <span className="eyebrow text-sodium">Grounded football intelligence</span>
          <h2
            id="product-outcome"
            className="display mt-3 max-w-[13ch] text-[clamp(2.4rem,6vw,4.9rem)] leading-[0.9] tracking-[0.025em]"
          >
            Find the moments. Prove every one.
          </h2>
          <p className="mt-5 max-w-[58ch] text-[14px] leading-relaxed text-chalk-dim sm:text-[15px]">
            Every Angle turns full-match footage into playable, searchable clips — with
            a human decision between every AI proposal and the final edit.
          </p>
          <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <WorkspaceLink primary onClick={() => onNavigate("search")}>
              Search verified moments
            </WorkspaceLink>
            <WorkspaceLink onClick={() => onNavigate("verify")}>
              Review proposals
            </WorkspaceLink>
            <WorkspaceLink onClick={() => onNavigate("reel")}>
              Assemble a reel
            </WorkspaceLink>
          </div>
        </div>

        <ol className="grid content-center gap-px border border-line bg-line sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
          {WORKFLOW.map((step) => (
            <li key={step.number} className="min-w-0 bg-ink-900/95 p-4">
              <div className="flex items-baseline justify-between gap-3">
                <span className="display text-[13px] text-chalk">{step.label}</span>
                <span className="tnum font-mono text-[10px] text-sodium">
                  {step.number}
                </span>
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-chalk-faint">
                {step.detail}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function WorkspaceLink({
  children,
  onClick,
  primary = false,
}: {
  children: ReactNode;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-h-10 cursor-pointer border px-4 py-2 text-left font-mono text-[10px] uppercase tracking-[0.1em] transition-colors sm:text-center ${
        primary
          ? "border-sodium bg-sodium text-sodium-ink hover:brightness-110"
          : "border-line bg-ink-900/80 text-chalk-dim hover:border-chalk-faint hover:text-chalk"
      }`}
    >
      {children}
    </button>
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
    <div className="mx-auto max-w-[1180px] px-4 pb-20 pt-5 sm:px-6 sm:pb-24 sm:pt-7">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-4 sm:gap-6">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
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
