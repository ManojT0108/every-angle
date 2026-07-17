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
import { positionTimelineEvents } from "../src/lib/timeline";

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

  it("puts clustered playable moments in separate selectable lanes", () => {
    const clustered = [
      event("save-one", "clips/one.mp4", 42),
      event("save-two", "clips/two.mp4", 43),
      event("save-three", "clips/three.mp4", 44),
    ];
    const positioned = positionTimelineEvents(clustered, 32);

    expect(new Set(positioned.map(({ lane }) => lane)).size).toBe(3);
    expect(positioned.every(({ hitboxWidth }) => hitboxWidth >= 24)).toBe(true);

    const markup = renderToStaticMarkup(
      <TimelineView
        matchId="match-test"
        data={timeline(clustered)}
        playing={null}
        onPlay={() => {}}
        onClose={() => {}}
        pixelsPerMinute={32}
      />,
    );
    expect(markup.match(/aria-label="Play save clip/g)).toHaveLength(3);
    expect(markup).toContain('data-event-lane="2"');
  });

  it("renders a wider time canvas as the zoom level increases", () => {
    const renderAt = (pixelsPerMinute: number) =>
      renderToStaticMarkup(
        <TimelineView
          matchId="match-test"
          data={{ ...timeline([]), duration: 600 }}
          playing={null}
          onPlay={() => {}}
          onClose={() => {}}
          pixelsPerMinute={pixelsPerMinute}
          onZoomIn={() => {}}
          onZoomOut={() => {}}
        />,
      );

    const compact = renderAt(20);
    const expanded = renderAt(64);
    expect(compact).toContain('data-pixels-per-minute="20"');
    expect(compact).toContain("width:352px");
    expect(expanded).toContain('data-pixels-per-minute="64"');
    expect(expanded).toContain("width:792px");
    expect(expanded).toContain('aria-label="Zoom timeline in"');
    expect(expanded).toContain('aria-label="Scrollable match timeline"');
    expect(expanded).toContain("Human-added");
    expect(expanded).toContain("AI-proposed");
  });
});
