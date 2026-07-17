import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TimelineView } from "../src/components/Timeline";
import type { MomentEvent, Timeline } from "../src/lib/api";

type ElementProps = Record<string, unknown> & { children?: ReactNode };

function findElement(
  node: ReactNode,
  predicate: (element: ReactElement<ElementProps>) => boolean,
): ReactElement<ElementProps> {
  if (isValidElement<ElementProps>(node)) {
    if (predicate(node)) return node;
    for (const child of Children.toArray(node.props.children)) {
      try {
        return findElement(child, predicate);
      } catch {
        // Keep searching sibling branches.
      }
    }
  }
  throw new Error("Element not found");
}

function event(id: string, clip: string | null, tStart: number): MomentEvent {
  return {
    id,
    from_proposal: `proposal-${id}`,
    t_start: tStart,
    t_end: tStart + 8,
    type: "save",
    caption: `${id} caption`,
    clip,
    team: null,
    player: null,
  };
}

function timeline(events: MomentEvent[]): Timeline {
  return { duration: 120, windows: [], events, rejected: [] };
}

function expectNoNestedButtons(markup: string): void {
  let buttonDepth = 0;
  for (const [tag] of markup.matchAll(/<\/?button\b[^>]*>/g)) {
    if (tag.startsWith("</")) {
      buttonDepth -= 1;
    } else {
      expect(buttonDepth).toBe(0);
      buttonDepth += 1;
    }
  }
  expect(buttonDepth).toBe(0);
}

describe("match timeline clips", () => {
  it("opens a clip bar in the shared modal with its match-scoped media URL", () => {
    const playable = event("playable", "clips/save.mp4", 42);
    const onPlay = vi.fn();
    const onSeek = vi.fn();
    const closed = TimelineView({
      matchId: "match-test",
      data: timeline([playable]),
      playing: null,
      onPlay,
      onClose: () => {},
      onSeek,
    });
    const bar = findElement(
      closed,
      (element) => element.props["aria-label"] === "Play save clip at 0:42",
    );

    (bar.props.onClick as () => void)();

    expect(onPlay).toHaveBeenCalledWith(playable);
    expect(onSeek).toHaveBeenCalledWith(42);

    const openMarkup = renderToStaticMarkup(
      <TimelineView
        matchId="match-test"
        data={timeline([playable])}
        playing={playable}
        onPlay={() => {}}
        onClose={() => {}}
      />,
    );
    expect(openMarkup).toContain('role="dialog"');
    expect(openMarkup).toContain('src="/media/match-test/clips/save.mp4"');
    expectNoNestedButtons(openMarkup);
  });

  it("leaves a timeline mark without a clip inert", () => {
    const markup = renderToStaticMarkup(
      <TimelineView
        matchId="match-test"
        data={timeline([event("clipless", null, 20)])}
        playing={null}
        onPlay={() => {}}
        onClose={() => {}}
      />,
    );

    expect(markup).toContain('title="clipless caption"');
    expect(markup).not.toContain("<button");
    expect(markup).not.toContain('role="dialog"');
  });
});
