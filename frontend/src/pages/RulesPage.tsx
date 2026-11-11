import { useState, useEffect } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { IconRail, type RailModule } from "@/components/layout/IconRail";
import { PreviewPanel } from "@/components/layout/PreviewPanel";
import { cn } from "@/lib/cn";
import { useApps } from "@/shared/hooks/useApps";
import { useActiveApp } from "@/shared/hooks/useActiveApp";
import { useEntities, useRelations } from "@/shared/hooks/useEntities";
import { useEntityRules, useCreateRule, useUpdateRule, useDeleteRule, useTestRule, useRuleLogs, useRuleConflicts, useRuleWebhookDeliveries } from "@/shared/hooks/useRules";
import type { EntityRead, FieldRead } from "@/shared/api/entities";
import type { Rule, RuleTrigger, RuleTestResponse, RuleExecutionLogRead, RuleConflictLogRead } from "@/shared/api/rules";

/* <option>s for a field picker. A <select> whose value matches no <option>
   silently DISPLAYS its first option while the stored value stays unchanged,
   so a rule bound to a renamed/removed field (e.g. stale key `nazvanie` after
   the field became «Сумма» / `summa`) looked correctly configured but wrote
   into a field that no longer exists. Surface that case explicitly. */
function fieldOptions(fields: { id: string; name: string; display_name: string }[], current: string) {
  const missing = !!current && fields.length > 0 && !fields.some((f) => f.name === current);
  return (
    <>
      {missing && <option value={current}>{`⚠ Поле не найдено: ${current}`}</option>}
      {fields.map((f) => <option key={f.id} value={f.name}>{f.display_name}</option>)}
    </>
  );
}

function uid() { return Math.random().toString(36).slice(2); }

/* ── Condition / Action row types (UI only) ──
   A condition's compare value can be a plain literal or a "lookup" — reads
   a value from a DIFFERENT entity's records (ТЗ: "проверка достаточности
   материалов по рецепту"). A lookup's filter values are always evaluated
   against the record the rule is validating — even a filter nested inside
   another lookup (chaining) — so `currentEntityFields` is threaded through
   unchanged at every nesting depth; only the lookup's OWN target entity
   changes per level. See backend/app/engine/lookup.py for the executed
   semantics this UI is building. */
interface LookupFilterRow {
  id: string;
  targetFieldName: string;              // field on the lookup's target entity ("id" is the record's own id)
  matchType: "literal" | "field_ref" | "lookup";
  literalValue: string;
  fieldRefField: string;                // field on the CURRENT (validated) entity
  nestedLookup: LookupConfig | null;     // chaining: this filter's value is another lookup's result
}
interface LookupConfig {
  entityId: string;
  filters: LookupFilterRow[];
  resultField: string;                  // field to read/aggregate; unused when agg === "count"
  agg: "value" | "sum" | "count" | "avg" | "min" | "max";
}
function blankLookup(): LookupConfig {
  return { entityId: "", filters: [], resultField: "", agg: "value" };
}
function blankFilterRow(): LookupFilterRow {
  return { id: uid(), targetFieldName: "", matchType: "field_ref", literalValue: "", fieldRefField: "", nestedLookup: null };
}

interface CondRow { id: string; field: string; op: string; valueType: "literal" | "lookup"; value: string; lookup: LookupConfig | null; }
interface ActionRow {
  id: string; type: string; field: string; value: string; message: string; url: string;
  notifyToType: "literal" | "field_ref"; notifyTo: string; notifySubject: string; notifyTemplate: string;
  // update_record only ("Обновить связанную запись" — ТЗ: write an
  // aggregated value from this entity into a record of a DIFFERENT entity
  // reached via a relation field on this one, e.g. "сумма операций по
  // работнику"): `recordIdField` is the relation field (on the entity this
  // rule is attached to) whose value is the target record's real id;
  // `value`/`valueType`/`lookup` describe what to write into `field` on
  // that target record, same three-way choice a condition's value has.
  recordIdField: string;
  valueType: "literal" | "field_ref" | "lookup";
  lookup: LookupConfig | null;
}

const TRIGGER_EVENTS = [
  { value: "record.created",  label: "При создании записи" },
  { value: "record.updated",  label: "При обновлении записи" },
  { value: "record.deleted",  label: "При удалении записи" },
  { value: "field.changed",   label: "При изменении поля" },
  { value: "schedule",        label: "По расписанию" },
];

const SCHEDULE_KINDS = [
  { value: "cron",          label: "По календарю (например, раз в месяц)" },
  { value: "relative_date", label: "Относительно даты в записи (например, за N дней до срока)" },
];

const COMPARE_OPS = [
  { value: "eq",          label: "=" },
  { value: "ne",          label: "≠" },
  { value: "gt",          label: ">" },
  { value: "gte",         label: "≥" },
  { value: "lt",          label: "<" },
  { value: "lte",         label: "≤" },
  { value: "contains",    label: "содержит" },
  { value: "icontains",   label: "содержит (без рег.)" },
  { value: "is_null",     label: "пустое" },
  { value: "is_not_null", label: "не пустое" },
];

const AUTOMATION_ACTION_TYPES = [
  { value: "set_field",          label: "Установить значение поля" },
  { value: "update_record",      label: "Обновить связанную запись" },
  { value: "send_notification",  label: "Отправить уведомление" },
  { value: "call_webhook",       label: "Вызвать Webhook" },
  { value: "stop",               label: "Остановить выполнение правил" },
];
const VALIDATION_ACTION_TYPES = [
  { value: "block_save", label: "Отклонить сохранение" },
];

/* ── Lookup expression ↔ API dict ── */
function buildLookupNode(cfg: LookupConfig): Record<string, unknown> {
  const filter: Record<string, unknown> = {};
  for (const f of cfg.filters) {
    if (!f.targetFieldName) continue;
    if (f.matchType === "field_ref") filter[f.targetFieldName] = { type: "field_ref", field: f.fieldRefField };
    else if (f.matchType === "lookup" && f.nestedLookup) filter[f.targetFieldName] = buildLookupNode(f.nestedLookup);
    else filter[f.targetFieldName] = f.literalValue;
  }
  return {
    type: "lookup",
    entity_id: cfg.entityId,
    filter,
    ...(cfg.agg === "count" ? {} : { field: cfg.resultField }),
    agg: cfg.agg,
  };
}
function parseLookupNode(node: Record<string, unknown>): LookupConfig {
  const filterObj = (node.filter as Record<string, unknown>) ?? {};
  const filters: LookupFilterRow[] = Object.entries(filterObj).map(([key, v]) => {
    const vv = v as Record<string, unknown> | string | number | null;
    if (vv && typeof vv === "object" && vv.type === "field_ref") {
      return { id: uid(), targetFieldName: key, matchType: "field_ref", literalValue: "", fieldRefField: String(vv.field ?? ""), nestedLookup: null };
    }
    if (vv && typeof vv === "object" && vv.type === "lookup") {
      return { id: uid(), targetFieldName: key, matchType: "lookup", literalValue: "", fieldRefField: "", nestedLookup: parseLookupNode(vv as Record<string, unknown>) };
    }
    return { id: uid(), targetFieldName: key, matchType: "literal", literalValue: String(vv ?? ""), fieldRefField: "", nestedLookup: null };
  });
  return {
    entityId: String(node.entity_id ?? ""),
    filters,
    resultField: String(node.field ?? ""),
    agg: (String(node.agg ?? "value") as LookupConfig["agg"]),
  };
}

/* ── Serialize conditions rows → API dict.
   Rules with 2+ conditions used to serialize as {type:"logical", op:"and",
   conditions:[...]} — a shape the backend has never recognized (it only
   ever accepted {type:"and", children:[...]}), so multi-condition rules
   have been silently failing to save/evaluate correctly. Fixed here. ── */
function buildConditions(rows: CondRow[]): Record<string, unknown> {
  if (!rows.length) return {};
  const items = rows.map((r) => ({
    type: "compare", field: r.field, op: r.op,
    value: r.valueType === "lookup" && r.lookup ? buildLookupNode(r.lookup) : (r.value || null),
  }));
  return items.length === 1 ? items[0] : { type: "and", children: items };
}

/* ── Parse API conditions dict → rows (accepts the legacy "logical" shape
   too, so a rule saved by the old broken code doesn't just disappear when
   reopened for editing). ── */
function parseConditions(raw: Record<string, unknown>): CondRow[] {
  if (!raw || !Object.keys(raw).length) return [];
  function toRow(c: Record<string, unknown>): CondRow {
    const val = c.value as Record<string, unknown> | string | number | null;
    if (val && typeof val === "object" && val.type === "lookup") {
      return { id: uid(), field: String(c.field ?? ""), op: String(c.op ?? "eq"), valueType: "lookup", value: "", lookup: parseLookupNode(val as Record<string, unknown>) };
    }
    return { id: uid(), field: String(c.field ?? ""), op: String(c.op ?? "eq"), valueType: "literal", value: String(val ?? ""), lookup: null };
  }
  if (raw.type === "and" || raw.type === "logical") {
    const list = ((raw.children ?? raw.conditions) as unknown[]) ?? [];
    return list.map((c) => toRow(c as Record<string, unknown>));
  }
  if (raw.type === "compare") return [toRow(raw)];
  return [];
}

/* Build a single expression node for an action's `value` field — the same
   three-way choice a condition's compare value has, plus field_ref (an
   action's value can reference another field on the SAME triggering
   record, which a condition's compare doesn't need since `field` already
   names that side of the comparison). */
function buildActionValueExpr(r: ActionRow): Record<string, unknown> {
  if (r.valueType === "lookup" && r.lookup) return buildLookupNode(r.lookup);
  if (r.valueType === "field_ref") return { type: "field_ref", field: r.value };
  return { type: "literal", value: r.value };
}

/* ── Serialize action rows → API list.
   set_field used to send {field_name: ...} — the backend action schema
   (and the interpreter) only ever read `field`, so every set_field action
   created through this UI has been a silent no-op. send_notification sent
   just {message} — the backend expects to/to_field + subject + template,
   none of which existed here, so notification rules never actually sent
   anything either. Both fixed here. ── */
function buildActions(rows: ActionRow[]): Record<string, unknown>[] {
  return rows.map((r) => {
    if (r.type === "set_field") return { type: "set_field", field: r.field, value: r.value };
    if (r.type === "update_record") {
      return {
        type: "update_record",
        record_id_field: r.recordIdField,
        payload: { [r.field]: buildActionValueExpr(r) },
      };
    }
    if (r.type === "send_notification") {
      return {
        type: "send_notification",
        ...(r.notifyToType === "field_ref" ? { to_field: r.notifyTo } : { to: r.notifyTo }),
        subject: r.notifySubject,
        template: r.notifyTemplate,
      };
    }
    if (r.type === "call_webhook") return { type: "call_webhook", url: r.url, method: "POST" };
    if (r.type === "block_save")   return { type: "block_save", message: r.message || "Сохранение отклонено правилом проверки" };
    return { type: r.type };
  });
}

/* ── Parse API actions list → rows ── */
function parseActions(acts: Record<string, unknown>[]): ActionRow[] {
  return (acts ?? []).map((a) => {
    let field = String((a.field as string) ?? (a.field_name as string) ?? "");
    let valueType: ActionRow["valueType"] = "literal";
    let value = String(a.value ?? "");
    let lookup: LookupConfig | null = null;
    if (a.type === "update_record") {
      const payload = (a.payload as Record<string, unknown>) ?? {};
      const [k, v] = Object.entries(payload)[0] ?? ["", null];
      field = k;
      if (v && typeof v === "object" && (v as Record<string, unknown>).type === "lookup") {
        valueType = "lookup";
        lookup = parseLookupNode(v as Record<string, unknown>);
      } else if (v && typeof v === "object" && (v as Record<string, unknown>).type === "field_ref") {
        valueType = "field_ref";
        value = String((v as Record<string, unknown>).field ?? "");
      } else if (v && typeof v === "object" && (v as Record<string, unknown>).type === "literal") {
        value = String((v as Record<string, unknown>).value ?? "");
      } else {
        value = String(v ?? "");
      }
    }
    return {
    id:      uid(),
    type:    String(a.type ?? "set_field"),
    field,
    value,
    valueType,
    lookup,
    recordIdField: String((a.record_id_field as string) ?? ""),
    message: String(a.message ?? ""),
    url:     String(a.url ?? ""),
    notifyToType: a.to_field ? "field_ref" : "literal",
    notifyTo:      String((a.to_field as string) ?? (a.to as string) ?? ""),
    notifySubject: String(a.subject ?? ""),
    notifyTemplate: String(a.template ?? ""),
    };
  });
}

/* ── Blank form state ── */
function blankForm(entityId: string) {
  return {
    name: "",
    description: "",
    priority: 100,
    triggerEvent: "record.created",
    watchFields: [] as string[],
    scheduleKind: "cron" as "cron" | "relative_date",
    cronMinute: "0", cronHour: "0", cronDayOfMonth: "*", cronMonthOfYear: "*", cronDayOfWeek: "*",
    relativeDateField: "",
    relativeOffsetDays: -3,
    conditions: [] as CondRow[],
    actions: [] as ActionRow[],
    entityId,
  };
}

const LOOKUP_AGG_OPTIONS = [
  { value: "value", label: "значение поля" },
  { value: "sum",    label: "сумма" },
  { value: "count",  label: "количество записей" },
  { value: "avg",    label: "среднее" },
  { value: "min",    label: "минимум" },
  { value: "max",    label: "максимум" },
];

/* ════════════════════════════════════════════════════════════════
   Lookup editor — reads a value from a DIFFERENT entity's records.
   Recursive: a filter row can itself be "another lookup" (chaining), which
   renders a nested LookupEditor. Every level's "field_ref" filter option
   is always a field on the CURRENT (validated) entity — chaining a filter
   through an intermediate table's own fields isn't expressible via
   field_ref, only by nesting a lookup as that filter's value, so
   `currentEntityFields` never changes across nesting depth.
   ════════════════════════════════════════════════════════════════ */
function LookupEditor({ value, onChange, entities, currentEntityFields, depth = 0 }: {
  value: LookupConfig;
  onChange: (v: LookupConfig) => void;
  entities: EntityRead[];
  currentEntityFields: FieldRead[];
  depth?: number;
}) {
  const targetEntity = entities.find((e) => e.id === value.entityId) ?? null;
  const targetFields = (targetEntity?.fields ?? []).filter((f) => !f.is_system);

  function patch(p: Partial<LookupConfig>) { onChange({ ...value, ...p }); }
  function addFilter() { patch({ filters: [...value.filters, blankFilterRow()] }); }
  function patchFilter(id: string, p: Partial<LookupFilterRow>) {
    patch({ filters: value.filters.map((f) => f.id === id ? { ...f, ...p } : f) });
  }
  function removeFilter(id: string) { patch({ filters: value.filters.filter((f) => f.id !== id) }); }

  if (depth > 3) {
    return <p className="text-[12px] text-mistake">Слишком глубокая вложенность (максимум 4 уровня)</p>;
  }

  return (
    <div className={cn("flex flex-col gap-2 border-l-2 border-cta/20 pl-3 py-2", depth > 0 && "bg-white/50 rounded-r-[8px]")}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[12px] text-primary/50 shrink-0">Найти в</span>
        <select
          value={value.entityId}
          onChange={(e) => patch({ entityId: e.target.value, filters: [], resultField: "" })}
          className="h-[30px] w-[160px] border border-cardbg rounded-[6px] px-2 text-[12px] bg-white focus:outline-none focus:border-cta"
        >
          <option value="">— таблица —</option>
          {entities.map((e) => <option key={e.id} value={e.id}>{e.display_name}</option>)}
        </select>
        <select
          value={value.agg}
          onChange={(e) => patch({ agg: e.target.value as LookupConfig["agg"] })}
          className="h-[30px] w-[150px] border border-cardbg rounded-[6px] px-2 text-[12px] bg-white focus:outline-none focus:border-cta"
        >
          {LOOKUP_AGG_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {value.agg !== "count" && (
          <>
            <span className="text-[12px] text-primary/50 shrink-0">поля</span>
            <select
              value={value.resultField}
              onChange={(e) => patch({ resultField: e.target.value })}
              className="h-[30px] w-[150px] border border-cardbg rounded-[6px] px-2 text-[12px] bg-white focus:outline-none focus:border-cta"
            >
              <option value="">— поле —</option>
              {targetFields.map((f) => <option key={f.id} value={f.name}>{f.display_name}</option>)}
            </select>
          </>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {value.filters.map((f) => (
          <div key={f.id} className="flex flex-col gap-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[12px] text-primary/50 shrink-0">где</span>
              <select
                value={f.targetFieldName}
                onChange={(e) => patchFilter(f.id, { targetFieldName: e.target.value })}
                className="h-[30px] w-[150px] border border-cardbg rounded-[6px] px-2 text-[12px] bg-white focus:outline-none focus:border-cta"
              >
                <option value="">— поле таблицы —</option>
                <option value="id">ID записи</option>
                {targetFields.map((tf) => <option key={tf.id} value={tf.name}>{tf.display_name}</option>)}
              </select>
              <span className="text-[12px] text-primary/50 shrink-0">=</span>
              <select
                value={f.matchType}
                onChange={(e) => patchFilter(f.id, { matchType: e.target.value as LookupFilterRow["matchType"], nestedLookup: e.target.value === "lookup" ? (f.nestedLookup ?? blankLookup()) : f.nestedLookup })}
                className="h-[30px] w-[150px] border border-cardbg rounded-[6px] px-2 text-[12px] bg-white focus:outline-none focus:border-cta"
              >
                <option value="field_ref">поле текущей записи</option>
                <option value="literal">конкретное значение</option>
                <option value="lookup">результат другого поиска</option>
              </select>
              {f.matchType === "field_ref" && (
                <select
                  value={f.fieldRefField}
                  onChange={(e) => patchFilter(f.id, { fieldRefField: e.target.value })}
                  className="h-[30px] flex-1 min-w-[140px] border border-cardbg rounded-[6px] px-2 text-[12px] bg-white focus:outline-none focus:border-cta"
                >
                  <option value="">— поле —</option>
                  {currentEntityFields.map((cf) => <option key={cf.id} value={cf.name}>{cf.display_name}</option>)}
                </select>
              )}
              {f.matchType === "literal" && (
                <input
                  value={f.literalValue}
                  onChange={(e) => patchFilter(f.id, { literalValue: e.target.value })}
                  placeholder="значение"
                  className="h-[30px] flex-1 min-w-[100px] border border-cardbg rounded-[6px] px-2 text-[12px] focus:outline-none focus:border-cta"
                />
              )}
              <button onClick={() => removeFilter(f.id)} className="text-primary/30 hover:text-mistake text-[15px] leading-none shrink-0">✕</button>
            </div>
            {f.matchType === "lookup" && f.nestedLookup && (
              <LookupEditor
                value={f.nestedLookup}
                onChange={(lk) => patchFilter(f.id, { nestedLookup: lk })}
                entities={entities}
                currentEntityFields={currentEntityFields}
                depth={depth + 1}
              />
            )}
          </div>
        ))}
        <button onClick={addFilter} className="self-start text-[12px] text-cta hover:underline">+ Добавить условие поиска</button>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Rule editor modal
   ════════════════════════════════════════════════════════════════ */
function RuleModal({
  rule,
  entityId,
  fields,
  entities,
  appId,
  ruleType = "automation",
  onClose,
}: {
  rule: Rule | null;
  entityId: string;
  fields: FieldRead[];
  entities: EntityRead[];
  appId: string;
  ruleType?: "automation" | "validation";
  onClose: () => void;
}) {
  const isEdit = !!rule;
  const createMut = useCreateRule(appId);
  const updateMut = useUpdateRule(appId);
  const isValidation = ruleType === "validation";
  const actionTypes = isValidation ? VALIDATION_ACTION_TYPES : AUTOMATION_ACTION_TYPES;
  // Only "update_record" needs relation metadata (to resolve a relation
  // field on this entity to the related entity whose record gets updated).
  const { data: relations = [] } = useRelations(appId);

  const [form, setForm] = useState(() => {
    if (rule) {
      const blank = blankForm(entityId);
      return {
        ...blank,
        name:        rule.name,
        description: rule.description ?? "",
        priority:    rule.priority,
        triggerEvent: rule.trigger.event,
        watchFields:  rule.trigger.watch_fields ?? [],
        scheduleKind: rule.trigger.schedule_kind ?? blank.scheduleKind,
        cronMinute:      rule.trigger.cron?.minute ?? blank.cronMinute,
        cronHour:        rule.trigger.cron?.hour ?? blank.cronHour,
        cronDayOfMonth:  rule.trigger.cron?.day_of_month ?? blank.cronDayOfMonth,
        cronMonthOfYear: rule.trigger.cron?.month_of_year ?? blank.cronMonthOfYear,
        cronDayOfWeek:   rule.trigger.cron?.day_of_week ?? blank.cronDayOfWeek,
        relativeDateField:   rule.trigger.relative_date?.date_field ?? blank.relativeDateField,
        relativeOffsetDays:  rule.trigger.relative_date?.offset_days ?? blank.relativeOffsetDays,
        conditions:  parseConditions(rule.conditions),
        actions:     parseActions(rule.actions),
        entityId,
      };
    }
    const blank = blankForm(entityId);
    if (isValidation) blank.actions = [{ id: uid(), type: "block_save", field: "", value: "", message: "", url: "", notifyToType: "literal", notifyTo: "", notifySubject: "", notifyTemplate: "", recordIdField: "", valueType: "literal", lookup: null }];
    return blank;
  });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const userFields = fields.filter((f) => !f.is_system);

  function setF<K extends keyof typeof form>(k: K, v: typeof form[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  /* ── Condition helpers ── */
  function addCond() {
    setForm((p) => ({ ...p, conditions: [...p.conditions, { id: uid(), field: userFields[0]?.name ?? "", op: "eq", valueType: "literal" as const, value: "", lookup: null }] }));
  }
  function patchCond(id: string, patch: Partial<CondRow>) {
    setForm((p) => ({ ...p, conditions: p.conditions.map((c) => c.id === id ? { ...c, ...patch } : c) }));
  }
  function removeCond(id: string) {
    setForm((p) => ({ ...p, conditions: p.conditions.filter((c) => c.id !== id) }));
  }

  /* ── Action helpers ── */
  function addAction() {
    const defaultType = isValidation ? "block_save" : "set_field";
    setForm((p) => ({ ...p, actions: [...p.actions, {
      id: uid(), type: defaultType, field: userFields[0]?.name ?? "", value: "", message: "", url: "",
      notifyToType: "literal", notifyTo: "", notifySubject: "", notifyTemplate: "",
      recordIdField: "", valueType: "literal", lookup: null,
    }] }));
  }
  function patchAction(id: string, patch: Partial<ActionRow>) {
    setForm((p) => ({ ...p, actions: p.actions.map((a) => a.id === id ? { ...a, ...patch } : a) }));
  }
  function removeAction(id: string) {
    setForm((p) => ({ ...p, actions: p.actions.filter((a) => a.id !== id) }));
  }

  function buildTrigger(): RuleTrigger {
    if (form.triggerEvent === "schedule") {
      return {
        event: "schedule",
        schedule_kind: form.scheduleKind,
        cron: form.scheduleKind === "cron" ? {
          minute: form.cronMinute, hour: form.cronHour, day_of_month: form.cronDayOfMonth,
          month_of_year: form.cronMonthOfYear, day_of_week: form.cronDayOfWeek,
        } : undefined,
        relative_date: form.scheduleKind === "relative_date" ? {
          date_field: form.relativeDateField, offset_days: form.relativeOffsetDays,
        } : undefined,
      };
    }
    return { event: form.triggerEvent, watch_fields: form.triggerEvent === "field.changed" ? form.watchFields : undefined };
  }

  async function handleSave() {
    if (!form.name.trim()) { setError("Введите название правила"); return; }
    if (form.triggerEvent === "schedule" && form.scheduleKind === "relative_date" && !form.relativeDateField) {
      setError("Выберите поле с датой для расписания");
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      name:        form.name.trim(),
      description: form.description.trim() || null,
      priority:    form.priority,
      rule_type:   ruleType,
      trigger:     buildTrigger(),
      conditions:  buildConditions(form.conditions),
      actions:     buildActions(form.actions),
    };
    try {
      if (isEdit && rule) {
        await updateMut.mutateAsync({ ruleId: rule.id, body: payload });
      } else {
        await createMut.mutateAsync({ ...payload, entity_id: entityId });
      }
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  }

  const opsWithoutValue = ["is_null", "is_not_null"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-[16px] shadow-2xl w-[820px] max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-7 py-5 border-b border-cardbg">
          <h2 className="text-[20px] font-bold text-primary">{isEdit ? "Редактировать правило" : "Новое правило"}</h2>
          <button onClick={onClose} className="text-primary/40 hover:text-primary text-xl leading-none">✕</button>
        </div>

        <div className="overflow-y-auto flex-1 px-7 py-6 flex flex-col gap-6">
          {error && <div className="px-4 py-2 bg-[#FDECEC] text-mistake text-[14px] rounded-[8px]">{error}</div>}

          {/* ── Basic info ── */}
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-[13px] text-primary/60 mb-1">Название *</label>
              <input
                value={form.name}
                onChange={(e) => setF("name", e.target.value)}
                placeholder="Например: Уведомление при создании"
                className="w-full h-[38px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta"
              />
            </div>
            <div className="w-[120px]">
              <label className="block text-[13px] text-primary/60 mb-1">Приоритет</label>
              <input
                type="number" min={1} max={9999}
                value={form.priority}
                onChange={(e) => setF("priority", Number(e.target.value))}
                className="w-full h-[38px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta"
              />
            </div>
          </div>

          {/* ── Trigger ── */}
          <div>
            <p className="text-[15px] font-semibold text-primary mb-3">Триггер</p>
            <select
              value={form.triggerEvent}
              onChange={(e) => setF("triggerEvent", e.target.value)}
              className="h-[38px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta bg-white"
            >
              {TRIGGER_EVENTS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            {form.triggerEvent === "field.changed" && userFields.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {userFields.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => {
                      const wf = form.watchFields;
                      setF("watchFields", wf.includes(f.name) ? wf.filter((x) => x !== f.name) : [...wf, f.name]);
                    }}
                    className={cn(
                      "px-3 py-1 rounded-full border text-[13px] transition-colors",
                      form.watchFields.includes(f.name)
                        ? "bg-cta text-white border-cta"
                        : "border-cardbg text-primary hover:border-cta"
                    )}
                  >
                    {f.display_name}
                  </button>
                ))}
              </div>
            )}
            {form.triggerEvent === "schedule" && (
              <div className="mt-3 flex flex-col gap-3 bg-mainbg rounded-[8px] p-4">
                <select
                  value={form.scheduleKind}
                  onChange={(e) => setF("scheduleKind", e.target.value as "cron" | "relative_date")}
                  className="h-[36px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta bg-white w-fit"
                >
                  {SCHEDULE_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>

                {form.scheduleKind === "cron" ? (
                  <div>
                    <div className="flex gap-2">
                      {([
                        ["cronMinute", "Минута"], ["cronHour", "Час"], ["cronDayOfMonth", "День месяца"],
                        ["cronMonthOfYear", "Месяц"], ["cronDayOfWeek", "День недели"],
                      ] as const).map(([key, label]) => (
                        <div key={key} className="flex-1">
                          <label className="block text-[11px] text-primary/50 mb-1">{label}</label>
                          <input
                            value={form[key]}
                            onChange={(e) => setF(key, e.target.value)}
                            placeholder="*"
                            className="w-full h-[32px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary text-center focus:outline-none focus:border-cta"
                          />
                        </div>
                      ))}
                    </div>
                    <p className="text-[11px] text-primary/40 mt-2">
                      «*» — любое значение; конкретное число — точное совпадение. Проверяется раз в час, поэтому минута
                      имеет смысл только как «0» (сработает в начале часа) или «*» (каждый час). Например: час=0, день месяца=1 — раз в месяц, первого числа.
                    </p>
                  </div>
                ) : (
                  <div className="flex gap-3 items-end">
                    <div className="flex-1">
                      <label className="block text-[11px] text-primary/50 mb-1">Поле с датой</label>
                      <select
                        value={form.relativeDateField}
                        onChange={(e) => setF("relativeDateField", e.target.value)}
                        className="w-full h-[36px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta bg-white"
                      >
                        <option value="">— выберите поле —</option>
                        {userFields.filter((f) => f.field_type === "date" || f.field_type === "datetime").map((f) => (
                          <option key={f.id} value={f.name}>{f.display_name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="w-[140px]">
                      <label className="block text-[11px] text-primary/50 mb-1">Дней (- = до, + = после)</label>
                      <input
                        type="number" min={-365} max={365}
                        value={form.relativeOffsetDays}
                        onChange={(e) => setF("relativeOffsetDays", Number(e.target.value))}
                        className="w-full h-[36px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Conditions ── */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <p className="text-[15px] font-semibold text-primary">ЕСЛИ (условия)</p>
              <button onClick={addCond} className="text-[13px] text-cta hover:underline">+ Добавить условие</button>
            </div>
            {form.conditions.length === 0 && (
              <p className="text-[13px] text-primary/40 italic">Нет условий — правило срабатывает всегда</p>
            )}
            <div className="flex flex-col gap-2">
              {form.conditions.map((c, i) => (
                <div key={c.id} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  {i > 0 && <span className="text-[11px] font-semibold text-primary/40 w-8 text-right shrink-0">И</span>}
                  {i === 0 && <span className="w-8 shrink-0" />}
                  <select
                    value={c.field}
                    onChange={(e) => patchCond(c.id, { field: e.target.value })}
                    className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                  >
                    {fieldOptions(userFields, c.field)}
                  </select>
                  <select
                    value={c.op}
                    onChange={(e) => patchCond(c.id, { op: e.target.value })}
                    className="h-[34px] w-[150px] border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                  >
                    {COMPARE_OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  {!opsWithoutValue.includes(c.op) && (
                    <select
                      value={c.valueType}
                      onChange={(e) => {
                        const vt = e.target.value as "literal" | "lookup";
                        patchCond(c.id, { valueType: vt, lookup: vt === "lookup" ? (c.lookup ?? blankLookup()) : c.lookup });
                      }}
                      className="h-[34px] w-[110px] shrink-0 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                    >
                      <option value="literal">Значение</option>
                      <option value="lookup">Из таблицы</option>
                    </select>
                  )}
                  {!opsWithoutValue.includes(c.op) && c.valueType === "literal" && (
                    <input
                      value={c.value}
                      onChange={(e) => patchCond(c.id, { value: e.target.value })}
                      placeholder="Значение"
                      className="h-[34px] w-[180px] border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                    />
                  )}
                  <button onClick={() => removeCond(c.id)} className="text-primary/30 hover:text-mistake text-lg leading-none w-6 shrink-0">✕</button>
                </div>
                {!opsWithoutValue.includes(c.op) && c.valueType === "lookup" && c.lookup && (
                  <div className="ml-10">
                    <LookupEditor
                      value={c.lookup}
                      onChange={(lk) => patchCond(c.id, { lookup: lk })}
                      entities={entities}
                      currentEntityFields={userFields}
                    />
                  </div>
                )}
                </div>
              ))}
            </div>
          </div>

          {/* ── Actions ── */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <p className="text-[15px] font-semibold text-primary">ТО (действия)</p>
              <button onClick={addAction} className="text-[13px] text-cta hover:underline">+ Добавить действие</button>
            </div>
            {form.actions.length === 0 && (
              <p className="text-[13px] text-primary/40 italic">Нет действий — добавьте хотя бы одно</p>
            )}
            <div className="flex flex-col gap-3">
              {form.actions.map((a) => (
                <div key={a.id} className="flex items-start gap-2 bg-mainbg rounded-[10px] p-3">
                  <select
                    value={a.type}
                    onChange={(e) => patchAction(a.id, { type: e.target.value })}
                    className="h-[34px] w-[230px] border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta shrink-0"
                  >
                    {actionTypes.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                  <div className="flex-1 flex flex-col gap-2">
                    {a.type === "set_field" && (
                      <div className="flex gap-2">
                        <select
                          value={a.field}
                          onChange={(e) => patchAction(a.id, { field: e.target.value })}
                          className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                        >
                          {fieldOptions(userFields, a.field)}
                        </select>
                        <input
                          value={a.value}
                          onChange={(e) => patchAction(a.id, { value: e.target.value })}
                          placeholder="Новое значение"
                          className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                        />
                      </div>
                    )}
                    {a.type === "update_record" && (() => {
                      const relationFields = userFields.filter((f) => f.field_type === "relation");
                      const rel = relations.find(
                        (r) => r.from_entity_id === entityId && r.from_field_name === a.recordIdField
                      );
                      const targetEntity = rel ? entities.find((e) => e.id === rel.to_entity_id) : null;
                      const targetFields = (targetEntity?.fields ?? []).filter((f) => !f.is_system);
                      return (
                        <div className="flex flex-col gap-2">
                          <div className="flex gap-2 items-center">
                            <span className="text-[12px] text-primary/50 shrink-0">Через связь</span>
                            <select
                              value={a.recordIdField}
                              onChange={(e) => patchAction(a.id, { recordIdField: e.target.value, field: "" })}
                              className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                            >
                              <option value="">— выберите поле-связь —</option>
                              {relationFields.map((f) => <option key={f.id} value={f.name}>{f.display_name}</option>)}
                            </select>
                          </div>
                          {a.recordIdField && (
                            <div className="flex gap-2 items-center">
                              <span className="text-[12px] text-primary/50 shrink-0">Поле там</span>
                              <select
                                value={a.field}
                                onChange={(e) => patchAction(a.id, { field: e.target.value })}
                                className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                                disabled={!targetEntity}
                              >
                                <option value="">— выберите поле —</option>
                                {fieldOptions(targetFields, a.field)}
                              </select>
                            </div>
                          )}
                          {a.recordIdField && a.field && (
                            <div className="flex gap-2 items-center">
                              <select
                                value={a.valueType}
                                onChange={(e) => {
                                  const vt = e.target.value as ActionRow["valueType"];
                                  patchAction(a.id, { valueType: vt, lookup: vt === "lookup" ? (a.lookup ?? blankLookup()) : a.lookup });
                                }}
                                className="h-[34px] w-[160px] shrink-0 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                              >
                                <option value="literal">Значение</option>
                                <option value="field_ref">Поле текущей записи</option>
                                <option value="lookup">Агрегация по таблице</option>
                              </select>
                              {a.valueType === "literal" && (
                                <input
                                  value={a.value}
                                  onChange={(e) => patchAction(a.id, { value: e.target.value })}
                                  placeholder="Значение"
                                  className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                                />
                              )}
                              {a.valueType === "field_ref" && (
                                <select
                                  value={a.value}
                                  onChange={(e) => patchAction(a.id, { value: e.target.value })}
                                  className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                                >
                                  <option value="">— поле текущей записи —</option>
                                  {fieldOptions(userFields, a.value)}
                                </select>
                              )}
                            </div>
                          )}
                          {a.recordIdField && a.field && a.valueType === "lookup" && a.lookup && (
                            <LookupEditor
                              value={a.lookup}
                              onChange={(lk) => patchAction(a.id, { lookup: lk })}
                              entities={entities}
                              currentEntityFields={userFields}
                            />
                          )}
                        </div>
                      );
                    })()}
                    {a.type === "send_notification" && (
                      <div className="flex flex-col gap-2">
                        <div className="flex gap-2">
                          <select
                            value={a.notifyToType}
                            onChange={(e) => patchAction(a.id, { notifyToType: e.target.value as "literal" | "field_ref", notifyTo: "" })}
                            className="h-[34px] w-[140px] shrink-0 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                          >
                            <option value="literal">Email (статично)</option>
                            <option value="field_ref">Поле записи</option>
                          </select>
                          {a.notifyToType === "field_ref" ? (
                            <select
                              value={a.notifyTo}
                              onChange={(e) => patchAction(a.id, { notifyTo: e.target.value })}
                              className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] bg-white focus:outline-none focus:border-cta"
                            >
                              <option value="">— поле с email —</option>
                              {fieldOptions(userFields, a.notifyTo)}
                            </select>
                          ) : (
                            <input
                              value={a.notifyTo}
                              onChange={(e) => patchAction(a.id, { notifyTo: e.target.value })}
                              placeholder="куда: email@example.com"
                              className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                            />
                          )}
                        </div>
                        <input
                          value={a.notifySubject}
                          onChange={(e) => patchAction(a.id, { notifySubject: e.target.value })}
                          placeholder="Тема письма"
                          className="h-[34px] border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                        />
                        <textarea
                          value={a.notifyTemplate}
                          onChange={(e) => patchAction(a.id, { notifyTemplate: e.target.value })}
                          placeholder="Текст уведомления (HTML)"
                          rows={2}
                          className="border border-cardbg rounded-[8px] px-2 py-1.5 text-[13px] focus:outline-none focus:border-cta resize-y"
                        />
                      </div>
                    )}
                    {a.type === "call_webhook" && (
                      <input
                        value={a.url}
                        onChange={(e) => patchAction(a.id, { url: e.target.value })}
                        placeholder="https://example.com/hook"
                        className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                      />
                    )}
                    {a.type === "stop" && (
                      <span className="text-[13px] text-primary/50 leading-[34px]">Остальные действия этого и последующих правил в батче не выполнятся. Запись всё равно сохранится.</span>
                    )}
                    {a.type === "block_save" && (
                      <input
                        value={a.message}
                        onChange={(e) => patchAction(a.id, { message: e.target.value })}
                        placeholder="Сообщение об ошибке для пользователя"
                        className="h-[34px] flex-1 border border-cardbg rounded-[8px] px-2 text-[13px] focus:outline-none focus:border-cta"
                      />
                    )}
                  </div>
                  <button onClick={() => removeAction(a.id)} className="text-primary/30 hover:text-mistake text-lg leading-none w-6 mt-[7px] shrink-0">✕</button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-7 py-4 border-t border-cardbg">
          <button onClick={onClose} className="h-[38px] px-5 rounded-[8px] border border-cardbg text-[14px] text-primary hover:bg-mainbg">
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="h-[38px] px-6 rounded-[8px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90 disabled:opacity-50"
          >
            {saving ? "Сохранение…" : "Сохранить правило"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Autofill rule editor modal
   ════════════════════════════════════════════════════════════════ */
interface FillRow { id: string; targetField: string; sourceType: "literal" | "field_ref"; sourceValue: string; }

function AutofillModal({ rule, entityId, fields, appId, onClose }: {
  rule: Rule | null; entityId: string; fields: FieldRead[]; appId: string; onClose: () => void;
}) {
  const isEdit = !!rule;
  const createMut = useCreateRule(appId);
  const updateMut = useUpdateRule(appId);
  const userFields = fields.filter((f) => !f.is_system);

  function parseAutofillActions(actions: Record<string, unknown>[]): FillRow[] {
    return actions.filter((a) => a.type === "set_field").map((a) => ({
      id: uid(),
      targetField: String((a.field_name ?? a.field) ?? ""),
      sourceType: (a.value as Record<string, unknown>)?.type === "field_ref" ? "field_ref" : "literal",
      sourceValue: (a.value as Record<string, unknown>)?.type === "field_ref"
        ? String((a.value as Record<string, unknown>).field ?? "")
        : String(a.value ?? ""),
    }));
  }

  const [name, setName] = useState(rule?.name ?? "");
  const [triggerEvent, setTriggerEvent] = useState(rule?.trigger.event ?? "record.created");
  const [watchField, setWatchField] = useState(rule?.trigger.watch_fields?.[0] ?? "");
  const [condField, setCondField] = useState("");
  const [condOp, setCondOp] = useState("eq");
  const [condValue, setCondValue] = useState("");
  const [hasCond, setHasCond] = useState(false);
  const [fills, setFills] = useState<FillRow[]>(() =>
    rule
      ? parseAutofillActions(rule.actions)
      : [{ id: uid(), targetField: userFields[0]?.name ?? "", sourceType: "literal", sourceValue: "" }]
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (rule?.conditions && Object.keys(rule.conditions).length > 0) {
      const c = rule.conditions as Record<string, unknown>;
      if (c.type === "compare") {
        setHasCond(true);
        setCondField(String(c.field ?? ""));
        setCondOp(String(c.op ?? "eq"));
        setCondValue(String(c.value ?? ""));
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function addFill() {
    setFills((p) => [...p, { id: uid(), targetField: userFields[0]?.name ?? "", sourceType: "literal", sourceValue: "" }]);
  }
  function patchFill(id: string, patch: Partial<FillRow>) {
    setFills((p) => p.map((f) => f.id === id ? { ...f, ...patch } : f));
  }
  function removeFill(id: string) {
    setFills((p) => p.filter((f) => f.id !== id));
  }

  async function handleSave() {
    if (!name.trim()) { setError("Введите название"); return; }
    if (fills.length === 0) { setError("Добавьте хотя бы одно поле для заполнения"); return; }
    setSaving(true);
    setError(null);
    const actions = fills.map((f) => ({
      type: "set_field",
      field_name: f.targetField,
      value: f.sourceType === "field_ref" ? { type: "field_ref", field: f.sourceValue } : f.sourceValue,
    }));
    const conditions = hasCond && condField
      ? { type: "compare", field: condField, op: condOp, value: condValue || null }
      : {};
    const payload = {
      name: name.trim(),
      rule_type: "autofill" as const,
      trigger: { event: triggerEvent, watch_fields: triggerEvent === "field.changed" && watchField ? [watchField] : [] },
      conditions,
      actions,
      priority: 50,
    };
    try {
      if (isEdit && rule) {
        await updateMut.mutateAsync({ ruleId: rule.id, body: payload });
      } else {
        await createMut.mutateAsync({ ...payload, entity_id: entityId });
      }
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  }

  const AUTOFILL_TRIGGERS = [
    { value: "record.created", label: "При создании записи" },
    { value: "record.updated", label: "При любом обновлении" },
    { value: "field.changed",  label: "При изменении поля" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-[16px] shadow-2xl w-[640px] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-7 py-5 border-b border-cardbg">
          <div>
            <h2 className="text-[20px] font-bold text-primary">{isEdit ? "Редактировать автозаполнение" : "Новое автозаполнение"}</h2>
            <p className="text-[13px] text-primary/50 mt-0.5">Автоматически заполняет поля при срабатывании</p>
          </div>
          <button onClick={onClose} className="text-primary/40 hover:text-primary text-xl leading-none">✕</button>
        </div>

        <div className="overflow-y-auto flex-1 px-7 py-6 flex flex-col gap-5">
          {error && <div className="px-4 py-2 bg-[#FDECEC] text-mistake text-[14px] rounded-[8px]">{error}</div>}

          {/* Name */}
          <div>
            <label className="block text-[13px] text-primary/60 mb-1">Название *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например: Заполнить дату при создании"
              className="w-full h-[38px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta"
            />
          </div>

          {/* Trigger */}
          <div>
            <label className="block text-[13px] text-primary/60 mb-1">Когда срабатывает</label>
            <div className="flex gap-2">
              <select
                value={triggerEvent}
                onChange={(e) => setTriggerEvent(e.target.value)}
                className="flex-1 h-[38px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta bg-white"
              >
                {AUTOFILL_TRIGGERS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              {triggerEvent === "field.changed" && (
                <select
                  value={watchField}
                  onChange={(e) => setWatchField(e.target.value)}
                  className="flex-1 h-[38px] border border-cardbg rounded-[8px] px-3 text-[14px] text-primary focus:outline-none focus:border-cta bg-white"
                >
                  <option value="">— выберите поле —</option>
                  {fieldOptions(userFields, watchField)}
                </select>
              )}
            </div>
          </div>

          {/* Optional condition */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <label className="text-[13px] text-primary/60">Условие (необязательно)</label>
              <button
                onClick={() => setHasCond((v) => !v)}
                className={cn("text-[12px] px-2 py-0.5 rounded-full border transition-colors",
                  hasCond ? "bg-cta/10 border-cta/30 text-cta" : "border-cardbg text-primary/40 hover:border-cta/30 hover:text-cta")}
              >
                {hasCond ? "Активно ✕" : "+ Добавить"}
              </button>
            </div>
            {hasCond && (
              <div className="flex gap-2 items-center bg-mainbg rounded-[8px] px-3 py-2">
                <span className="text-[13px] text-primary/50 shrink-0">Если</span>
                <select
                  value={condField}
                  onChange={(e) => setCondField(e.target.value)}
                  className="flex-1 h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary bg-white focus:outline-none"
                >
                  <option value="">— поле —</option>
                  {fieldOptions(userFields, condField)}
                </select>
                <select
                  value={condOp}
                  onChange={(e) => setCondOp(e.target.value)}
                  className="w-[130px] h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary bg-white focus:outline-none"
                >
                  {COMPARE_OPS.map((op) => <option key={op.value} value={op.value}>{op.label}</option>)}
                </select>
                {!["is_null", "is_not_null"].includes(condOp) && (
                  <input
                    value={condValue}
                    onChange={(e) => setCondValue(e.target.value)}
                    placeholder="значение"
                    className="w-[110px] h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary focus:outline-none focus:border-cta"
                  />
                )}
              </div>
            )}
          </div>

          {/* Fill mappings */}
          <div>
            <label className="block text-[13px] text-primary/60 mb-2">Заполнить поля</label>
            <div className="flex flex-col gap-2">
              {fills.map((f) => (
                <div key={f.id} className="flex items-center gap-2 bg-mainbg rounded-[8px] px-3 py-2">
                  <select
                    value={f.targetField}
                    onChange={(e) => patchFill(f.id, { targetField: e.target.value })}
                    className="flex-1 h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary bg-white focus:outline-none"
                  >
                    {fieldOptions(userFields, f.targetField)}
                  </select>
                  <span className="text-[13px] text-primary/40 shrink-0 font-mono">=</span>
                  <select
                    value={f.sourceType}
                    onChange={(e) => patchFill(f.id, { sourceType: e.target.value as "literal" | "field_ref", sourceValue: "" })}
                    className="w-[140px] h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary bg-white focus:outline-none"
                  >
                    <option value="literal">Значение</option>
                    <option value="field_ref">Другое поле</option>
                  </select>
                  {f.sourceType === "literal" ? (
                    <input
                      value={f.sourceValue}
                      onChange={(e) => patchFill(f.id, { sourceValue: e.target.value })}
                      placeholder="введите значение"
                      className="flex-1 h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary focus:outline-none focus:border-cta"
                    />
                  ) : (
                    <select
                      value={f.sourceValue}
                      onChange={(e) => patchFill(f.id, { sourceValue: e.target.value })}
                      className="flex-1 h-[34px] border border-cardbg rounded-[6px] px-2 text-[13px] text-primary bg-white focus:outline-none"
                    >
                      <option value="">— поле-источник —</option>
                      {fieldOptions(userFields, f.sourceValue)}
                    </select>
                  )}
                  {fills.length > 1 && (
                    <button onClick={() => removeFill(f.id)} className="text-primary/30 hover:text-mistake text-[16px] leading-none shrink-0">✕</button>
                  )}
                </div>
              ))}
              <button onClick={addFill} className="self-start text-[13px] text-cta hover:text-cta/70 font-medium mt-1">
                + Добавить поле
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-7 py-4 border-t border-cardbg">
          <button onClick={onClose} className="h-[38px] px-5 rounded-[8px] border border-cardbg text-[14px] text-primary hover:bg-mainbg">
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="h-[38px] px-6 rounded-[8px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90 disabled:opacity-50"
          >
            {saving ? "Сохранение…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Rule test modal
   ════════════════════════════════════════════════════════════════ */
function RuleTestModal({ appId, rule, onClose }: { appId: string; rule: Rule; onClose: () => void }) {
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState<RuleTestResponse | null>(null);
  const [parseErr, setParseErr] = useState("");
  const testMut = useTestRule(appId, rule.id);

  async function handleRun() {
    setParseErr("");
    let parsed: Record<string, unknown>;
    try { parsed = JSON.parse(payload); } catch { setParseErr("Невалидный JSON"); return; }
    const res = await testMut.mutateAsync({ record_payload: parsed, event: rule.trigger.event });
    setResult(res);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-[16px] shadow-2xl w-[680px] max-h-[85vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-7 py-5 border-b border-cardbg">
          <div>
            <h2 className="text-[18px] font-bold text-primary">Тест правила</h2>
            <p className="text-[13px] text-primary/50 mt-0.5">{rule.name}</p>
          </div>
          <button onClick={onClose} className="text-primary/40 hover:text-primary text-xl leading-none">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto px-7 py-5 flex flex-col gap-4">
          <div>
            <label className="block text-[13px] text-primary/60 mb-1">Тестовая запись (JSON)</label>
            <textarea
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              rows={6}
              className="w-full border border-cardbg rounded-[8px] px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-cta resize-none"
            />
            {parseErr && <p className="text-[12px] text-mistake mt-1">{parseErr}</p>}
          </div>
          {result && (
            <div className="flex flex-col gap-3">
              <div className={cn("flex items-center gap-2 px-4 py-2 rounded-[8px] text-[14px] font-medium",
                result.matched ? "bg-green-50 text-green-700" : "bg-mainbg text-primary/60")}>
                {result.matched ? "✓ Условие выполнено" : "✗ Условие не выполнено"}
              </div>
              {Object.keys(result.field_mutations).length > 0 && (
                <div>
                  <p className="text-[13px] font-semibold text-primary mb-1">Изменения полей</p>
                  <pre className="text-[12px] bg-mainbg rounded-[8px] px-3 py-2 overflow-x-auto">{JSON.stringify(result.field_mutations, null, 2)}</pre>
                </div>
              )}
              {result.errors.length > 0 && (
                <div>
                  <p className="text-[13px] font-semibold text-mistake mb-1">Ошибки</p>
                  {result.errors.map((e, i) => <p key={i} className="text-[12px] text-mistake">{e}</p>)}
                </div>
              )}
              {result.notifications.length > 0 && (
                <div>
                  <p className="text-[13px] font-semibold text-primary mb-1">Уведомления</p>
                  <pre className="text-[12px] bg-mainbg rounded-[8px] px-3 py-2 overflow-x-auto">{JSON.stringify(result.notifications, null, 2)}</pre>
                </div>
              )}
              {result.webhooks.length > 0 && (
                <div>
                  <p className="text-[13px] font-semibold text-primary mb-1">Вебхуки</p>
                  <pre className="text-[12px] bg-mainbg rounded-[8px] px-3 py-2 overflow-x-auto">{JSON.stringify(result.webhooks, null, 2)}</pre>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-3 px-7 py-4 border-t border-cardbg">
          <button onClick={onClose} className="h-[38px] px-5 rounded-[8px] border border-cardbg text-[14px] text-primary hover:bg-mainbg">Закрыть</button>
          <button onClick={handleRun} disabled={testMut.isPending}
            className="h-[38px] px-6 rounded-[8px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90 disabled:opacity-50">
            {testMut.isPending ? "Выполнение…" : "Запустить"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Rule logs drawer
   ════════════════════════════════════════════════════════════════ */
function RuleLogsDrawer({ appId, rule, onClose }: { appId: string; rule: Rule; onClose: () => void }) {
  const logsQuery = useRuleLogs(appId, rule.id, true);
  const logs: RuleExecutionLogRead[] = logsQuery.data ?? [];

  function statusColor(s: string) {
    if (s === "ok" || s === "success") return "text-green-600";
    if (s === "error" || s === "failed") return "text-mistake";
    return "text-primary/60";
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-t-[16px] shadow-2xl w-full max-w-[900px] max-h-[70vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-7 py-4 border-b border-cardbg shrink-0">
          <div>
            <h2 className="text-[17px] font-bold text-primary">Журнал выполнения</h2>
            <p className="text-[12px] text-primary/50 mt-0.5">{rule.name}</p>
          </div>
          <button onClick={onClose} className="text-primary/40 hover:text-primary text-xl leading-none">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto px-7 py-4">
          {logsQuery.isLoading && <p className="text-[13px] text-primary/40">Загрузка…</p>}
          {!logsQuery.isLoading && logs.length === 0 && (
            <p className="text-[13px] text-primary/40 text-center py-10">Записей нет — правило ещё не срабатывало</p>
          )}
          {logs.length > 0 && (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-primary/50 text-left border-b border-cardbg">
                  <th className="py-2 pr-4 font-medium">Время</th>
                  <th className="py-2 pr-4 font-medium">Событие</th>
                  <th className="py-2 pr-4 font-medium">Статус</th>
                  <th className="py-2 pr-4 font-medium">Длит., мс</th>
                  <th className="py-2 font-medium">Ошибка</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-cardbg/50 hover:bg-mainbg">
                    <td className="py-2 pr-4 text-primary/60 whitespace-nowrap">{new Date(log.executed_at).toLocaleString("ru")}</td>
                    <td className="py-2 pr-4 text-primary">{log.event}</td>
                    <td className={cn("py-2 pr-4 font-medium", statusColor(log.status))}>{log.status}</td>
                    <td className="py-2 pr-4 text-primary/60">{log.duration_ms ?? "—"}</td>
                    <td className="py-2 text-mistake text-[12px] truncate max-w-[200px]">{log.error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Rule conflicts drawer (ТЗ 3.5.4) — app-wide, optionally scoped to
   the currently selected entity
   ════════════════════════════════════════════════════════════════ */
function ConflictsDrawer({ appId, entityId, onClose }: { appId: string; entityId?: string; onClose: () => void }) {
  const [tab, setTab] = useState<"conflicts" | "webhooks">("conflicts");
  const conflictsQuery = useRuleConflicts(appId, entityId, tab === "conflicts");
  const webhooksQuery = useRuleWebhookDeliveries(appId, entityId, tab === "webhooks");
  const conflicts: RuleConflictLogRead[] = conflictsQuery.data ?? [];
  const deliveries = webhooksQuery.data ?? [];

  function fmt(value: unknown): string {
    if (value === null || value === undefined) return "—";
    return typeof value === "string" ? value : JSON.stringify(value);
  }

  const STATUS_LABEL: Record<string, string> = { delivered: "Доставлено", failed: "Ошибка", blocked: "Заблокировано" };
  const STATUS_CLASS: Record<string, string> = { delivered: "text-green-700", failed: "text-mistake", blocked: "text-amber-600" };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-t-[16px] shadow-2xl w-full max-w-[900px] max-h-[70vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-7 py-4 border-b border-cardbg shrink-0">
          <div>
            <h2 className="text-[17px] font-bold text-primary">Журнал правил</h2>
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => setTab("conflicts")}
                className={cn("text-[13px] px-3 py-1 rounded-full", tab === "conflicts" ? "bg-cta text-white" : "bg-mainbg text-primary/60")}
              >
                Конфликты
              </button>
              <button
                onClick={() => setTab("webhooks")}
                className={cn("text-[13px] px-3 py-1 rounded-full", tab === "webhooks" ? "bg-cta text-white" : "bg-mainbg text-primary/60")}
              >
                Webhook-доставки
              </button>
            </div>
          </div>
          <button onClick={onClose} className="text-primary/40 hover:text-primary text-xl leading-none">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto px-7 py-4">
          {tab === "conflicts" && (
            <>
              <p className="text-[12px] text-primary/50 mb-3">
                Когда два правила пишут разные значения в одно поле, побеждает правило с более высоким приоритетом
              </p>
              {conflictsQuery.isLoading && <p className="text-[13px] text-primary/40">Загрузка…</p>}
              {!conflictsQuery.isLoading && conflicts.length === 0 && (
                <p className="text-[13px] text-primary/40 text-center py-10">Конфликтов не зафиксировано</p>
              )}
              {conflicts.length > 0 && (
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-primary/50 text-left border-b border-cardbg">
                      <th className="py-2 pr-4 font-medium">Время</th>
                      <th className="py-2 pr-4 font-medium">Поле</th>
                      <th className="py-2 pr-4 font-medium">Применено</th>
                      <th className="py-2 font-medium">Проигравшие правила</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conflicts.map((c) => (
                      <tr key={c.id} className="border-b border-cardbg/50 hover:bg-mainbg align-top">
                        <td className="py-2 pr-4 text-primary/60 whitespace-nowrap">{new Date(c.detected_at).toLocaleString("ru")}</td>
                        <td className="py-2 pr-4 text-primary font-medium">{c.field_name}</td>
                        <td className="py-2 pr-4 text-green-700">{fmt(c.winning_value)}</td>
                        <td className="py-2 text-mistake text-[12px]">
                          {c.losing_writes.map((w, i) => (
                            <div key={i}>{w.rule_id.slice(0, 8)}… → {fmt(w.value)}</div>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
          {tab === "webhooks" && (
            <>
              <p className="text-[12px] text-primary/50 mb-3">
                Попытки доставки действия «Webhook» из правил. Цели во внутренней сети блокируются автоматически.
              </p>
              {webhooksQuery.isLoading && <p className="text-[13px] text-primary/40">Загрузка…</p>}
              {!webhooksQuery.isLoading && deliveries.length === 0 && (
                <p className="text-[13px] text-primary/40 text-center py-10">Доставок не зафиксировано</p>
              )}
              {deliveries.length > 0 && (
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-primary/50 text-left border-b border-cardbg">
                      <th className="py-2 pr-4 font-medium">Время</th>
                      <th className="py-2 pr-4 font-medium">URL</th>
                      <th className="py-2 pr-4 font-medium">Статус</th>
                      <th className="py-2 font-medium">Детали</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.map((d) => (
                      <tr key={d.id} className="border-b border-cardbg/50 hover:bg-mainbg align-top">
                        <td className="py-2 pr-4 text-primary/60 whitespace-nowrap">{new Date(d.created_at).toLocaleString("ru")}</td>
                        <td className="py-2 pr-4 text-primary font-medium truncate max-w-[280px]">{d.method} {d.url}</td>
                        <td className={cn("py-2 pr-4 font-medium", STATUS_CLASS[d.status] ?? "text-primary/60")}>
                          {STATUS_LABEL[d.status] ?? d.status}{d.status_code ? ` (${d.status_code})` : ""}
                        </td>
                        <td className="py-2 text-primary/50 text-[12px]">{d.error ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Rule card
   ════════════════════════════════════════════════════════════════ */
function RuleCard({ rule, appId, onEdit }: { rule: Rule; appId: string; onEdit: () => void; }) {
  const [showTest, setShowTest] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const updateMut = useUpdateRule(appId);
  const deleteMut = useDeleteRule(appId);

  const triggerLabel = TRIGGER_EVENTS.find((t) => t.value === rule.trigger.event)?.label ?? rule.trigger.event;

  return (
    <>
      <div className={cn("bg-white rounded-[12px] border px-5 py-4 flex items-start gap-4", rule.is_active ? "border-cardbg" : "border-cardbg opacity-60")}>
        {/* Active toggle */}
        <button
          onClick={() => updateMut.mutate({ ruleId: rule.id, body: { is_active: !rule.is_active } })}
          className={cn("mt-1 w-[38px] h-[22px] rounded-full shrink-0 transition-colors relative", rule.is_active ? "bg-cta" : "bg-cardbg")}
        >
          <span className={cn("absolute top-[3px] w-[16px] h-[16px] bg-white rounded-full shadow transition-transform", rule.is_active ? "translate-x-[18px]" : "translate-x-[3px]")} />
        </button>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[15px] font-semibold text-primary truncate">{rule.name}</span>
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#EBF4FF] text-cta shrink-0">{triggerLabel}</span>
            <span className="text-[11px] text-primary/40 shrink-0">пр. {rule.priority}</span>
          </div>
          {rule.description && (
            <p className="text-[13px] text-primary/60 truncate">{rule.description}</p>
          )}
          <p className="text-[12px] text-primary/40 mt-0.5">
            {rule.actions.length} действий · v{rule.version}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setShowTest(true)} className="h-[32px] px-3 rounded-[8px] border border-cardbg text-[13px] text-primary hover:bg-mainbg">
            Тест
          </button>
          <button onClick={() => setShowLogs(true)} className="h-[32px] px-3 rounded-[8px] border border-cardbg text-[13px] text-primary hover:bg-mainbg">
            Журнал
          </button>
          <button onClick={onEdit} className="h-[32px] px-3 rounded-[8px] border border-cardbg text-[13px] text-primary hover:bg-mainbg">
            Изменить
          </button>
          <button
            onClick={() => { if (confirm(`Удалить правило "${rule.name}"?`)) deleteMut.mutate(rule.id); }}
            className="h-[32px] px-3 rounded-[8px] border border-[#FDECEC] text-[13px] text-mistake hover:bg-[#FDECEC]"
          >
            Удалить
          </button>
        </div>
      </div>
      {showTest && <RuleTestModal appId={appId} rule={rule} onClose={() => setShowTest(false)} />}
      {showLogs && <RuleLogsDrawer appId={appId} rule={rule} onClose={() => setShowLogs(false)} />}
    </>
  );
}

/* ════════════════════════════════════════════════════════════════
   Main page
   ════════════════════════════════════════════════════════════════ */
export function RulesPage() {
  const [railModule, setRailModule] = useState<RailModule>("automation");
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [ruleTab, setRuleTab] = useState<"automation" | "autofill" | "validation">("automation");
  const [modal, setModal] = useState<{ open: boolean; rule: Rule | null }>({ open: false, rule: null });
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [showConflicts, setShowConflicts] = useState(false);

  const appsQuery = useApps();
  const app = useActiveApp(appsQuery.data?.items ?? []);
  const appId = app?.id ?? "";

  const entitiesQuery = useEntities(appId || undefined);
  const entities = entitiesQuery.data ?? [];

  const activeEntityId = selectedEntityId ?? entities[0]?.id ?? "";
  const activeEntity = entities.find((e) => e.id === activeEntityId) ?? null;
  const fields = activeEntity?.fields ?? [];

  const rulesQuery = useEntityRules(appId || undefined, activeEntityId || undefined);
  const allRules = rulesQuery.data ?? [];
  const rules = allRules.filter((r) => (r.rule_type ?? "automation") === ruleTab);

  function openCreate() { setModal({ open: true, rule: null }); }
  function openEdit(rule: Rule) { setModal({ open: true, rule }); }
  function closeModal() { setModal({ open: false, rule: null }); }

  const isAutofill = ruleTab === "autofill";
  const isValidationTab = ruleTab === "validation";

  const emptyText = isAutofill
    ? { icon: "✨", title: "Автозаполнений пока нет", desc: "Настройте автоматическое заполнение полей при создании или изменении записи.", btn: "Создать автозаполнение" }
    : isValidationTab
    ? { icon: "🛡️", title: "Проверок пока нет", desc: "Создайте проверку, чтобы отклонять сохранение записи, если условие не выполняется — например, если материала по рецепту не хватает.", btn: "Создать первую проверку" }
    : { icon: "⚡", title: "Правил пока нет", desc: "Создайте правило, чтобы автоматически реагировать на события: уведомления, изменение полей, вызов webhook.", btn: "Создать первое правило" };

  return (
    <div className="relative w-[1920px] h-[1080px] bg-white overflow-hidden">
      <Navbar />
      <IconRail active={railModule} onChange={setRailModule} onCollapse={() => setNavCollapsed((v) => !v)} collapsed={navCollapsed} />

      {/* ── Entity sidebar ── */}
      {!navCollapsed && <aside
        className="absolute bg-white overflow-y-auto border-r border-cardbg"
        style={{ left: 85, top: 70, width: 295, height: 1010 }}
      >
        {/* Tab switcher */}
        <div className="px-4 pt-4 pb-0 border-b border-cardbg">
          <div className="flex gap-1 mb-0">
            {([["automation", "Автоматизация"], ["autofill", "Автозаполнение"], ["validation", "Проверки"]] as const).map(([val, label]) => (
              <button
                key={val}
                onClick={() => setRuleTab(val)}
                className={cn(
                  "flex-1 py-2 text-[13px] font-medium rounded-t-[8px] transition-colors border-b-2",
                  ruleTab === val
                    ? "text-cta border-cta bg-[#EBF4FF]"
                    : "text-primary/50 border-transparent hover:text-primary hover:bg-mainbg"
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {entities.length === 0 && (
          <p className="px-5 py-4 text-[13px] text-primary/40">Нет таблиц — создайте их в разделе «База данных»</p>
        )}
        <nav className="py-2">
          {entities.map((ent) => (
            <button
              key={ent.id}
              onClick={() => setSelectedEntityId(ent.id)}
              className={cn(
                "w-full text-left px-5 py-[10px] text-[15px] transition-colors",
                ent.id === activeEntityId
                  ? "bg-[#EBF4FF] text-cta font-medium"
                  : "text-primary hover:bg-mainbg"
              )}
            >
              {ent.display_name}
            </button>
          ))}
        </nav>
      </aside>}

      {/* ── Rules list ── */}
      <main
        className="absolute bg-mainbg overflow-y-auto"
        style={{ left: navCollapsed ? 90 : 380, top: 70, width: navCollapsed ? 1250 : 960, height: 1010, transition: "left 0.2s, width 0.2s" }}
      >
        <div className="px-[40px] py-[28px]">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-[22px] font-bold text-primary">
                {activeEntity ? activeEntity.display_name : "Выберите таблицу"}
                {activeEntity && <span className="ml-2 text-[14px] font-normal text-primary/40">{isAutofill ? "· Автозаполнение" : isValidationTab ? "· Проверки" : "· Автоматизация"}</span>}
              </h2>
              {activeEntity && (
                <p className="text-[14px] text-primary/50 mt-1">
                  {rules.length === 0 ? "Нет записей" : `${rules.length} ${rules.length === 1 ? "правило" : rules.length < 5 ? "правила" : "правил"}`}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {appId && (
                <button
                  onClick={() => setShowConflicts(true)}
                  className="h-[38px] px-4 rounded-[10px] border border-cardbg text-[14px] text-primary hover:bg-mainbg"
                >
                  Журнал
                </button>
              )}
              {activeEntity && (
                <button
                  onClick={openCreate}
                  className="h-[38px] px-5 rounded-[10px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90 flex items-center gap-2"
                >
                  <span className="text-xl leading-none">+</span>
                  {isAutofill ? "Добавить автозаполнение" : isValidationTab ? "Добавить проверку" : "Добавить правило"}
                </button>
              )}
            </div>
          </div>

          {rulesQuery.isLoading && <p className="text-[14px] text-primary/40">Загрузка…</p>}

          {!rulesQuery.isLoading && rules.length === 0 && activeEntity && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="text-[48px] mb-4">{emptyText.icon}</div>
              <p className="text-[18px] font-semibold text-primary mb-2">{emptyText.title}</p>
              <p className="text-[14px] text-primary/50 mb-6 max-w-[400px]">{emptyText.desc}</p>
              <button
                onClick={openCreate}
                className="h-[40px] px-6 rounded-[10px] bg-cta text-white text-[15px] font-medium hover:bg-cta/90"
              >
                {emptyText.btn}
              </button>
            </div>
          )}

          <div className="flex flex-col gap-3">
            {rules.map((rule) => (
              <RuleCard key={rule.id} rule={rule} appId={appId} onEdit={() => openEdit(rule)} />
            ))}
          </div>
        </div>
      </main>

      <PreviewPanel projectName={app?.name ?? "Lesovik"} />

      {showConflicts && appId && (
        <ConflictsDrawer appId={appId} entityId={activeEntityId || undefined} onClose={() => setShowConflicts(false)} />
      )}

      {modal.open && activeEntity && !isAutofill && (
        <RuleModal
          rule={modal.rule}
          entityId={activeEntity.id}
          fields={fields}
          entities={entities}
          appId={appId}
          ruleType={isValidationTab ? "validation" : "automation"}
          onClose={closeModal}
        />
      )}
      {modal.open && activeEntity && isAutofill && (
        <AutofillModal
          rule={modal.rule}
          entityId={activeEntity.id}
          fields={fields}
          appId={appId}
          onClose={closeModal}
        />
      )}
    </div>
  );
}
