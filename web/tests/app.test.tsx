import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "../src/App";
import type { Timeline } from "../src/lib/api";

describe("homepage match summary", () => {
  it("shows grouped goal details from verified events without old pipeline tiles", () => {
    const matchId = "match-summary";
    const timeline: Timeline = {
      duration: 732,
      windows: [],
      events: [
        {
          id: "goal-live",
          from_proposal: "p-goal",
          t_start: 20,
          t_end: 30,
          type: "goal",
          caption: "Goal sequence",
          clip: "clips/goal.mp4",
          team: "Blue FC",
          player: "Alex Striker",
        },
        {
          id: "goal-replay",
          from_proposal: "p-replay",
          t_start: 35,
          t_end: 45,
          type: "goal",
          caption: "Replay of the same goal",
          clip: "clips/replay.mp4",
          team: "Blue FC",
          player: "Alex Striker",
        },
        {
          id: "goal-unknown",
          from_proposal: null,
          t_start: 300,
          t_end: 310,
          type: "goal",
          caption: "Another goal",
          clip: null,
          team: null,
          player: null,
        },
      ],
      rejected: [],
    };
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(["matches"], [
      {
        video_id: matchId,
        duration: timeline.duration,
        current_revision: 1,
        collection: "moments_rev_1",
        event_count: timeline.events.length,
      },
    ]);
    queryClient.setQueryData(["timeline", matchId], timeline);

    const markup = renderToStaticMarkup(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(markup).toContain("Match summary");
    expect(markup).toContain("Find the moments. Prove every one.");
    expect(markup).toContain("Signal scan");
    expect(markup).toContain("AI proposes");
    expect(markup).toContain("Human reviews");
    expect(markup).toContain("Moments ship");
    expect(markup).toContain('aria-label="Moment workspace"');
    expect(markup).toContain("Search verified moments");
    expect(markup).toContain("Review proposals");
    expect(markup).toContain("Assemble a reel");
    expect(markup).toContain("2 displayed goal groups");
    expect(markup).toContain("Alex Striker · Blue FC · 0:20");
    expect(markup).toContain("Goal · 5:00");
    expect(markup).toContain("12:12 footage");
    expect(markup).not.toContain("Footage to review");
    expect(markup).not.toContain("AI proposals");
    expect(markup).not.toContain("Awaiting review");
  });
});
