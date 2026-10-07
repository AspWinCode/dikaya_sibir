import { describe, expect, it } from "vitest";
import type { FieldRead } from "@/shared/api/entities";
import type { RelationRead } from "@/shared/api/entities";
import type { RecordRead } from "@/shared/api/records";
import { rangeCheckInfo } from "./RuntimeApp";

function field(name: string, overrides: Partial<FieldRead> = {}): FieldRead {
  return {
    id: name, entity_id: "e1", app_id: "a1", name, display_name: name,
    field_type: "decimal", is_required: false, is_unique: false, is_system: false,
    is_indexed: false, is_sensitive: false, default_value: null,
    validation_rules: {}, field_options: {}, formula_definition: null,
    ...overrides,
  } as FieldRead;
}

function relation(overrides: Partial<RelationRead> = {}): RelationRead {
  return {
    id: "r1", app_id: "a1", from_entity_id: "e1", to_entity_id: "e2",
    relation_type: "one_to_many", from_field_name: "pomeschenie", to_field_name: null,
    display_name: null, settings: {}, created_at: "",
    ...overrides,
  };
}

function rec(payload: Record<string, unknown>): RecordRead {
  return {
    id: "rec1", entity_id: "e1", payload, version: 1, is_deleted: false,
    deleted_at: null, deleted_by: null, created_by: null, updated_by: null,
    created_at: "", updated_at: "",
  } as RecordRead;
}

describe("rangeCheckInfo (ТЗ 15.3 — temperature deviation badge)", () => {
  const relField = field("pomeschenie", { field_type: "relation" });
  const temperaturaField = field("temperatura", {
    field_options: {
      range_check: { relation_field: "pomeschenie", min_field: "min_temperature", max_field: "max_temperature" },
    },
  });

  it("returns null when the field has no range_check config", () => {
    expect(rangeCheckInfo(field("plain"), rec({}), "e1", [relField], [])).toBeNull();
  });

  it("returns null when the named relation field doesn't exist on the entity", () => {
    expect(rangeCheckInfo(temperaturaField, rec({}), "e1", [temperaturaField], [])).toBeNull();
  });

  it("resolves the related entity/record and bound min/max field names", () => {
    const rooms = relation({ from_entity_id: "e1", to_entity_id: "e2", from_field_name: "pomeschenie" });
    const result = rangeCheckInfo(
      temperaturaField,
      rec({ pomeschenie: "room-7" }),
      "e1",
      [relField, temperaturaField],
      [rooms],
    );
    expect(result).toEqual({
      relatedEntityId: "e2",
      relatedRecordId: "room-7",
      minField: "min_temperature",
      maxField: "max_temperature",
    });
  });

  it("falls back to an empty related record id when the relation field is unset on the record", () => {
    const rooms = relation({ from_entity_id: "e1", to_entity_id: "e2", from_field_name: "pomeschenie" });
    const result = rangeCheckInfo(temperaturaField, rec({}), "e1", [relField, temperaturaField], [rooms]);
    expect(result?.relatedRecordId).toBe("");
  });
});
