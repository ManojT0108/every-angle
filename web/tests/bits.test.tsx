import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ClipModalView, ClipThumbPlayer } from "../src/components/bits";

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

describe("ClipThumb player", () => {
  it("opens the modal player and closes it from the backdrop or close button", () => {
    const onOpen = vi.fn();
    const onClose = vi.fn();
    const closed = ClipThumbPlayer({
      src: "/media/match/clips/goal.mp4",
      t: 42,
      open: false,
      onOpen,
      onClose,
    });
    const play = findElement(
      closed,
      (element) => element.props["aria-label"] === "Play clip at 0:42",
    );

    (play.props.onClick as () => void)();

    expect(onOpen).toHaveBeenCalledOnce();
    expect(renderToStaticMarkup(closed)).not.toContain('role="dialog"');

    const open = ClipThumbPlayer({
      src: "/media/match/clips/goal.mp4",
      t: 42,
      open: true,
      onOpen,
      onClose,
    });
    const markup = renderToStaticMarkup(open);
    const modal = ClipModalView({
      src: "/media/match/clips/goal.mp4",
      t: 42,
      onClose,
    });
    const backdrop = findElement(modal, (element) => element.props.role === "dialog");
    const close = findElement(
      modal,
      (element) => element.props["aria-label"] === "Close clip",
    );

    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('controls=""');
    expect(markup).toContain('autoPlay=""');

    (backdrop.props.onClick as () => void)();
    (close.props.onClick as () => void)();

    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
