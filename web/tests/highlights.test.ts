import { describe, expect, it } from "vitest";
import type { EventType, MomentEvent } from "../src/lib/api";
import { pickHighlights } from "../src/lib/highlights";

function event(
  id: string,
  type: EventType,
  tStart: number,
  tEnd = tStart + 5,
): MomentEvent {
  return {
    id,
    type,
    t_start: tStart,
    t_end: tEnd,
    caption: id,
    clip: `clips/${id}.mp4`,
    from_proposal: `proposal-${id}`,
    team: null,
    player: null,
  };
}

describe("pickHighlights", () => {
  it("returns an empty selection for an empty timeline", () => {
    expect(pickHighlights([])).toEqual([]);
  });

  it("deduplicates chained replay windows into one incident", () => {
    const events = [
      event("goal-live", "goal", 10, 20),
      event("goal-replay-1", "goal", 30, 40),
      event("goal-replay-2", "goal", 51, 60),
      event("later-save", "save", 80, 85),
    ];

    expect(pickHighlights(events)).toEqual(["goal-live", "later-save"]);
  });

  it("keeps the raw latest celebration as the terminal clip", () => {
    const events = [
      event("late-celebration", "celebration", 200, 210),
      event("goal", "goal", 195, 205),
      event("early-celebration", "celebration", 40, 45),
    ];

    expect(pickHighlights(events)).toEqual(["goal", "late-celebration"]);
  });

  it("honors the six-minute budget without a hard clip cap", () => {
    const events = [
      ...Array.from({ length: 40 }, (_, index) =>
        event(`play-${index}`, "goal", index * 30, index * 30 + 10),
      ),
      event("celebration", "celebration", 1_300, 1_310),
    ];
    const selected = pickHighlights(events);
    const byId = new Map(events.map((item) => [item.id, item]));
    const runtime = selected.reduce((total, id) => {
      const item = byId.get(id);
      return total + (item ? item.t_end - item.t_start : 0);
    }, 0);

    expect(selected.length).toBeGreaterThan(8);
    expect(runtime).toBe(360);
    expect(selected.at(-1)).toBe("celebration");
  });

  it("returns chosen plays chronologically after ranking them", () => {
    const events = [
      event("goal", "goal", 100),
      event("card", "card", 10),
      event("save", "save", 50),
    ];

    expect(pickHighlights(events)).toEqual(["card", "save", "goal"]);
  });
});
