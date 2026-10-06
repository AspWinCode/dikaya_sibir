import { describe, expect, it } from "vitest";
import type { RecordRead } from "@/shared/api/records";
import { applyPivotFilter } from "./RuntimeApp";

function rec(id: string, payload: Record<string, unknown>): RecordRead {
  return {
    id, entity_id: "e", payload, version: 1, is_deleted: false,
    deleted_at: null, deleted_by: null, created_by: null, updated_by: null,
    created_at: "", updated_at: "",
  } as RecordRead;
}

const records: RecordRead[] = [
  rec("1", { room: "A", qty: 10 }),
  rec("2", { room: "B", qty: 5 }),
  rec("3", { room: "A", qty: 20 }),
];

describe("applyPivotFilter (report builder's Фильтр condition)", () => {
  it("returns every record when no field/value is set — the report shows all data by default", () => {
    expect(applyPivotFilter(records, "", "eq", "")).toHaveLength(3);
    expect(applyPivotFilter(records, "room", "eq", "")).toHaveLength(3);
  });

  it("eq filters to exact string match", () => {
    expect(applyPivotFilter(records, "room", "eq", "A").map((r) => r.id)).toEqual(["1", "3"]);
  });

  it("ne excludes the matching value", () => {
    expect(applyPivotFilter(records, "room", "ne", "A").map((r) => r.id)).toEqual(["2"]);
  });

  it("numeric comparisons (gt/gte/lt/lte) compare as numbers, not strings", () => {
    expect(applyPivotFilter(records, "qty", "gt", "9").map((r) => r.id)).toEqual(["1", "3"]);
    expect(applyPivotFilter(records, "qty", "gte", "10").map((r) => r.id)).toEqual(["1", "3"]);
    expect(applyPivotFilter(records, "qty", "lt", "10").map((r) => r.id)).toEqual(["2"]);
    expect(applyPivotFilter(records, "qty", "lte", "5").map((r) => r.id)).toEqual(["2"]);
  });

  it("icontains is a case-insensitive substring match", () => {
    expect(applyPivotFilter(records, "room", "icontains", "a").map((r) => r.id)).toEqual(["1", "3"]);
  });

  it("a missing field value only matches 'ne', never 'eq'", () => {
    const withMissing = [...records, rec("4", { qty: 1 })];
    expect(applyPivotFilter(withMissing, "room", "eq", "A").map((r) => r.id)).not.toContain("4");
    expect(applyPivotFilter(withMissing, "room", "ne", "A").map((r) => r.id)).toContain("4");
  });
});
