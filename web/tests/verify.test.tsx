import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { api, type Proposal } from "../src/lib/api";
import { invalidateReviewQueries, judgedProposals } from "../src/lib/verify";
import { ProposalEditForm, ProposalMedia } from "../src/views/Verify";

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: "proposal-1",
    t_start: 10,
    t_end: 16,
    type: "goal",
    confidence: "high",
    caption: "A shot finds the net",
    status: "pending",
    clip: null,
    frames: ["/media/match/frames/wide-1.jpg"],
    ...overrides,
  };
}

describe("Review proposal media", () => {
  it("renders a compact clip launcher instead of inline controls when available", () => {
    const markup = renderToStaticMarkup(
      <ProposalMedia p={proposal({ clip: "/media/match/clips/proposal.mp4" })} />,
    );

    expect(markup).toContain("<video");
    expect(markup).toContain('preload="metadata"');
    expect(markup).toContain('src="/media/match/clips/proposal.mp4"');
    expect(markup).toContain('aria-label="Play clip at 0:10"');
    expect(markup).not.toContain('controls=""');
    expect(markup).not.toContain("Evidence frame");
  });

  it("falls back to evidence stills when no clip is available", () => {
    const markup = renderToStaticMarkup(<ProposalMedia p={proposal()} />);

    expect(markup).not.toContain("<video");
    expect(markup).toContain('src="/media/match/frames/wide-1.jpg"');
    expect(markup).toContain('alt="Evidence frame 1"');
  });

  it("excludes ordinary-play proposals from the judged list", () => {
    const notable = proposal({ id: "notable", status: "accepted" });
    const ordinaryPlay = proposal({
      id: "ordinary-play",
      type: "none",
      status: "rejected",
    });

    expect(judgedProposals([ordinaryPlay, notable])).toEqual([notable]);
  });

  it("posts edited values and invalidates every Review consumer", async () => {
    const form = renderToStaticMarkup(
      <ProposalEditForm
        caption="Corrected caption"
        type="save"
        busy={false}
        onCaptionChange={() => {}}
        onTypeChange={() => {}}
        onSave={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(form).toContain("<textarea");
    expect(form).toContain('<option value="none">none</option>');
    expect(form).toContain("Save");
    expect(form).toContain("Cancel");

    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        proposal_id: "proposal-1",
        status: "accepted",
        event_id: "e-001",
      }),
    });
    vi.stubGlobal("fetch", fetch);

    await api.editProposal("match-test", "proposal/1", {
      caption: "Corrected caption",
      type: "save",
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/matches/match-test/proposals/proposal%2F1/edit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ caption: "Corrected caption", type: "save" }),
      }),
    );

    const invalidateQueries = vi.fn().mockResolvedValue(undefined);
    invalidateReviewQueries({ invalidateQueries }, "match-test");

    expect(invalidateQueries.mock.calls.map(([filters]) => filters.queryKey)).toEqual([
      ["proposals", "match-test"],
      ["timeline", "match-test"],
      ["search", "match-test"],
    ]);
    vi.unstubAllGlobals();
  });
});
