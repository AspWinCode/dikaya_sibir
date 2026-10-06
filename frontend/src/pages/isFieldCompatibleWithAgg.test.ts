import { describe, expect, it } from "vitest";
import { isFieldCompatibleWithAgg } from "./ViewEditorPage";

describe("isFieldCompatibleWithAgg (report builder: Показатель × Способ расчёта)", () => {
  it("Количество (count) accepts any field type — it just counts rows", () => {
    expect(isFieldCompatibleWithAgg("text", "count")).toBe(true);
    expect(isFieldCompatibleWithAgg("select", "count")).toBe(true);
    expect(isFieldCompatibleWithAgg("relation", "count")).toBe(true);
    expect(isFieldCompatibleWithAgg("number", "count")).toBe(true);
  });

  it.each(["sum", "avg", "min", "max"])(
    "%s accepts numeric-ish field types (number/decimal/currency/formula)",
    (agg) => {
      expect(isFieldCompatibleWithAgg("number", agg)).toBe(true);
      expect(isFieldCompatibleWithAgg("decimal", agg)).toBe(true);
      expect(isFieldCompatibleWithAgg("currency", agg)).toBe(true);
      expect(isFieldCompatibleWithAgg("formula", agg)).toBe(true);
    }
  );

  it.each(["sum", "avg", "min", "max"])(
    "%s rejects non-numeric field types — this is the 'SUM(text field)' case the acceptance criteria calls out",
    (agg) => {
      expect(isFieldCompatibleWithAgg("text", agg)).toBe(false);
      expect(isFieldCompatibleWithAgg("select", agg)).toBe(false);
      expect(isFieldCompatibleWithAgg("relation", agg)).toBe(false);
      expect(isFieldCompatibleWithAgg("boolean", agg)).toBe(false);
    }
  );
});
