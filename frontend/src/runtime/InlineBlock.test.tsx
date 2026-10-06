import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { EntityRead, FieldRead, RelationRead } from "@/shared/api/entities";
import type { RecordRead } from "@/shared/api/records";
import { InlineBlock } from "./RuntimeApp";

const API = "/api/v1";
const APP_ID = "app-1";

function field(partial: Partial<FieldRead> & Pick<FieldRead, "id" | "name" | "display_name" | "field_type">): FieldRead {
  return {
    entity_id: "e", app_id: APP_ID, is_required: false, is_system: false,
    is_unique: false, display_order: 0, field_options: {}, formula_definition: null,
    ...partial,
  } as FieldRead;
}

function relationFixture(partial: Partial<RelationRead> & Pick<RelationRead, "id" | "from_entity_id" | "to_entity_id" | "relation_type" | "from_field_name" | "display_name">): RelationRead {
  return { app_id: APP_ID, to_field_name: null, settings: {}, created_at: "", ...partial } as RelationRead;
}

function record(partial: Partial<RecordRead> & Pick<RecordRead, "id" | "entity_id" | "payload">): RecordRead {
  return {
    version: 1, is_deleted: false, deleted_at: null, deleted_by: null,
    created_by: null, updated_by: null, created_at: "", updated_at: "",
    ...partial,
  } as RecordRead;
}

const productsEntity: EntityRead = {
  id: "ent-products", app_id: APP_ID, slug: "products", display_name: "Продукция",
  name_plural: "Продукция", description: null, icon: null, color: null,
  fields: [field({ id: "pf1", name: "title", display_name: "Название", field_type: "text" })],
} as EntityRead;

const receiptsEntity: EntityRead = {
  id: "ent-receipts", app_id: APP_ID, slug: "receipts", display_name: "Поступления",
  name_plural: "Поступления", description: null, icon: null, color: null,
  fields: [
    field({ id: "rf1", name: "parent_id", display_name: "Родитель", field_type: "relation" }),
    field({ id: "rf2", name: "qty", display_name: "Количество", field_type: "number" }),
    field({
      id: "rf3", name: "product_id", display_name: "Продукция", field_type: "relation",
      field_options: { target_entity_id: "ent-products" },
    }),
  ],
} as EntityRead;

const relation: RelationRead = relationFixture({
  id: "rel-1", from_entity_id: receiptsEntity.id, to_entity_id: "ent-parent",
  relation_type: "one_to_many", from_field_name: "parent_id", display_name: "Поступления родителя",
});

let receiptRecords: RecordRead[] = [];
const productRecords: RecordRead[] = [
  record({ id: "prod-1", entity_id: productsEntity.id, payload: { title: "Доска дубовая" } }),
];

const server = setupServer(
  http.get(`${API}/apps/:appId/entities/:entityId/records`, ({ params }) => {
    const items = params.entityId === receiptsEntity.id ? receiptRecords : productRecords;
    return HttpResponse.json({ items, next_cursor: null, has_more: false, total: items.length });
  }),
  http.get(`${API}/apps/:appId/entities/:entityId/records/:recordId`, ({ params }) => {
    const pool = params.entityId === receiptsEntity.id ? receiptRecords : productRecords;
    const rec = pool.find((r) => r.id === params.recordId);
    return rec ? HttpResponse.json(rec) : HttpResponse.json({ detail: "Not found" }, { status: 404 });
  }),
  http.patch(`${API}/apps/:appId/entities/:entityId/records/:recordId`, async ({ params, request }) => {
    const body = (await request.json()) as { payload: Record<string, unknown> };
    const idx = receiptRecords.findIndex((r) => r.id === params.recordId);
    receiptRecords[idx] = { ...receiptRecords[idx], payload: { ...receiptRecords[idx].payload, ...body.payload } };
    return HttpResponse.json(receiptRecords[idx]);
  }),
  http.delete(`${API}/apps/:appId/entities/:entityId/records/:recordId`, ({ params }) => {
    receiptRecords = receiptRecords.filter((r) => r.id !== params.recordId);
    return new HttpResponse(null, { status: 204 });
  })
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderInline() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const colors = { bg: "#fff", surface: "#fff", border: "#ddd", text: "#000", textMuted: "#666" };
  return render(
    <QueryClientProvider client={qc}>
      <InlineBlock
        appId={APP_ID}
        entity={receiptsEntity}
        relation={relation}
        parentRecordId="parent-1"
        inlineTitle="Поступления"
        accent="#00205F"
        colors={colors as never}
        entities={[receiptsEntity, productsEntity]}
        relations={[relation]}
      />
    </QueryClientProvider>
  );
}

describe("InlineBlock (secondary/related table on a detail page)", () => {
  afterEach(() => {
    receiptRecords = [];
  });

  it("resolves a relation field to the related record's display name, not a raw id", async () => {
    receiptRecords = [
      record({ id: "rec-1", entity_id: receiptsEntity.id, payload: { qty: 5, product_id: "prod-1" } }),
    ];
    renderInline();

    expect(await screen.findByText("Доска дубовая")).toBeInTheDocument();
    expect(screen.queryByText("prod-1")).not.toBeInTheDocument();
  });

  it("lets the user edit a row and save it through the real update API", async () => {
    receiptRecords = [
      record({ id: "rec-1", entity_id: receiptsEntity.id, payload: { qty: 5, product_id: "prod-1" } }),
    ];
    const user = userEvent.setup();
    renderInline();

    await screen.findByText("Доска дубовая");
    await user.click(screen.getByTitle("Редактировать"));

    const qtyInput = screen.getByDisplayValue("5");
    await user.clear(qtyInput);
    await user.type(qtyInput, "12");
    await user.click(screen.getByText("✓"));

    await waitFor(() => expect(receiptRecords[0].payload.qty).toBe(12));
  });

  it("lets the user delete a row with confirmation, and the list refreshes", async () => {
    receiptRecords = [
      record({ id: "rec-1", entity_id: receiptsEntity.id, payload: { qty: 5, product_id: "prod-1" } }),
    ];
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderInline();

    await screen.findByText("Доска дубовая");
    await user.click(screen.getByTitle("Удалить"));

    await waitFor(() => expect(screen.getByText("Нет связанных записей")).toBeInTheDocument());
    expect(receiptRecords).toHaveLength(0);
  });
});
