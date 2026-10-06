import { describe, expect, it } from "vitest";
import { parseStaticOptions, groupRecordsByField, buildRecordTree, computeRangeStatus } from "./blockHelpers";

describe("computeRangeStatus (e.g. температура помещения vs его min/max)", () => {
  it("is 'ok' within [min, max] inclusive, 'below'/'above' outside it", () => {
    expect(computeRangeStatus(5, 2, 8)).toBe("ok");
    expect(computeRangeStatus(2, 2, 8)).toBe("ok");
    expect(computeRangeStatus(8, 2, 8)).toBe("ok");
    expect(computeRangeStatus(1, 2, 8)).toBe("below");
    expect(computeRangeStatus(9, 2, 8)).toBe("above");
  });

  it("is 'unknown' when the value is missing — never a false 'ok'", () => {
    expect(computeRangeStatus(null, 2, 8)).toBe("unknown");
    expect(computeRangeStatus(undefined, 2, 8)).toBe("unknown");
    expect(computeRangeStatus(NaN, 2, 8)).toBe("unknown");
  });

  it("is 'unknown' when neither bound is configured on the room — nothing to check against", () => {
    expect(computeRangeStatus(5, null, null)).toBe("unknown");
  });

  it("checks against a single bound when only one side is configured", () => {
    expect(computeRangeStatus(10, 2, null)).toBe("ok");
    expect(computeRangeStatus(1, 2, null)).toBe("below");
    expect(computeRangeStatus(5, null, 8)).toBe("ok");
    expect(computeRangeStatus(9, null, 8)).toBe("above");
  });
});

describe("parseStaticOptions", () => {
  it("splits on newlines and trims", () => {
    expect(parseStaticOptions("Вариант 1\n Вариант 2 \n\nВариант 3")).toEqual([
      "Вариант 1", "Вариант 2", "Вариант 3",
    ]);
  });

  it("returns empty array for empty/undefined input", () => {
    expect(parseStaticOptions("")).toEqual([]);
    expect(parseStaticOptions(undefined)).toEqual([]);
    expect(parseStaticOptions(null)).toEqual([]);
  });

  it("drops blank lines", () => {
    expect(parseStaticOptions("a\n\n\nb")).toEqual(["a", "b"]);
  });
});

describe("groupRecordsByField", () => {
  const rec = (id: string, status?: string) => ({ id, payload: { status } });

  it("groups records by field value, preserving first-seen order", () => {
    const records = [rec("1", "new"), rec("2", "done"), rec("3", "new"), rec("4", "done")];
    const groups = groupRecordsByField(records, "status");
    expect(groups.map((g) => g.key)).toEqual(["new", "done"]);
    expect(groups[0].items.map((r) => r.id)).toEqual(["1", "3"]);
    expect(groups[1].items.map((r) => r.id)).toEqual(["2", "4"]);
  });

  it("buckets missing/empty values under the empty label", () => {
    const records = [rec("1", "new"), rec("2", undefined), rec("3", "")];
    const groups = groupRecordsByField(records, "status", "Без категории");
    const empty = groups.find((g) => g.key === "Без категории");
    expect(empty?.items.map((r) => r.id)).toEqual(["2", "3"]);
  });

  it("returns no groups for an empty record list", () => {
    expect(groupRecordsByField([], "status")).toEqual([]);
  });
});

describe("buildRecordTree", () => {
  const rec = (id: string, parent?: string) => ({ id, payload: { parent } });

  it("nests children under their parent", () => {
    const records = [rec("a"), rec("b", "a"), rec("c", "a"), rec("d", "b")];
    const tree = buildRecordTree(records, "parent");
    expect(tree).toHaveLength(1);
    expect(tree[0].record.id).toBe("a");
    expect(tree[0].children.map((n) => n.record.id).sort()).toEqual(["b", "c"]);
    const nodeB = tree[0].children.find((n) => n.record.id === "b")!;
    expect(nodeB.children.map((n) => n.record.id)).toEqual(["d"]);
  });

  it("treats records with no resolvable parent as roots", () => {
    const records = [rec("a"), rec("b", "missing-id"), rec("c", "")];
    const tree = buildRecordTree(records, "parent");
    expect(tree.map((n) => n.record.id).sort()).toEqual(["a", "b", "c"]);
  });

  it("does not infinite-loop on a cycle, and does not duplicate the cyclic record", () => {
    // a -> b -> a (cycle). Neither can be root since each has a resolvable parent,
    // but the tree must still terminate and never place a node under itself twice.
    const records = [rec("a", "b"), rec("b", "a")];
    const tree = buildRecordTree(records, "parent");
    // With everyone claiming a resolvable parent, there are no roots — nothing renders,
    // which is the safe outcome for a cyclic graph (better than infinite recursion).
    expect(tree).toEqual([]);
  });

  it("a record does not become its own parent", () => {
    const records = [rec("a", "a")];
    const tree = buildRecordTree(records, "parent");
    expect(tree).toHaveLength(1);
    expect(tree[0].children).toEqual([]);
  });
});
