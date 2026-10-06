/** Pure, unit-testable helpers extracted from RuntimeApp block rendering. */

export type RangeStatus = "ok" | "below" | "above" | "unknown";

/**
 * Compares a measured value against an optional [min, max] range — e.g. a
 * "Температурный контроль" reading against its Помещение's configured
 * min/max temperature. Generic: works for any numeric field checked
 * against any two optional bounds, not specific to temperature.
 *
 * Both bounds are optional independently (a room might only have a max,
 * or neither, in which case the status is "unknown" rather than a
 * confident but meaningless "ok" — don't claim a reading is fine when
 * there was nothing to check it against).
 */
export function computeRangeStatus(
  value: number | null | undefined,
  min: number | null | undefined,
  max: number | null | undefined,
): RangeStatus {
  if (value === null || value === undefined || isNaN(value)) return "unknown";
  if (min === null || min === undefined) {
    if (max === null || max === undefined) return "unknown";
    return value > max ? "above" : "ok";
  }
  if (max === null || max === undefined) {
    return value < min ? "below" : "ok";
  }
  if (value < min) return "below";
  if (value > max) return "above";
  return "ok";
}

/** Parses a newline-separated static option list into trimmed, non-empty option strings. */
export function parseStaticOptions(raw: string | undefined | null): string[] {
  if (!raw) return [];
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export interface RecordLike {
  id: string;
  payload: Record<string, unknown>;
}

/** Groups records by the string value of a field, preserving first-seen group order. Missing/empty values go under `emptyLabel`. */
export function groupRecordsByField<T extends RecordLike>(
  records: T[],
  field: string,
  emptyLabel = "Без категории",
): { key: string; items: T[] }[] {
  const order: string[] = [];
  const buckets = new Map<string, T[]>();
  for (const rec of records) {
    const raw = rec.payload[field];
    const key = raw === null || raw === undefined || raw === "" ? emptyLabel : String(raw);
    if (!buckets.has(key)) {
      buckets.set(key, []);
      order.push(key);
    }
    buckets.get(key)!.push(rec);
  }
  return order.map((key) => ({ key, items: buckets.get(key)! }));
}

export interface TreeNode<T extends RecordLike> {
  record: T;
  children: TreeNode<T>[];
}

/**
 * Builds a parent/child tree from a flat record list using `parentField` as the
 * self-referencing FK. Records whose parent id doesn't resolve to another record
 * in the list (including an empty/missing parent) become roots. Guards against
 * cycles: a record already placed in the tree is never placed again.
 */
export function buildRecordTree<T extends RecordLike>(records: T[], parentField: string): TreeNode<T>[] {
  const byId = new Map<string, T>(records.map((r) => [r.id, r]));
  const childrenOf = new Map<string, T[]>();
  const roots: T[] = [];

  for (const rec of records) {
    const parentRaw = rec.payload[parentField];
    const parentId = parentRaw === null || parentRaw === undefined || parentRaw === "" ? null : String(parentRaw);
    if (parentId && byId.has(parentId) && parentId !== rec.id) {
      if (!childrenOf.has(parentId)) childrenOf.set(parentId, []);
      childrenOf.get(parentId)!.push(rec);
    } else {
      roots.push(rec);
    }
  }

  function build(rec: T, seen: Set<string>): TreeNode<T> {
    const nextSeen = new Set(seen);
    nextSeen.add(rec.id);
    const kids = (childrenOf.get(rec.id) ?? []).filter((c) => !seen.has(c.id));
    return { record: rec, children: kids.map((c) => build(c, nextSeen)) };
  }

  return roots.map((r) => build(r, new Set()));
}
