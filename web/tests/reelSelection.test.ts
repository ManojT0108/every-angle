import { describe, expect, it } from "vitest";
import {
  mergeSelection,
  reconcileSelection,
  replaceSelection,
} from "../src/lib/reelSelection";

describe("reel selection", () => {
  it("replaces, merges in order without duplicates, and reconciles removals", () => {
    expect(replaceSelection(["new", "new", "last"])).toEqual(["new", "last"]);
    expect(mergeSelection(["first", "second"], ["second", "third"])).toEqual([
      "first",
      "second",
      "third",
    ]);
    expect(
      reconcileSelection(["first", "rejected", "third"], [
        { id: "first" },
        { id: "third" },
      ]),
    ).toEqual(["first", "third"]);
  });
});
