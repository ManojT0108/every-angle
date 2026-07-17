import { timecode, type Timeline } from "../lib/api";
import { goalIncidents, type GoalIncident } from "../lib/matchSummary";

function incidentLabel(incident: GoalIncident): string {
  const at = timecode(incident.time);
  if (incident.player && incident.team) {
    return `${incident.player} · ${incident.team} · ${at}`;
  }
  if (incident.player) return `${incident.player} · ${at}`;
  if (incident.team) return `${incident.team} goal · ${at}`;
  return `Goal · ${at}`;
}

export function MatchSummary({ data }: { data: Timeline }) {
  const incidents = goalIncidents(data.events);
  const groupLabel = `${incidents.length} displayed goal group${
    incidents.length === 1 ? "" : "s"
  }`;

  return (
    <section
      aria-label="Match summary"
      className="mt-6 grid gap-5 border-y border-line bg-ink-800 px-4 py-5 sm:px-5 md:grid-cols-[minmax(210px,0.72fr)_minmax(0,1.45fr)] md:gap-7"
    >
      <div>
        <span className="eyebrow">Verified match moments</span>
        <h2 className="display mt-1 text-[22px]">Match summary</h2>
        <p className="tnum mt-2 font-mono text-[11px] text-chalk-dim">
          {groupLabel} · {timecode(data.duration)} footage
        </p>
        <p className="mt-3 max-w-[42ch] text-[12px] text-chalk-faint">
          Replay-adjacent goal moments are grouped for display.
        </p>
      </div>

      {incidents.length > 0 ? (
        <ol className="grid content-start gap-2 sm:grid-cols-2">
          {incidents.map((incident, index) => (
            <li
              key={incident.id}
              className="border border-line border-l-chalk bg-ink-900 px-4 py-3"
            >
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <span className="eyebrow text-chalk-dim">Verified goal</span>
                <span className="tnum font-mono text-[9px] text-chalk-faint">
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <span className="tnum font-mono text-[13px] text-chalk">
                {incidentLabel(incident)}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="self-center border border-dashed border-line px-4 py-5 text-[13px] text-chalk-faint">
          No verified goal moments.
        </p>
      )}
    </section>
  );
}
