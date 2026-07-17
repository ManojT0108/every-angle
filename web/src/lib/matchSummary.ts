import type { MomentEvent } from "./api";
import { groupIncidents } from "./highlights";

export interface GoalIncident {
  id: string;
  time: number;
  team: string | null;
  player: string | null;
}

function unambiguousValue(
  events: MomentEvent[],
  field: "team" | "player",
): string | null {
  const values = new Set(
    events
      .map((event) => event[field]?.trim())
      .filter((value): value is string => Boolean(value)),
  );
  return values.size === 1 ? [...values][0] : null;
}

/** Derive honest display incidents from verified goal moments. */
export function goalIncidents(events: MomentEvent[]): GoalIncident[] {
  return groupIncidents(events.filter((event) => event.type === "goal"))
    .map((incident) => ({
      id: incident.events[0].id,
      time: Math.min(...incident.events.map((event) => event.t_start)),
      team: unambiguousValue(incident.events, "team"),
      player: unambiguousValue(incident.events, "player"),
    }))
    .sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
}
