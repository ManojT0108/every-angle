import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { api, type MomentEvent } from "../src/lib/api";
import { Search } from "../src/views/Search";

function event(id: string, tStart: number): MomentEvent & { score: number } {
  return {
    id,
    from_proposal: `proposal-${id}`,
    t_start: tStart,
    t_end: tStart + 5,
    type: "goal",
    caption: id,
    clip: `clips/${id}.mp4`,
    team: null,
    player: null,
    score: 0.999,
  };
}

describe("Search browse mode", () => {
  it("opens without a query and lists all verified events chronologically", () => {
    const search = vi.spyOn(api, "search");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const markup = renderToStaticMarkup(
      <QueryClientProvider client={queryClient}>
        <Search
          matchId="match-test"
          events={[event("late moment", 120), event("early moment", 5)]}
          inReel={new Set()}
          onApplySelection={() => {}}
        />
      </QueryClientProvider>,
    );

    expect(search).not.toHaveBeenCalled();
    expect(markup.indexOf("early moment")).toBeLessThan(
      markup.indexOf("late moment"),
    );
    expect(markup).toContain("0:05");
    expect(markup).toContain("2:00");
    expect(markup).not.toContain("0.999");
    expect(markup).toContain("Browse shows every");
  });
});
