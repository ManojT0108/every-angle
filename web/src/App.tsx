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

  const { data: matches, error: matchErr } = useQuery({
    queryKey: ["matches"],
    queryFn: api.matches,
  });
  const matchId = matches?.[0]?.video_id;

  const { data: tl } = useQuery({
    queryKey: ["timeline", matchId],
    queryFn: () => api.timeline(matchId as string),
    enabled: Boolean(matchId),
  });

  if (matchErr)
    return (
      <Shell>
        <ErrorNote>
          Could not reach the API — is the backend running on :8000?
          <br />
          <span className="font-mono text-[12px]">{(matchErr as Error).message}</span>
        </ErrorNote>
      </Shell>
    );

  if (!matchId || !tl)
    return (
      <Shell>
        <Empty>Loading match…</Empty>
      </Shell>
    );

  const reviewed = tl.windows.reduce((a, w) => a + (w.t_end - w.t_start), 0);
  const goals = tl.events.filter((e) => e.type === "goal").length;

  return (
    <Shell matchId={matchId} duration={tl.duration}>
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

function Shell({
  children,
  matchId,
  duration,
}: {
  children: ReactNode;
  matchId?: string;
  duration?: number;
}) {
  return (
    <div className="mx-auto max-w-[1180px] px-6 pb-24 pt-7">
      <header className="flex flex-wrap items-end justify-between gap-6 border-b border-line pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="display m-0 text-[30px] leading-none">Every&nbsp;Angle</h1>
          <span className="eyebrow">Moment intelligence</span>
        </div>
        {matchId && (
          <div className="tnum font-mono text-[11px] tracking-wide text-chalk-dim">
            MATCH <b className="font-semibold text-chalk">{matchId}</b>
            {duration ? ` · ${timecode(duration)}` : ""} ·{" "}
            <b className="font-semibold text-chalk">SoccerTrack v2</b> CC BY 4.0
          </div>
        )}
      </header>

      <main>{children}</main>

      <footer className="mt-11 flex flex-wrap justify-between gap-4 border-t border-line pt-4 font-mono text-[10.5px] tracking-wide text-chalk-faint">
        <span>Match footage: SoccerTrack v2 © Atom Scott et al. · CC BY 4.0 · edited</span>
        <span>Qdrant · Claude vision · FFmpeg</span>
      </footer>
    </div>
  );
}
