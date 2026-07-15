import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, timecode } from "./lib/api";
import { Timeline } from "./components/Timeline";
import { Empty, ErrorNote, Figure, Figures } from "./components/bits";
import { Verify } from "./views/Verify";
import { Search } from "./views/Search";
import { Reel } from "./views/Reel";

type Tab = "verify" | "search" | "reel";

export default function App() {
  const [tab, setTab] = useState<Tab>("search");
  const [reel, setReel] = useState<string[]>([]);
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

  const shellProps = {
    matches: matches ?? [],
    matchId,
    onPick: (id: string) => {
      setPicked(id);
      setReel([]);
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

  const reviewed = tl.windows.reduce((a, w) => a + (w.t_end - w.t_start), 0);
  const goals = tl.events.filter((e) => e.type === "goal").length;

  return (
    <Shell {...shellProps} duration={tl.duration}>
      <Figures>
        <Figure
          label="Footage to review"
          value={timecode(reviewed)}
          unit={`of ${timecode(tl.duration)}`}
          hero
        />
        <Figure label="Candidate windows" value={tl.windows.length} />
        <Figure label="Goals kept" value={goals} />
        <Figure label="Rejected by human" value={tl.rejected.length} />
        <Figure label="Verified moments" value={tl.events.length} />
      </Figures>

      <Timeline data={tl} />

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
            {t}
            {t === "reel" && reel.length > 0 && (
              <span className="tnum ml-2 bg-sodium px-1.5 text-[11px] text-sodium-ink">
                {reel.length}
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
            inReel={new Set(reel)}
            onAdd={(id) => setReel((r) => (r.includes(id) ? r : [...r, id]))}
          />
        )}
        {tab === "reel" && <Reel matchId={matchId} selected={reel} setSelected={setReel} />}
      </div>
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
