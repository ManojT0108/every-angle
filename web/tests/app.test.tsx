import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "../src/App";
import type { Proposal, Timeline } from "../src/lib/api";

function proposal(
  id: string,
  type: Proposal["type"],
  status: Proposal["status"],
): Proposal {
  return {
    id,
    t_start: 10,
    t_end: 20,
    type,
    confidence: "high",
    caption: id,
    status,
    clip: null,
    frames: [],
  };
}

describe("homepage stats", () => {
  it("derives all four figures from the timeline and latest proposals", () => {
    const matchId = "match-stats";
    const timeline: Timeline = {
      duration: 732,
      windows: [
        {
          id: "w-1",
          t_start: 10,
          t_end: 70,
          audio_peak: false,
          scene_cut: false,
          motion_peak: true,
          score: 1,
        },
        {
          id: "w-2",
          t_start: 100,
          t_end: 250,
          audio_peak: true,
          scene_cut: false,
          motion_peak: false,
          score: 1,
        },
      ],
      events: [
        {
          id: "e-1",
          from_proposal: "p-accepted",
          t_start: 20,
          t_end: 30,
          type: "goal",
          caption: "First verified clip",
          clip: "clips/e-1.mp4",
          team: null,
          player: null,
        },
        {
          id: "e-2",
          from_proposal: null,
          t_start: 300,
          t_end: 310,
          type: "save",
          caption: "Second verified clip",
          clip: null,
          team: null,
          player: null,
        },
      ],
      rejected: [],
    };
    const proposals = [
      proposal("p-pending", "goal", "pending"),
      proposal("p-accepted", "save", "accepted"),
      proposal("p-rejected", "card", "rejected"),
      proposal("p-ordinary", "none", "pending"),
    ];
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
    queryClient.setQueryData(["proposals", matchId], proposals);

    const markup = renderToStaticMarkup(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(markup).toMatch(
      /Footage to review<\/div><div[^>]*>3:30<small[^>]*>of 12:12<\/small>/,
    );
    expect(markup).toMatch(/AI proposals<\/div><div[^>]*>3<\/div>/);
    expect(markup).toMatch(/Verified clips<\/div><div[^>]*>2<\/div>/);
    expect(markup).toMatch(/Awaiting review<\/div><div[^>]*>1<\/div>/);
    expect(markup).not.toContain("Candidate windows");
    expect(markup).not.toContain("Goals kept");
    expect(markup).not.toContain("Rejected by human");
  });
});
