import { describe, expect, it } from "vitest";
import type { MomentEvent } from "../src/lib/api";
import { goalIncidents } from "../src/lib/matchSummary";

function goal(
  id: string,
  start: number,
  end: number,
  team: string | null,
  player: string | null,
): MomentEvent {
  return {
    id,
    from_proposal: `proposal-${id}`,
    t_start: start,
    t_end: end,
    type: "goal",
    caption: id,
    clip: `clips/${id}.mp4`,
    team,
    player,
  };
}

describe("goalIncidents", () => {
  it("groups replay-adjacent moments and suppresses conflicting identity labels", () => {
    const incidents = goalIncidents([
      goal("live", 10, 20, "RMA", "Alex Striker"),
      goal("replay", 25, 35, "Real Madrid", "Alex Striker"),
      goal("later", 100, 110, null, null),
    ]);

    expect(incidents).toEqual([
      { id: "live", time: 10, team: null, player: "Alex Striker" },
      { id: "later", time: 100, team: null, player: null },
    ]);
  });
});
