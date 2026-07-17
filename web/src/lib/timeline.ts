import { timecode, type MomentEvent } from "./api";

export const TIMELINE_ZOOM_LEVELS = [12, 20, 32, 48, 64] as const;
export const DEFAULT_TIMELINE_ZOOM = 32;
export const TIMELINE_CANVAS_PADDING = 76;

const EVENT_LANE_GAP = 4;

export interface PositionedEvent {
  event: MomentEvent;
  hitboxWidth: number;
  lane: number;
  x: number;
}

export function timelineEventLabel(event: MomentEvent): string {
  const type = event.type[0].toUpperCase() + event.type.slice(1);
  return `${type} ${timecode(event.t_start)}`;
}

function eventHitboxWidth(event: MomentEvent): number {
  return Math.max(72, Math.min(144, timelineEventLabel(event).length * 6 + 16));
}

/** Deterministic greedy lane placement over each event's rendered hitbox. */
export function positionTimelineEvents(
  events: MomentEvent[],
  pixelsPerMinute: number,
): PositionedEvent[] {
  const laneEnds: number[] = [];
  return [...events]
    .sort((a, b) => a.t_start - b.t_start || a.id.localeCompare(b.id))
    .map((event) => {
      const hitboxWidth = eventHitboxWidth(event);
      const x =
        TIMELINE_CANVAS_PADDING +
        (Math.max(0, event.t_start) / 60) * pixelsPerMinute;
      const start = x - hitboxWidth / 2;
      const end = x + hitboxWidth / 2;
      let lane = laneEnds.findIndex(
        (laneEnd) => start >= laneEnd + EVENT_LANE_GAP,
      );
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(end);
      } else {
        laneEnds[lane] = end;
      }
      return { event, hitboxWidth, lane, x };
    });
}

function tickInterval(pixelsPerMinute: number): number {
  const minuteSteps = [1, 2, 5, 10, 15, 30, 60];
  return (minuteSteps.find((minutes) => minutes * pixelsPerMinute >= 80) ?? 120) * 60;
}

export function timelineTicks(duration: number, pixelsPerMinute: number): number[] {
  if (duration <= 0) return [0];
  const interval = tickInterval(pixelsPerMinute);
  const ticks = Array.from(
    { length: Math.floor(duration / interval) + 1 },
    (_, index) => index * interval,
  );
  if (ticks.at(-1) !== duration) ticks.push(duration);
  return ticks;
}
