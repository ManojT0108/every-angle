import type { MomentEvent } from "./api";

function unique(ids: readonly string[]): string[] {
  return [...new Set(ids)];
}

export function replaceSelection(incoming: readonly string[]): string[] {
  return unique(incoming);
}

export function mergeSelection(
  selected: string[],
  incoming: readonly string[],
): string[] {
  const merged = unique([...selected, ...incoming]);
  if (merged.length === selected.length && merged.every((id, index) => id === selected[index])) {
    return selected;
  }
  return merged;
}

export function reconcileSelection(
  selected: string[],
  events: readonly Pick<MomentEvent, "id">[],
): string[] {
  const available = new Set(events.map((event) => event.id));
  const reconciled = unique(selected).filter((id) => available.has(id));
  if (
    reconciled.length === selected.length &&
    reconciled.every((id, index) => id === selected[index])
  ) {
    return selected;
  }
  return reconciled;
}
