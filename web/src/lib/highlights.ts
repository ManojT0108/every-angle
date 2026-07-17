import type { EventType, MomentEvent } from "./api";

const INCIDENT_GAP = 12;
const MAX_SECONDS = 360;

const TYPE_RANK: Record<EventType, number> = {
  goal: 0,
  penalty: 1,
  save: 2,
  counterattack: 3,
  card: 4,
  celebration: 5,
};

function duration(event: MomentEvent): number {
  return Math.max(0, event.t_end - event.t_start);
}

function chronological(a: MomentEvent, b: MomentEvent): number {
  if (a.t_start !== b.t_start) return a.t_start - b.t_start;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

function byPriority(a: MomentEvent, b: MomentEvent): number {
  return TYPE_RANK[a.type] - TYPE_RANK[b.type] || chronological(a, b);
}

/** Pick a deterministic reel within the six-minute runtime budget. */
export function pickHighlights(events: MomentEvent[]): string[] {
  const celebrations = events.filter((event) => event.type === "celebration");
  const plays = events.filter((event) => event.type !== "celebration").sort(chronological);
  const latestCelebration = celebrations.sort(chronological).at(-1);

  // An oversized source clip cannot be included without breaking the absolute cap.
  const terminal =
    latestCelebration && duration(latestCelebration) <= MAX_SECONDS
      ? latestCelebration
      : undefined;
  let secondsRemaining = MAX_SECONDS - (terminal ? duration(terminal) : 0);

  const incidents: { representative: MomentEvent; end: number }[] = [];
  for (const event of plays) {
    const incident = incidents.at(-1);
    if (!incident || event.t_start > incident.end + INCIDENT_GAP) {
      incidents.push({ representative: event, end: event.t_end });
      continue;
    }

    incident.end = Math.max(incident.end, event.t_end);
    if (byPriority(event, incident.representative) < 0) {
      incident.representative = event;
    }
  }

  const selected: MomentEvent[] = [];
  for (const { representative } of incidents.sort((a, b) =>
    byPriority(a.representative, b.representative),
  )) {
    const clipDuration = duration(representative);
    if (clipDuration > secondsRemaining) continue;
    selected.push(representative);
    secondsRemaining -= clipDuration;
  }

  selected.sort(chronological);
  if (terminal) selected.push(terminal);
  return selected.map((event) => event.id);
}
