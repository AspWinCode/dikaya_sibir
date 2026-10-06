import { useState, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Navbar } from "@/components/layout/Navbar";
import { IconRail, type RailModule } from "@/components/layout/IconRail";
import { cn } from "@/lib/cn";
import { toSystemName } from "@/lib/toSystemName";
import { useApps } from "@/shared/hooks/useApps";
import { useActiveApp } from "@/shared/hooks/useActiveApp";
import {
  useEntities,
  useCreateEntity,
  useUpdateEntity,
  useDeleteEntity,
  useCreateField,
  useUpdateField,
  useDeleteField,
  useRelations,
  useCreateRelation,
  useUpdateRelation,
  useDeleteRelation,
} from "@/shared/hooks/useEntities";
import {
  useSequences,
  useCreateSequence,
  useUpdateSequence,
  useDeleteSequence,
  usePreviewNextSequenceValue,
} from "@/shared/hooks/useSequences";
import type {
  EntityRead,
  FieldCreate,
  FieldRead,
  FieldType,
  FieldUpdate,
  RelationCreate,
  RelationRead,
  RelationType,
  RelationUpdate,
} from "@/shared/api/entities";
import type { Sequence, SequenceCreate, SequenceUpdate } from "@/shared/api/sequences";

// ─────────────────────────────────────────────
// Field type metadata
// ─────────────────────────────────────────────

interface FieldTypeMeta {
  label: string;
  group: string;
  icon: (cls?: string) => JSX.Element;
}

const FIELD_TYPES: Record<FieldType, FieldTypeMeta> = {
  text:         { label: "Текст",            group: "Основные", icon: (c) => <IconText cls={c} /> },
  long_text:    { label: "Длинный текст",    group: "Основные", icon: (c) => <IconLongText cls={c} /> },
  rich_text:    { label: "Форматированный",  group: "Основные", icon: (c) => <IconRichText cls={c} /> },
  number:       { label: "Число",            group: "Основные", icon: (c) => <IconNumber cls={c} /> },
  decimal:      { label: "Десятичное",       group: "Основные", icon: (c) => <IconDecimal cls={c} /> },
  currency:     { label: "Валюта",           group: "Основные", icon: (c) => <IconCurrency cls={c} /> },
  boolean:      { label: "Булево",           group: "Основные", icon: (c) => <IconBoolean cls={c} /> },
  date:         { label: "Дата",             group: "Дата/Время", icon: (c) => <IconDate cls={c} /> },
  datetime:     { label: "Дата и время",     group: "Дата/Время", icon: (c) => <IconDatetime cls={c} /> },
  time:         { label: "Время",            group: "Дата/Время", icon: (c) => <IconTime cls={c} /> },
  select:       { label: "Список",           group: "Выбор", icon: (c) => <IconSelect cls={c} /> },
  multi_select: { label: "Множ. выбор",      group: "Выбор", icon: (c) => <IconMultiSelect cls={c} /> },
  file:         { label: "Файл",             group: "Медиа", icon: (c) => <IconFile cls={c} /> },
  image:        { label: "Изображение",      group: "Медиа", icon: (c) => <IconImage cls={c} /> },
  relation:     { label: "Связь",            group: "Связи", icon: (c) => <IconRelation cls={c} /> },
  lookup:       { label: "Lookup",           group: "Связи", icon: (c) => <IconLookup cls={c} /> },
  formula:      { label: "Формула",          group: "Вычисляемые", icon: (c) => <IconFormula cls={c} /> },
  signature:    { label: "Подпись (ЭП)",     group: "Вычисляемые", icon: (c) => <IconSignature cls={c} /> },
  url:          { label: "URL",              group: "Контакты", icon: (c) => <IconUrl cls={c} /> },
  email:        { label: "Email",            group: "Контакты", icon: (c) => <IconEmail cls={c} /> },
  phone:        { label: "Телефон",          group: "Контакты", icon: (c) => <IconPhone cls={c} /> },
  json:         { label: "JSON",             group: "Прочее", icon: (c) => <IconJson cls={c} /> },
};

const FIELD_TYPE_GROUPS = [
  "Основные",
  "Дата/Время",
  "Выбор",
  "Медиа",
  "Связи",
  "Вычисляемые",
  "Контакты",
  "Прочее",
];

const RELATION_LABELS: Record<RelationType, string> = {
  one_to_one:   "Один к одному",
  one_to_many:  "Один ко многим",
  many_to_many: "Многие ко многим",
};

const RELATION_BADGE: Record<RelationType | "many_to_one", string> = {
  one_to_one:   "1:1",
  one_to_many:  "1:N",
  many_to_one:  "N:1",
  many_to_many: "N:M",
};

function effectiveRelationType(r: RelationRead, activeEntityId: string): RelationType | "many_to_one" {
  if (r.from_entity_id === activeEntityId) return r.relation_type;
  if (r.relation_type === "one_to_many") return "many_to_one";
  return r.relation_type;
}

// ─────────────────────────────────────────────
// Formula helpers
// ─────────────────────────────────────────────

interface FormulaFn {
  label: string;
  name: string;
  syntax: string;
  desc: string;
  group: string;
}

const FORMULA_FNS: FormulaFn[] = [
  // Arithmetic
  { group: "Арифметика", name: "+",      label: "+",        syntax: "a + b",                desc: "Сложение" },
  { group: "Арифметика", name: "-",      label: "−",        syntax: "a - b",                desc: "Вычитание" },
  { group: "Арифметика", name: "*",      label: "×",        syntax: "a * b",                desc: "Умножение" },
  { group: "Арифметика", name: "/",      label: "÷",        syntax: "a / b",                desc: "Деление" },
  { group: "Арифметика", name: "%",      label: "%",        syntax: "a % b",                desc: "Остаток" },
  // Logic
  { group: "Логика", name: "IF",     label: "ЕСЛИ",     syntax: "IF(условие, тогда, иначе)", desc: "Условное выражение" },
  { group: "Логика", name: "AND",    label: "И",        syntax: "AND(a, b)",               desc: "Логическое И" },
  { group: "Логика", name: "OR",     label: "ИЛИ",      syntax: "OR(a, b)",                desc: "Логическое ИЛИ" },
  { group: "Логика", name: "NOT",    label: "НЕ",       syntax: "NOT(a)",                  desc: "Логическое НЕ" },
  // Aggregates
  { group: "Агрегаты", name: "SUM",   label: "СУММА",    syntax: "SUM(поле)",              desc: "Сумма связанных записей" },
  { group: "Агрегаты", name: "COUNT", label: "СЧЁТ",     syntax: "COUNT(поле)",            desc: "Количество связанных записей" },
  { group: "Агрегаты", name: "MIN",   label: "МИН",      syntax: "MIN(поле)",              desc: "Минимальное значение" },
  { group: "Агрегаты", name: "MAX",   label: "МАКС",     syntax: "MAX(поле)",              desc: "Максимальное значение" },
  { group: "Агрегаты", name: "AVG",   label: "СРЕДНЕЕ",  syntax: "AVG(поле)",              desc: "Среднее значение" },
  // Date
  { group: "Даты", name: "TODAY",    label: "СЕГОДНЯ",  syntax: "TODAY()",                 desc: "Текущая дата" },
  { group: "Даты", name: "YEAR",     label: "ГОД",      syntax: "YEAR(дата)",              desc: "Год из даты" },
  { group: "Даты", name: "MONTH",    label: "МЕСЯЦ",    syntax: "MONTH(дата)",             desc: "Месяц из даты" },
  { group: "Даты", name: "DAY",      label: "ДЕНЬ",     syntax: "DAY(дата)",               desc: "День из даты" },
  { group: "Даты", name: "DATEDIFF", label: "РАЗНДАТ",  syntax: "DATEDIFF(д1, д2, 'day')", desc: "Разница между датами" },
  // String
  { group: "Строки", name: "CONCAT",  label: "ОБЪЕД",    syntax: "CONCAT(a, b)",           desc: "Объединение строк" },
  { group: "Строки", name: "LEN",     label: "ДЛСТР",    syntax: "LEN(текст)",             desc: "Длина строки" },
  { group: "Строки", name: "LEFT",    label: "ЛЕВСИМВ",  syntax: "LEFT(текст, n)",         desc: "Первые N символов" },
  { group: "Строки", name: "RIGHT",   label: "ПРАВСИМВ", syntax: "RIGHT(текст, n)",        desc: "Последние N символов" },
  { group: "Строки", name: "UPPER",   label: "ПРОПИСН",  syntax: "UPPER(текст)",           desc: "В верхний регистр" },
  { group: "Строки", name: "LOWER",   label: "СТРОЧН",   syntax: "LOWER(текст)",           desc: "В нижний регистр" },
];
const FORMULA_GROUPS = ["Арифметика", "Логика", "Агрегаты", "Даты", "Строки"];

// ─────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────

export function DataSchemaPage() {
  const [railModule, setRailModule] = useState<RailModule>("data");
  const [navCollapsed, setNavCollapsed] = useState(false);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const appsQ   = useApps();
  const activeApp = useActiveApp(appsQ.data?.items ?? []);
  const appId   = activeApp?.id ?? "";

  const entitiesQ  = useEntities(appId || undefined);
  const relationsQ = useRelations(appId || undefined);
  const entities   = entitiesQ.data ?? [];
  const relations  = relationsQ.data ?? [];

  const createEntityM  = useCreateEntity(appId);
  const updateEntityM  = useUpdateEntity(appId);
  const deleteEntityM  = useDeleteEntity(appId);
  const createFieldM   = useCreateField(appId);
  const updateFieldM   = useUpdateField(appId);
  const deleteFieldM   = useDeleteField(appId);
  const createRelationM = useCreateRelation(appId);
  const updateRelationM = useUpdateRelation(appId);
  const deleteRelationM = useDeleteRelation(appId);

  const [activeEntityId, setActiveEntityId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"fields" | "relations" | "sequences">("fields");

  const sequencesQ     = useSequences(appId, activeEntityId ?? undefined);
  const sequences      = sequencesQ.data ?? [];
  const createSeqM     = useCreateSequence(appId, activeEntityId ?? "");
  const updateSeqM     = useUpdateSequence(appId, activeEntityId ?? "");
  const deleteSeqM     = useDeleteSequence(appId, activeEntityId ?? "");

  // Modal states
  const [entityModal, setEntityModal] = useState<{ mode: "create" | "edit"; entity?: EntityRead } | null>(null);
  const [fieldModal, setFieldModal]   = useState<{ mode: "create" | "edit"; field?: FieldRead } | null>(null);
  const [relationModal, setRelationModal] = useState(false);
  const [relationError, setRelationError] = useState<string | null>(null);
  const [editRelation, setEditRelation] = useState<RelationRead | null>(null);
  const [editRelationError, setEditRelationError] = useState<string | null>(null);
  const [deleteEntityId, setDeleteEntityId] = useState<string | null>(null);
  const [deleteFieldId, setDeleteFieldId]   = useState<{ entityId: string; fieldId: string } | null>(null);
  const [deleteRelationId, setDeleteRelationId] = useState<string | null>(null);
  const [seqModal, setSeqModal] = useState<{ mode: "create" | "edit"; seq?: Sequence } | null>(null);
  const [deleteSeqId, setDeleteSeqId] = useState<string | null>(null);

  const activeEntity = entities.find((e) => e.id === activeEntityId) ?? null;
  const entityRelations = relations.filter(
    (r) => r.from_entity_id === activeEntityId || r.to_entity_id === activeEntityId,
  );

  // Sort fields by display_order
  const sortedFields = activeEntity
    ? [...activeEntity.fields].sort((a, b) => a.display_order - b.display_order)
    : [];
  const systemFields = sortedFields.filter((f) => f.is_system);
  const userFields   = sortedFields.filter((f) => !f.is_system);

  return (
    <div className="relative w-[1920px] h-[1080px] bg-mainbg overflow-hidden">
      <Navbar />
      <IconRail
        active={railModule}
        onChange={setRailModule}
        onCollapse={() => setNavCollapsed((v) => !v)}
        collapsed={navCollapsed}
      />

      {/* ── Entity list sidebar ── */}
      {!navCollapsed && (
        <aside
          className="absolute bg-white border-r border-cardbg flex flex-col"
          style={{ left: 85, top: 70, width: 300, height: 1010 }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-cardbg shrink-0">
            <span className="text-[16px] font-semibold text-primary">Сущности</span>
            <button
              onClick={() => setEntityModal({ mode: "create" })}
              className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-mainbg text-cta"
              title="Создать сущность"
            >
              <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M8 3v10M3 8h10" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto py-1">
            {entitiesQ.isLoading && (
              <p className="px-4 py-6 text-[13px] text-primary/40 text-center">Загрузка…</p>
            )}
            {!entitiesQ.isLoading && entities.length === 0 && (
              <div className="px-4 py-8 text-center">
                <p className="text-[13px] text-primary/40 mb-3">Нет сущностей</p>
                <button
                  onClick={() => setEntityModal({ mode: "create" })}
                  className="text-[13px] text-cta hover:underline font-medium"
                >
                  Создать первую
                </button>
              </div>
            )}
            {entities.map((entity) => (
              <div
                key={entity.id}
                onClick={() => setActiveEntityId(entity.id)}
                className={cn(
                  "group flex items-center justify-between px-4 py-2.5 cursor-pointer transition-colors",
                  entity.id === activeEntityId
                    ? "bg-[#EBF4FF] text-cta"
                    : "text-primary hover:bg-mainbg",
                )}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-lg leading-none shrink-0">{entity.icon ?? "📋"}</span>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium truncate">{entity.display_name}</p>
                    <p className="text-[11px] opacity-50 truncate font-mono">{entity.slug}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  <button
                    onClick={(e) => { e.stopPropagation(); setEntityModal({ mode: "edit", entity }); }}
                    className="w-6 h-6 flex items-center justify-center rounded hover:bg-white/80 text-primary/60"
                    title="Изменить"
                  >
                    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M11 2l3 3-9 9H2v-3L11 2z" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                  {!entity.is_system && (
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteEntityId(entity.id); }}
                      className="w-6 h-6 flex items-center justify-center rounded hover:bg-white/80 text-[#D32F2F]/60"
                      title="Удалить"
                    >
                      <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M3 4h10M5 4V3h6v1M6 7v5M10 7v5M4 4l1 9h6l1-9" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-cardbg px-4 py-3 text-[12px] text-primary/40 shrink-0">
            Всего: {entities.length} сущностей
          </div>
        </aside>
      )}

      {/* ── Entity detail area ── */}
      <main
        className="absolute overflow-hidden flex flex-col"
        style={{
          left: navCollapsed ? 90 : 385,
          top: 70,
          width: navCollapsed ? 1830 : 1535,
          height: 1010,
          transition: "left 0.2s, width 0.2s",
        }}
      >
        {!activeEntity ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <svg viewBox="0 0 64 64" className="w-16 h-16 mb-4 text-primary/20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="8" y="8" width="48" height="48" rx="6" />
              <path d="M20 24h24M20 32h16M20 40h8" strokeLinecap="round" />
            </svg>
            <p className="text-[16px] font-semibold text-primary/40 mb-2">Выберите сущность</p>
            <p className="text-[13px] text-primary/30">или создайте новую в боковой панели</p>
          </div>
        ) : (
          <>
            {/* Entity header */}
            <div className="bg-white border-b border-cardbg px-6 py-4 shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{activeEntity.icon ?? "📋"}</span>
                  <div>
                    <h2 className="text-[20px] font-bold text-primary leading-tight">
                      {activeEntity.display_name}
                    </h2>
                    {activeEntity.description && (
                      <p className="text-[13px] text-primary/50 mt-0.5">{activeEntity.description}</p>
                    )}
                  </div>
                  {activeEntity.is_system && (
                    <span className="px-2 py-0.5 bg-mainbg text-primary/50 text-[11px] rounded-full border border-cardbg">
                      системная
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const appParam = searchParams.get("app");
                      const url = `/database?entity=${activeEntity.id}${appParam ? `&app=${appParam}` : ""}`;
                      navigate(url);
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] text-cta border border-cta/30 rounded-[8px] hover:bg-[#EBF4FF] transition-colors"
                  >
                    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <ellipse cx="8" cy="4" rx="5" ry="2" />
                      <path d="M3 4v8c0 1.1 2.24 2 5 2s5-.9 5-2V4" />
                      <path d="M3 8c0 1.1 2.24 2 5 2s5-.9 5-2" />
                    </svg>
                    Перейти к данным
                  </button>
                  <button
                    onClick={() => setEntityModal({ mode: "edit", entity: activeEntity })}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] text-primary border border-cardbg rounded-[8px] hover:bg-mainbg transition-colors"
                  >
                    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M11 2l3 3-9 9H2v-3L11 2z" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Изменить
                  </button>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex items-center gap-1 mt-4">
                {(["fields", "relations", "sequences"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={cn(
                      "px-4 py-1.5 rounded-[8px] text-[13px] font-medium transition-colors",
                      activeTab === tab
                        ? "bg-[#EBF4FF] text-cta"
                        : "text-primary/60 hover:bg-mainbg",
                    )}
                  >
                    {tab === "fields"
                      ? `Поля (${activeEntity.fields.length})`
                      : tab === "relations"
                      ? `Связи (${entityRelations.length})`
                      : `Последовательности (${sequences.length})`}
                  </button>
                ))}
              </div>
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-6">
              {activeTab === "fields" && (
                <FieldsTab
                  systemFields={systemFields}
                  userFields={userFields}
                  onAddField={() => setFieldModal({ mode: "create" })}
                  onEditField={(f) => setFieldModal({ mode: "edit", field: f })}
                  onDeleteField={(f) =>
                    setDeleteFieldId({ entityId: activeEntity.id, fieldId: f.id })
                  }
                />
              )}
              {activeTab === "relations" && (
                <RelationsTab
                  relations={entityRelations}
                  entities={entities}
                  activeEntityId={activeEntity.id}
                  onAddRelation={() => setRelationModal(true)}
                  onEditRelation={(r) => { setEditRelation(r); setEditRelationError(null); }}
                  onDeleteRelation={(r) => setDeleteRelationId(r.id)}
                />
              )}
              {activeTab === "sequences" && (
                <SequencesTab
                  sequences={sequences}
                  onAdd={() => setSeqModal({ mode: "create" })}
                  onEdit={(s) => setSeqModal({ mode: "edit", seq: s })}
                  onDelete={(s) => setDeleteSeqId(s.id)}
                />
              )}
            </div>
          </>
        )}
      </main>

      {/* ── Modals ── */}
      {entityModal && (
        <EntityModal
          mode={entityModal.mode}
          entity={entityModal.entity}
          onClose={() => setEntityModal(null)}
          onCreate={(data) =>
            createEntityM.mutate(data, { onSuccess: () => setEntityModal(null) })
          }
          onUpdate={(data) => {
            if (!entityModal.entity) return;
            updateEntityM.mutate(
              { entityId: entityModal.entity.id, body: data },
              { onSuccess: () => setEntityModal(null) },
            );
          }}
          saving={createEntityM.isPending || updateEntityM.isPending}
        />
      )}

      {fieldModal && activeEntity && (
        <FieldModal
          mode={fieldModal.mode}
          field={fieldModal.field}
          entity={activeEntity}
          entities={entities}
          onClose={() => setFieldModal(null)}
          onCreate={(data) => {
            // Relation fields must go through the relation endpoint so that a
            // metamodel.relation row is created (and the Relations tab shows it).
            if (
              data.field_type === "relation" &&
              (data.field_options?.target_entity_id as string | undefined)
            ) {
              createRelationM.mutate(
                {
                  from_entity_id: activeEntity.id,
                  to_entity_id: data.field_options!.target_entity_id as string,
                  relation_type: ((data.field_options?.relation_type as string) ?? "one_to_many") as RelationType,
                  from_field_name: data.name,
                },
                { onSuccess: () => setFieldModal(null) },
              );
            } else {
              createFieldM.mutate(
                { entityId: activeEntity.id, body: data },
                { onSuccess: () => setFieldModal(null) },
              );
            }
          }}
          onUpdate={(data) => {
            if (!fieldModal.field) return;
            updateFieldM.mutate(
              { entityId: activeEntity.id, fieldId: fieldModal.field.id, body: data },
              { onSuccess: () => setFieldModal(null) },
            );
          }}
          saving={createFieldM.isPending || updateRelationM.isPending || updateFieldM.isPending}
        />
      )}

      {relationModal && activeEntity && (
        <RelationModal
          entities={entities}
          fromEntityId={activeEntity.id}
          onClose={() => { setRelationModal(false); setRelationError(null); }}
          onCreate={(data) => {
            setRelationError(null);
            createRelationM.mutate(data, {
              onSuccess: () => { setRelationModal(false); setRelationError(null); },
              onError: (err: unknown) => {
                const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                setRelationError(detail ?? "Не удалось создать связь. Повторите попытку.");
              },
            });
          }}
          saving={createRelationM.isPending}
          error={relationError}
        />
      )}

      {editRelation && (
        <RelationEditModal
          relation={editRelation}
          entities={entities}
          onClose={() => { setEditRelation(null); setEditRelationError(null); }}
          onUpdate={(body) => {
            setEditRelationError(null);
            updateRelationM.mutate(
              { relationId: editRelation.id, body },
              {
                onSuccess: () => { setEditRelation(null); setEditRelationError(null); },
                onError: (err: unknown) => {
                  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                  setEditRelationError(detail ?? "Не удалось сохранить изменения.");
                },
              },
            );
          }}
          saving={updateRelationM.isPending}
          error={editRelationError}
        />
      )}

      {deleteEntityId && (
        <ConfirmModal
          title="Удалить сущность?"
          body="Все поля и данные этой сущности будут удалены безвозвратно."
          confirmLabel="Удалить"
          onClose={() => setDeleteEntityId(null)}
          onConfirm={() =>
            deleteEntityM.mutate(deleteEntityId, {
              onSuccess: () => {
                setDeleteEntityId(null);
                setActiveEntityId(null);
              },
            })
          }
          saving={deleteEntityM.isPending}
        />
      )}

      {deleteFieldId && (
        <ConfirmModal
          title="Удалить поле?"
          body="Данные в этом поле будут удалены безвозвратно."
          confirmLabel="Удалить"
          onClose={() => setDeleteFieldId(null)}
          onConfirm={() =>
            deleteFieldM.mutate(deleteFieldId, { onSuccess: () => setDeleteFieldId(null) })
          }
          saving={deleteFieldM.isPending}
        />
      )}

      {deleteRelationId && (
        <ConfirmModal
          title="Удалить связь?"
          body="Связь между сущностями будет удалена."
          confirmLabel="Удалить"
          onClose={() => setDeleteRelationId(null)}
          onConfirm={() =>
            deleteRelationM.mutate(deleteRelationId, {
              onSuccess: () => setDeleteRelationId(null),
            })
          }
          saving={deleteRelationM.isPending}
        />
      )}

      {seqModal && activeEntity && (
        <SequenceModal
          mode={seqModal.mode}
          seq={seqModal.seq}
          appId={appId}
          entityId={activeEntity.id}
          onClose={() => setSeqModal(null)}
          onCreate={(data) =>
            createSeqM.mutate(data, { onSuccess: () => setSeqModal(null) })
          }
          onUpdate={(data) => {
            if (!seqModal.seq) return;
            updateSeqM.mutate(
              { sequenceId: seqModal.seq.id, body: data },
              { onSuccess: () => setSeqModal(null) },
            );
          }}
          saving={createSeqM.isPending || updateSeqM.isPending}
        />
      )}

      {deleteSeqId && (
        <ConfirmModal
          title="Удалить последовательность?"
          body="Последовательность и её счётчик будут удалены безвозвратно."
          confirmLabel="Удалить"
          onClose={() => setDeleteSeqId(null)}
          onConfirm={() =>
            deleteSeqM.mutate(deleteSeqId, { onSuccess: () => setDeleteSeqId(null) })
          }
          saving={deleteSeqM.isPending}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// FieldsTab
// ─────────────────────────────────────────────

function FieldsTab({
  systemFields,
  userFields,
  onAddField,
  onEditField,
  onDeleteField,
}: {
  systemFields: FieldRead[];
  userFields: FieldRead[];
  onAddField: () => void;
  onEditField: (f: FieldRead) => void;
  onDeleteField: (f: FieldRead) => void;
}) {
  return (
    <div className="max-w-[900px]">
      {/* System fields */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <svg viewBox="0 0 16 16" className="w-4 h-4 text-primary/40" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="12" height="12" rx="2" />
            <path d="M6 8h4M8 6v4" strokeLinecap="round" />
          </svg>
          <span className="text-[12px] font-semibold text-primary/50 uppercase tracking-wider">
            Системные поля
          </span>
        </div>
        <div className="bg-mainbg/60 rounded-[12px] border border-cardbg overflow-hidden">
          {systemFields.map((f, i) => (
            <FieldRow
              key={f.id}
              field={f}
              isLast={i === systemFields.length - 1}
              onEdit={() => {}}
              onDelete={() => {}}
              isSystem
            />
          ))}
        </div>
      </div>

      {/* User fields */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <svg viewBox="0 0 16 16" className="w-4 h-4 text-primary/40" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 6h8M4 10h5" strokeLinecap="round" />
            </svg>
            <span className="text-[12px] font-semibold text-primary/50 uppercase tracking-wider">
              Пользовательские поля
            </span>
          </div>
          <button
            onClick={onAddField}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-cta text-white text-[13px] font-medium rounded-[8px] hover:bg-active transition-colors"
          >
            <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8 3v10M3 8h10" strokeLinecap="round" />
            </svg>
            Добавить поле
          </button>
        </div>
        {userFields.length === 0 ? (
          <div className="bg-white rounded-[12px] border border-dashed border-cardbg p-8 text-center">
            <p className="text-[13px] text-primary/40 mb-2">Нет пользовательских полей</p>
            <button
              onClick={onAddField}
              className="text-[13px] text-cta hover:underline font-medium"
            >
              Добавить первое поле
            </button>
          </div>
        ) : (
          <div className="bg-white rounded-[12px] border border-cardbg overflow-hidden">
            {userFields.map((f, i) => (
              <FieldRow
                key={f.id}
                field={f}
                isLast={i === userFields.length - 1}
                onEdit={() => onEditField(f)}
                onDelete={() => onDeleteField(f)}
                isSystem={false}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FieldRow({
  field,
  isLast,
  onEdit,
  onDelete,
  isSystem,
}: {
  field: FieldRead;
  isLast: boolean;
  onEdit: () => void;
  onDelete: () => void;
  isSystem: boolean;
}) {
  const meta = FIELD_TYPES[field.field_type as FieldType];
  return (
    <div
      className={cn(
        "group flex items-center gap-4 px-4 py-3 transition-colors",
        !isLast && "border-b border-cardbg",
        !isSystem && "hover:bg-mainbg/40 cursor-pointer",
        isSystem && "opacity-70",
      )}
      onClick={isSystem ? undefined : onEdit}
    >
      {/* Lock / drag icon */}
      <span className="w-4 shrink-0 flex items-center justify-center text-primary/30">
        {isSystem ? (
          <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="7" width="10" height="7" rx="1.5" />
            <path d="M5 7V5a3 3 0 016 0v2" />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M4 5h8M4 8h8M4 11h8" strokeLinecap="round" />
          </svg>
        )}
      </span>

      {/* Type icon */}
      <span className="w-5 h-5 text-cta shrink-0">
        {meta ? meta.icon("w-full h-full") : <IconDefault cls="w-full h-full" />}
      </span>

      {/* Names */}
      <div className="flex-1 min-w-0">
        <span className="text-[14px] font-medium text-primary">{field.display_name}</span>
        <span className="ml-2 font-mono text-[12px] text-primary/40">{field.name}</span>
      </div>

      {/* Type badge */}
      <span className="px-2 py-0.5 bg-mainbg text-primary/60 text-[11px] rounded-full border border-cardbg shrink-0">
        {meta?.label ?? field.field_type}
      </span>

      {/* Flags */}
      <div className="flex items-center gap-2 shrink-0">
        {field.is_required && (
          <span className="px-1.5 py-0.5 bg-red-50 text-red-600 text-[10px] rounded font-medium">обяз</span>
        )}
        {field.is_unique && (
          <span className="px-1.5 py-0.5 bg-purple-50 text-purple-600 text-[10px] rounded font-medium">уник</span>
        )}
        {field.is_indexed && (
          <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 text-[10px] rounded font-medium">индекс</span>
        )}
        {field.is_sensitive && (
          <span
            title="Значение шифруется (AES-256) и маскируется без явного права на чтение"
            className="px-1.5 py-0.5 bg-amber-50 text-amber-700 text-[10px] rounded font-medium"
          >
            🔒 шифр.
          </span>
        )}
      </div>

      {/* Actions */}
      {!isSystem && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-white text-primary/60"
          >
            <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11 2l3 3-9 9H2v-3L11 2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-white text-[#D32F2F]/60"
          >
            <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 4h10M5 4V3h6v1M6 7v5M10 7v5M4 4l1 9h6l1-9" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// RelationsTab
// ─────────────────────────────────────────────

function RelationsTab({
  relations,
  entities,
  activeEntityId,
  onAddRelation,
  onEditRelation,
  onDeleteRelation,
}: {
  relations: RelationRead[];
  entities: EntityRead[];
  activeEntityId: string;
  onAddRelation: () => void;
  onEditRelation: (r: RelationRead) => void;
  onDeleteRelation: (r: RelationRead) => void;
}) {
  const entityName = (id: string) =>
    entities.find((e) => e.id === id)?.display_name ?? id;

  return (
    <div className="max-w-[900px]">
      <div className="flex items-center justify-between mb-4">
        <p className="text-[13px] text-primary/60">
          Связи определяют отношения между сущностями (один к одному, один ко многим, многие ко многим).
        </p>
        <button
          onClick={onAddRelation}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-cta text-white text-[13px] font-medium rounded-[8px] hover:bg-active transition-colors shrink-0 ml-4"
        >
          <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3v10M3 8h10" strokeLinecap="round" />
          </svg>
          Добавить связь
        </button>
      </div>

      {relations.length === 0 ? (
        <div className="bg-white rounded-[12px] border border-dashed border-cardbg p-8 text-center">
          <p className="text-[13px] text-primary/40 mb-2">Нет связей</p>
          <button onClick={onAddRelation} className="text-[13px] text-cta hover:underline font-medium">
            Добавить первую связь
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-[12px] border border-cardbg overflow-hidden">
          {relations.map((r, i) => {
            const isFrom = r.from_entity_id === activeEntityId;
            return (
              <div
                key={r.id}
                className={cn(
                  "group flex items-center gap-4 px-4 py-3",
                  i < relations.length - 1 && "border-b border-cardbg",
                )}
              >
                <span
                  className={cn(
                    "px-2 py-0.5 text-[12px] font-bold rounded font-mono shrink-0",
                    "bg-cta/10 text-cta",
                  )}
                >
                  {RELATION_BADGE[effectiveRelationType(r, activeEntityId)]}
                </span>

                <div className="flex items-center gap-2 flex-1 min-w-0 text-[13px]">
                  <span className={cn("font-medium", isFrom ? "text-cta" : "text-primary/60")}>
                    {entityName(r.from_entity_id)}
                  </span>
                  <svg viewBox="0 0 24 24" className="w-4 h-4 text-primary/30 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M5 12h14M15 8l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className={cn("font-medium", !isFrom ? "text-cta" : "text-primary/60")}>
                    {entityName(r.to_entity_id)}
                  </span>
                  {r.display_name && (
                    <span className="ml-2 text-primary/40 truncate">— {r.display_name}</span>
                  )}
                </div>

                <span className="text-[12px] font-mono text-primary/40 shrink-0">
                  {r.from_field_name}
                  {r.to_field_name && ` → ${r.to_field_name}`}
                </span>

                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => onEditRelation(r)}
                    className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-mainbg text-primary/40 hover:text-primary"
                    title="Редактировать"
                  >
                    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M11 2l3 3-8 8H3v-3l8-8z" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                  <button
                    onClick={() => onDeleteRelation(r)}
                    className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-mainbg text-[#D32F2F]/60"
                    title="Удалить"
                  >
                    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M3 4h10M5 4V3h6v1M6 7v5M10 7v5M4 4l1 9h6l1-9" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// EntityModal
// ─────────────────────────────────────────────

function EntityModal({
  mode,
  entity,
  onClose,
  onCreate,
  onUpdate,
  saving,
}: {
  mode: "create" | "edit";
  entity?: EntityRead;
  onClose: () => void;
  onCreate: (d: { slug: string; display_name: string; name_plural?: string; description?: string; icon?: string; color?: string }) => void;
  onUpdate: (d: { display_name?: string; name_plural?: string; description?: string; icon?: string; color?: string }) => void;
  saving: boolean;
}) {
  const [slug, setSlug]           = useState(entity?.slug ?? "");
  const [slugTouched, setSlugTouched] = useState(false);
  const [displayName, setDisplayName] = useState(entity?.display_name ?? "");
  const namePlural = entity?.name_plural ?? "";
  const [description, setDescription] = useState(entity?.description ?? "");
  const [icon, setIcon]           = useState(entity?.icon ?? "📋");
  const color                     = entity?.color ?? "#00205F";

  const ICONS = ["📋", "📊", "👤", "🏢", "📦", "💼", "📝", "🔧", "🌿", "📁", "🎯", "⚙️"];

  const handleSubmit = () => {
    if (!displayName.trim()) return;
    if (mode === "create") {
      if (!slug.trim()) return;
      onCreate({ slug, display_name: displayName, name_plural: namePlural || undefined, description: description || undefined, icon, color });
    } else {
      onUpdate({ display_name: displayName, name_plural: namePlural || undefined, description: description || undefined, icon, color });
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-[20px] shadow-2xl w-[480px]">
        <div className="px-6 pt-6 pb-4 border-b border-cardbg">
          <h3 className="text-[18px] font-bold text-primary">
            {mode === "create" ? "Создать сущность" : "Редактировать сущность"}
          </h3>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Icon picker */}
          <div>
            <label className="block text-[12px] font-semibold text-primary/60 mb-2 uppercase tracking-wider">Иконка</label>
            <div className="flex flex-wrap gap-2">
              {ICONS.map((ic) => (
                <button
                  key={ic}
                  onClick={() => setIcon(ic)}
                  className={cn(
                    "w-9 h-9 flex items-center justify-center rounded-[8px] text-lg transition-all",
                    icon === ic ? "bg-[#EBF4FF] ring-2 ring-cta" : "bg-mainbg hover:bg-cardbg",
                  )}
                >
                  {ic}
                </button>
              ))}
            </div>
          </div>

          {/* Display name */}
          <FormField label="Отображаемое название *">
            <input
              value={displayName}
              onChange={(e) => {
                const v = e.target.value;
                setDisplayName(v);
                if (mode === "create" && !slugTouched) setSlug(toSystemName(v));
              }}
              placeholder="Например: Клиенты"
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
            />
          </FormField>

          {/* Slug (only create) */}
          {mode === "create" && (
            <FormField label="Системное имя *" hint="Заполняется автоматически, можно изменить">
              <input
                value={slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""));
                }}
                placeholder="clients"
                className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
              />
            </FormField>
          )}

          {/* Description */}
          <FormField label="Описание">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание сущности…"
              rows={2}
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta resize-none"
            />
          </FormField>
        </div>

        <div className="px-6 pb-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-[13px] text-primary/60 hover:text-primary transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || !displayName.trim() || (mode === "create" && !slug.trim())}
            className="px-5 py-2 bg-cta text-white text-[13px] font-medium rounded-[10px] hover:bg-active transition-colors disabled:opacity-50"
          >
            {saving ? "Сохранение…" : mode === "create" ? "Создать" : "Сохранить"}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─────────────────────────────────────────────
// FieldModal (multi-step: choose type → configure)
// ─────────────────────────────────────────────

function FieldModal({
  mode,
  field,
  entity,
  entities,
  onClose,
  onCreate,
  onUpdate,
  saving,
}: {
  mode: "create" | "edit";
  field?: FieldRead;
  entity: EntityRead;
  entities: EntityRead[];
  onClose: () => void;
  onCreate: (d: FieldCreate) => void;
  onUpdate: (d: FieldUpdate) => void;
  saving: boolean;
}) {
  const [step, setStep] = useState<"type" | "config">(mode === "edit" ? "config" : "type");
  const [fieldType, setFieldType] = useState<FieldType>(
    (field?.field_type as FieldType) ?? "text",
  );

  // Config state
  const [name, setName]               = useState(field?.name ?? "");
  const [nameTouched, setNameTouched] = useState(false);
  const [displayName, setDisplayName] = useState(field?.display_name ?? "");
  const [isRequired, setIsRequired]   = useState(field?.is_required ?? false);
  const [isUnique, setIsUnique]       = useState(field?.is_unique ?? false);
  const [isIndexed, setIsIndexed]     = useState(field?.is_indexed ?? false);
  const [isSensitive, setIsSensitive] = useState(field?.is_sensitive ?? false);
  const [fieldOptions, setFieldOptions] = useState<Record<string, unknown>>(
    field?.field_options ?? {},
  );
  const [formulaDef, setFormulaDef] = useState<Record<string, unknown>>(
    (field?.formula_definition as Record<string, unknown>) ?? {},
  );
  const [showFormulaEditor, setShowFormulaEditor] = useState(false);

  // Select/multi_select choices
  const choices: string[] = Array.isArray(fieldOptions.choices)
    ? (fieldOptions.choices as string[])
    : [];

  const setChoices = (c: string[]) =>
    setFieldOptions((prev) => ({ ...prev, choices: c }));

  const [newChoice, setNewChoice] = useState("");

  const handleSubmit = () => {
    if (!displayName.trim()) return;
    const opts = fieldType === "formula"
      ? { ...fieldOptions, formula_text: (formulaDef.text as string) ?? "" }
      : fieldOptions;

    if (mode === "create") {
      if (!name.trim()) return;
      onCreate({
        name,
        display_name: displayName,
        field_type: fieldType,
        is_required: isRequired,
        is_unique: isUnique,
        is_indexed: isIndexed,
        is_sensitive: isSensitive,
        field_options: opts,
        formula_definition: fieldType === "formula" ? formulaDef : undefined,
      });
    } else {
      onUpdate({
        display_name: displayName,
        is_required: isRequired,
        is_unique: isUnique,
        is_indexed: isIndexed,
        field_options: opts,
        formula_definition: fieldType === "formula" ? formulaDef : undefined,
      });
    }
  };

  if (showFormulaEditor) {
    return (
      <FormulaEditorModal
        entity={entity}
        entities={entities}
        definition={formulaDef}
        onClose={() => setShowFormulaEditor(false)}
        onSave={(def) => { setFormulaDef(def); setShowFormulaEditor(false); }}
      />
    );
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-[20px] shadow-2xl w-[560px] max-h-[85vh] flex flex-col">
        <div className="px-6 pt-6 pb-4 border-b border-cardbg shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-[18px] font-bold text-primary">
              {mode === "create" ? "Добавить поле" : `Редактировать: ${field?.display_name}`}
            </h3>
            {step === "config" && mode === "create" && (
              <button
                onClick={() => setStep("type")}
                className="flex items-center gap-1 text-[13px] text-primary/50 hover:text-primary"
              >
                <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M10 4L6 8l4 4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Изменить тип
              </button>
            )}
          </div>
          {step === "config" && (
            <div className="flex items-center gap-2 mt-2">
              <span className="w-5 h-5 text-cta">
                {FIELD_TYPES[fieldType]?.icon("w-full h-full")}
              </span>
              <span className="text-[13px] text-primary/60">
                {FIELD_TYPES[fieldType]?.label}
              </span>
            </div>
          )}
        </div>

        {step === "type" ? (
          /* ── Step 1: choose type ── */
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {FIELD_TYPE_GROUPS.map((group) => {
              const types = Object.entries(FIELD_TYPES).filter(
                ([, m]) => m.group === group,
              ) as [FieldType, FieldTypeMeta][];
              if (!types.length) return null;
              return (
                <div key={group} className="mb-5">
                  <p className="text-[11px] font-semibold text-primary/40 uppercase tracking-wider mb-2">
                    {group}
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {types.map(([type, meta]) => (
                      <button
                        key={type}
                        onClick={() => { setFieldType(type); setStep("config"); }}
                        className={cn(
                          "flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] border text-left transition-all",
                          "hover:border-cta hover:bg-[#EBF4FF]",
                          "border-cardbg bg-mainbg/40",
                        )}
                      >
                        <span className="w-5 h-5 text-cta shrink-0">
                          {meta.icon("w-full h-full")}
                        </span>
                        <span className="text-[13px] font-medium text-primary truncate">
                          {meta.label}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* ── Step 2: configure ── */
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {/* Display name */}
            <FormField label="Название *">
              <input
                value={displayName}
                onChange={(e) => {
                  const v = e.target.value;
                  setDisplayName(v);
                  if (mode === "create" && !nameTouched) setName(toSystemName(v));
                }}
                placeholder="Название поля"
                className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
              />
            </FormField>

            {/* Name (create only) */}
            {mode === "create" && (
              <FormField label="Системное имя *" hint="Заполняется автоматически, можно изменить">
                <input
                  value={name}
                  onChange={(e) => {
                    setNameTouched(true);
                    setName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""));
                  }}
                  placeholder="field_name"
                  className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
                />
              </FormField>
            )}

            {/* Type-specific config */}
            {(fieldType === "select" || fieldType === "multi_select") && (
              <div>
                <label className="block text-[12px] font-semibold text-primary/60 mb-2 uppercase tracking-wider">
                  Варианты выбора
                </label>
                <div className="space-y-1.5 mb-2">
                  {choices.map((c, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="flex-1 px-3 py-1.5 bg-mainbg border border-cardbg rounded-[6px] text-[13px] text-primary">
                        {c}
                      </span>
                      <button
                        onClick={() => setChoices(choices.filter((_, j) => j !== i))}
                        className="w-6 h-6 flex items-center justify-center text-primary/40 hover:text-[#D32F2F]"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    value={newChoice}
                    onChange={(e) => setNewChoice(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && newChoice.trim()) {
                        setChoices([...choices, newChoice.trim()]);
                        setNewChoice("");
                      }
                    }}
                    placeholder="Новый вариант…"
                    className="flex-1 px-3 py-1.5 border border-cardbg rounded-[6px] text-[13px] text-primary focus:outline-none focus:border-cta"
                  />
                  <button
                    onClick={() => {
                      if (newChoice.trim()) {
                        setChoices([...choices, newChoice.trim()]);
                        setNewChoice("");
                      }
                    }}
                    className="px-3 py-1.5 bg-cta text-white text-[13px] rounded-[6px] hover:bg-active"
                  >
                    +
                  </button>
                </div>
              </div>
            )}

            {fieldType === "relation" && (
              <div className="space-y-3">
                <FormField label="Связанная сущность">
                  <select
                    value={(fieldOptions.target_entity_id as string) ?? ""}
                    onChange={(e) =>
                      setFieldOptions((p) => ({ ...p, target_entity_id: e.target.value }))
                    }
                    className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
                  >
                    <option value="">Выберите сущность…</option>
                    {entities
                      .filter((e) => e.id !== entity.id)
                      .map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.icon ?? "📋"} {e.display_name}
                        </option>
                      ))}
                  </select>
                </FormField>
                {mode === "create" && (
                  <FormField label="Тип связи">
                    <select
                      value={(fieldOptions.relation_type as string) ?? "one_to_many"}
                      onChange={(e) =>
                        setFieldOptions((p) => ({ ...p, relation_type: e.target.value }))
                      }
                      className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
                    >
                      <option value="one_to_one">Один к одному (1:1)</option>
                      <option value="one_to_many">Один ко многим (1:N)</option>
                      <option value="many_to_many">Многие ко многим (N:M)</option>
                    </select>
                  </FormField>
                )}
              </div>
            )}

            {fieldType === "currency" && (
              <FormField label="Код валюты">
                <input
                  value={(fieldOptions.currency_code as string) ?? "RUB"}
                  onChange={(e) =>
                    setFieldOptions((p) => ({ ...p, currency_code: e.target.value.toUpperCase() }))
                  }
                  placeholder="RUB"
                  maxLength={3}
                  className="w-32 px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
                />
              </FormField>
            )}

            {fieldType === "formula" && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[12px] font-semibold text-primary/60 uppercase tracking-wider">
                    Формула
                  </label>
                  <button
                    onClick={() => setShowFormulaEditor(true)}
                    className="flex items-center gap-1.5 px-3 py-1 bg-cta text-white text-[12px] font-medium rounded-[6px] hover:bg-active"
                  >
                    <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M3 8h4l1-5 2 10 1-5h4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Открыть редактор
                  </button>
                </div>
                {formulaDef.text ? (
                  <div className="px-3 py-2 bg-mainbg border border-cardbg rounded-[8px] font-mono text-[13px] text-primary">
                    {formulaDef.text as string}
                  </div>
                ) : (
                  <div
                    onClick={() => setShowFormulaEditor(true)}
                    className="px-3 py-3 bg-mainbg border border-dashed border-cardbg rounded-[8px] text-[13px] text-primary/40 text-center cursor-pointer hover:border-cta hover:text-cta/60 transition-colors"
                  >
                    Нажмите для создания формулы
                  </div>
                )}
              </div>
            )}

            {(fieldType === "number" || fieldType === "decimal" || fieldType === "currency") && (
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Минимум">
                  <input
                    type="number"
                    value={(fieldOptions.min as number | undefined) ?? ""}
                    onChange={(e) =>
                      setFieldOptions((p) => ({
                        ...p,
                        min: e.target.value ? Number(e.target.value) : undefined,
                      }))
                    }
                    placeholder="—"
                    className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
                  />
                </FormField>
                <FormField label="Максимум">
                  <input
                    type="number"
                    value={(fieldOptions.max as number | undefined) ?? ""}
                    onChange={(e) =>
                      setFieldOptions((p) => ({
                        ...p,
                        max: e.target.value ? Number(e.target.value) : undefined,
                      }))
                    }
                    placeholder="—"
                    className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
                  />
                </FormField>
              </div>
            )}

            {fieldType === "text" && (
              <FormField label="Макс. длина">
                <input
                  type="number"
                  value={(fieldOptions.max_length as number | undefined) ?? ""}
                  onChange={(e) =>
                    setFieldOptions((p) => ({
                      ...p,
                      max_length: e.target.value ? Number(e.target.value) : undefined,
                    }))
                  }
                  placeholder="—"
                  className="w-32 px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
                />
              </FormField>
            )}

            {fieldType === "signature" && (
              <div className="px-4 py-3 bg-amber-50 border border-amber-200 rounded-[8px]">
                <p className="text-[13px] text-amber-800 font-medium">Подпись ЭП</p>
                <p className="text-[12px] text-amber-600 mt-0.5">
                  Подпись электронного документа будет реализована в очереди 3.
                </p>
              </div>
            )}

            {/* Flags */}
            <div className="pt-2 border-t border-cardbg space-y-2">
              <Toggle label="Обязательное" value={isRequired} onChange={setIsRequired} />
              <Toggle
                label="Уникальное"
                value={isUnique}
                onChange={(v) => { setIsUnique(v); if (v) setIsSensitive(false); }}
              />
              <Toggle label="Индексировать" value={isIndexed} onChange={setIsIndexed} />
              {mode === "create" && (
                <>
                  <Toggle
                    label="🔒 Чувствительное (шифровать AES-256)"
                    value={isSensitive}
                    onChange={(v) => { setIsSensitive(v); if (v) setIsUnique(false); }}
                  />
                  {isSensitive && (
                    <p className="text-[12px] text-amber-600">
                      Значение будет зашифровано в базе и скрыто (маскировано) для ролей без
                      явного права на чтение этого поля. По зашифрованному полю нельзя
                      фильтровать, сортировать или искать. Настройку нельзя изменить после
                      создания поля.
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {step === "config" && (
          <div className="px-6 pb-6 flex justify-end gap-2 border-t border-cardbg pt-4 shrink-0">
            <button
              onClick={onClose}
              className="px-4 py-2 text-[13px] text-primary/60 hover:text-primary transition-colors"
            >
              Отмена
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving || !displayName.trim() || (mode === "create" && !name.trim())}
              className="px-5 py-2 bg-cta text-white text-[13px] font-medium rounded-[10px] hover:bg-active transition-colors disabled:opacity-50"
            >
              {saving ? "Сохранение…" : mode === "create" ? "Добавить" : "Сохранить"}
            </button>
          </div>
        )}
      </div>
    </ModalOverlay>
  );
}

// ─────────────────────────────────────────────
// FormulaEditorModal — visual formula builder
// ─────────────────────────────────────────────

function FormulaEditorModal({
  entity,
  entities,
  definition,
  onClose,
  onSave,
}: {
  entity: EntityRead;
  entities: EntityRead[];
  definition: Record<string, unknown>;
  onClose: () => void;
  onSave: (def: Record<string, unknown>) => void;
}) {
  const [formulaText, setFormulaText] = useState((definition.text as string) ?? "");
  const [activeFnGroup, setActiveFnGroup] = useState(FORMULA_GROUPS[0]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const insertAtCursor = (text: string) => {
    const el = textareaRef.current;
    if (!el) {
      setFormulaText((f) => f + text);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const newVal = formulaText.slice(0, start) + text + formulaText.slice(end);
    setFormulaText(newVal);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + text.length, start + text.length);
    });
  };

  const insertFn = (fn: FormulaFn) => {
    if (["+", "-", "*", "/", "%"].includes(fn.name)) {
      insertAtCursor(` ${fn.name} `);
    } else {
      insertAtCursor(`${fn.name}(`);
    }
  };

  const insertField = (fieldName: string, entitySlug?: string) => {
    const ref = entitySlug ? `{${entitySlug}.${fieldName}}` : `{${fieldName}}`;
    insertAtCursor(ref);
  };

  const fnsInGroup = FORMULA_FNS.filter((f) => f.group === activeFnGroup);

  // Parse tokens for display (simple color-coding)
  const tokens = tokenizeFormula(formulaText);

  const handleSave = () => {
    onSave({
      text: formulaText,
      updated_at: new Date().toISOString(),
    });
  };

  // Related entities (via relation fields in entity)
  const relatedEntityIds = entity.fields
    .filter((f) => f.field_type === "relation" && f.field_options.target_entity_id)
    .map((f) => f.field_options.target_entity_id as string);
  const relatedEntities = entities.filter((e) => relatedEntityIds.includes(e.id));

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-[20px] shadow-2xl flex flex-col" style={{ width: 900, maxHeight: "90vh" }}>
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-cardbg shrink-0">
          <h3 className="text-[18px] font-bold text-primary">Редактор формул</h3>
          <p className="text-[13px] text-primary/50 mt-0.5">
            Кликайте по функциям и полям для вставки, или пишите формулу вручную
          </p>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Left: function categories + functions */}
          <div className="w-[260px] border-r border-cardbg flex flex-col shrink-0">
            {/* Category tabs */}
            <div className="flex flex-col py-2 border-b border-cardbg">
              {FORMULA_GROUPS.map((g) => (
                <button
                  key={g}
                  onClick={() => setActiveFnGroup(g)}
                  className={cn(
                    "text-left px-4 py-1.5 text-[13px] font-medium transition-colors",
                    activeFnGroup === g
                      ? "bg-[#EBF4FF] text-cta"
                      : "text-primary/60 hover:bg-mainbg",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
            {/* Function list */}
            <div className="flex-1 overflow-y-auto py-2">
              {fnsInGroup.map((fn) => (
                <button
                  key={fn.name}
                  onClick={() => insertFn(fn)}
                  className="w-full text-left px-4 py-2 hover:bg-mainbg transition-colors group"
                >
                  <div className="flex items-baseline gap-2">
                    <span className="text-[13px] font-mono font-semibold text-cta group-hover:text-active">
                      {fn.label}
                    </span>
                  </div>
                  <p className="text-[11px] text-primary/40 mt-0.5 font-mono">{fn.syntax}</p>
                  <p className="text-[11px] text-primary/50 mt-0.5">{fn.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Center: formula input + token preview */}
          <div className="flex-1 flex flex-col min-w-0 p-4 gap-3">
            {/* Token preview */}
            {formulaText && (
              <div className="px-3 py-2 bg-mainbg border border-cardbg rounded-[8px] min-h-[36px] flex flex-wrap gap-1 items-center">
                {tokens.map((tok, i) => (
                  <span
                    key={i}
                    className={cn(
                      "text-[13px] font-mono",
                      tok.type === "fn"      && "text-cta font-semibold",
                      tok.type === "field"   && "px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[12px]",
                      tok.type === "op"      && "text-purple-600 font-bold",
                      tok.type === "literal" && "text-green-700",
                      tok.type === "other"   && "text-primary/70",
                    )}
                  >
                    {tok.value}
                  </span>
                ))}
              </div>
            )}

            {/* Text input */}
            <textarea
              ref={textareaRef}
              value={formulaText}
              onChange={(e) => setFormulaText(e.target.value)}
              placeholder="IF({status} == 'active', {amount} * {rate}, 0)"
              rows={4}
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] font-mono text-[14px] text-primary focus:outline-none focus:border-cta resize-none"
            />

            {/* Quick operators */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[11px] text-primary/40 font-semibold uppercase tracking-wider mr-1">Операторы:</span>
              {["()", "+", "-", "*", "/", "==", "!=", ">", "<", ">=", "<="].map((op) => (
                <button
                  key={op}
                  onClick={() => insertAtCursor(op === "()" ? "()" : ` ${op} `)}
                  className="px-2 py-0.5 bg-mainbg border border-cardbg rounded text-[12px] font-mono text-primary hover:border-cta hover:text-cta transition-colors"
                >
                  {op}
                </button>
              ))}
            </div>

            {/* Formula help */}
            <div className="text-[12px] text-primary/40 space-y-1 border-t border-cardbg pt-3">
              <p><span className="font-mono text-blue-600">{"{field}"}</span> — ссылка на поле текущей сущности</p>
              <p><span className="font-mono text-blue-600">{"{entity.field}"}</span> — ссылка на поле связанной сущности</p>
              <p>Строки: <span className="font-mono text-green-700">&apos;значение&apos;</span> · Числа: <span className="font-mono text-green-700">42</span> · Булево: <span className="font-mono text-green-700">true / false</span></p>
            </div>
          </div>

          {/* Right: fields */}
          <div className="w-[220px] border-l border-cardbg flex flex-col shrink-0">
            <div className="px-4 py-2.5 border-b border-cardbg">
              <p className="text-[12px] font-semibold text-primary/50 uppercase tracking-wider">
                Поля
              </p>
            </div>
            <div className="flex-1 overflow-y-auto">
              {/* Current entity */}
              <div className="px-4 pt-3 pb-1">
                <p className="text-[11px] font-semibold text-cta mb-1.5">
                  {entity.icon ?? "📋"} {entity.display_name}
                </p>
                {entity.fields
                  .sort((a, b) => a.display_order - b.display_order)
                  .map((f) => (
                    <button
                      key={f.id}
                      onClick={() => insertField(f.name)}
                      className="w-full text-left flex items-center gap-1.5 px-2 py-1 rounded hover:bg-mainbg transition-colors"
                    >
                      <span className="w-3.5 h-3.5 text-cta shrink-0">
                        {FIELD_TYPES[f.field_type as FieldType]?.icon("w-full h-full") ?? <IconDefault cls="w-full h-full" />}
                      </span>
                      <span className="text-[12px] font-mono text-primary/70 truncate">{f.name}</span>
                    </button>
                  ))}
              </div>

              {/* Related entities */}
              {relatedEntities.map((re) => (
                <div key={re.id} className="px-4 pt-3 pb-1 border-t border-cardbg">
                  <p className="text-[11px] font-semibold text-primary/50 mb-1.5">
                    {re.icon ?? "📋"} {re.display_name}
                  </p>
                  {re.fields
                    .filter((f) => !f.is_system)
                    .map((f) => (
                      <button
                        key={f.id}
                        onClick={() => insertField(f.name, re.slug)}
                        className="w-full text-left flex items-center gap-1.5 px-2 py-1 rounded hover:bg-mainbg transition-colors"
                      >
                        <span className="w-3.5 h-3.5 text-primary/40 shrink-0">
                          {FIELD_TYPES[f.field_type as FieldType]?.icon("w-full h-full") ?? <IconDefault cls="w-full h-full" />}
                        </span>
                        <span className="text-[12px] font-mono text-primary/60 truncate">{f.name}</span>
                      </button>
                    ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-cardbg flex justify-between items-center shrink-0">
          <button
            onClick={() => setFormulaText("")}
            className="text-[13px] text-primary/40 hover:text-primary/60"
          >
            Очистить
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-[13px] text-primary/60 hover:text-primary"
            >
              Отмена
            </button>
            <button
              onClick={handleSave}
              className="px-5 py-2 bg-cta text-white text-[13px] font-medium rounded-[10px] hover:bg-active"
            >
              Применить
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─────────────────────────────────────────────
// RelationModal
// ─────────────────────────────────────────────

function RelationModal({
  entities,
  fromEntityId,
  onClose,
  onCreate,
  saving,
  error,
}: {
  entities: EntityRead[];
  fromEntityId: string;
  onClose: () => void;
  onCreate: (d: RelationCreate) => void;
  saving: boolean;
  error?: string | null;
}) {
  const [toEntityId, setToEntityId]       = useState("");
  const [relationType, setRelationType]   = useState<RelationType>("one_to_many");
  const [displayName, setDisplayName]     = useState("");
  const [fromFieldName, setFromFieldName] = useState("");
  const [toFieldName, setToFieldName]     = useState("");
  const [customFields, setCustomFields]   = useState(false);

  const fromEntity = entities.find((e) => e.id === fromEntityId);
  const toEntity   = entities.find((e) => e.id === toEntityId);

  // Auto-suggest field names based on relation type and selected entity slug
  const suggestedFrom = toEntity
    ? relationType === "many_to_many"
      ? toEntity.slug
      : `${toEntity.slug}_id`
    : "";
  const suggestedTo = fromEntity
    ? relationType === "many_to_many"
      ? fromEntity.slug
      : `${fromEntity.slug}_id`
    : "";

  const effectiveFromField = customFields ? fromFieldName : suggestedFrom;
  const effectiveToField   = customFields ? toFieldName   : (relationType === "many_to_many" ? suggestedTo : toFieldName);

  const handleEntityChange = (id: string) => {
    setToEntityId(id);
    setFromFieldName("");
    setToFieldName("");
  };

  const handleTypeChange = (t: RelationType) => {
    setRelationType(t);
    setFromFieldName("");
    setToFieldName("");
  };

  const handleSubmit = () => {
    if (!toEntityId || !effectiveFromField.trim()) return;
    // many_to_many always needs reverse field
    const reverseField = relationType === "many_to_many"
      ? (effectiveToField || suggestedTo)
      : (effectiveToField || undefined);
    onCreate({
      from_entity_id: fromEntityId,
      to_entity_id: toEntityId,
      relation_type: relationType,
      from_field_name: effectiveFromField,
      to_field_name: reverseField,
      display_name: displayName || undefined,
    });
  };

  const RELATION_DESCRIPTIONS: Record<RelationType, string> = {
    one_to_one:   "Каждая запись A связана ровно с одной записью B",
    one_to_many:  "Одна запись A связана с несколькими записями B",
    many_to_many: "Любая запись A может быть связана с любым числом записей B",
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-[20px] shadow-2xl w-[520px]">
        <div className="px-6 pt-6 pb-4 border-b border-cardbg">
          <h3 className="text-[18px] font-bold text-primary">Добавить связь</h3>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Тип связи */}
          <div>
            <label className="block text-[12px] font-semibold text-primary/60 mb-2 uppercase tracking-wider">
              Тип связи
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(["one_to_one", "one_to_many", "many_to_many"] as RelationType[]).map((t) => (
                <button
                  key={t}
                  onClick={() => handleTypeChange(t)}
                  className={cn(
                    "py-3 px-3 rounded-[10px] border text-center transition-all",
                    relationType === t
                      ? "border-cta bg-[#EBF4FF]"
                      : "border-cardbg hover:border-cta/50",
                  )}
                >
                  <RelationDiagram type={t} active={relationType === t} />
                  <div className={cn("font-mono font-bold text-[13px] mt-1.5", relationType === t ? "text-cta" : "text-primary/60")}>
                    {RELATION_BADGE[t]}
                  </div>
                  <div className={cn("text-[11px] mt-0.5", relationType === t ? "text-cta/80" : "text-primary/40")}>
                    {RELATION_LABELS[t]}
                  </div>
                </button>
              ))}
            </div>
            <p className="mt-2 text-[12px] text-primary/50 px-1">
              {RELATION_DESCRIPTIONS[relationType]}
            </p>
          </div>

          {/* Связанная сущность */}
          <FormField label="Связанная сущность *">
            <select
              value={toEntityId}
              onChange={(e) => handleEntityChange(e.target.value)}
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
            >
              <option value="">Выберите сущность…</option>
              {entities.filter((e) => e.id !== fromEntityId).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.icon ?? "📋"} {e.display_name}
                </option>
              ))}
            </select>
          </FormField>

          {/* Визуальная схема связи */}
          {toEntity && (
            <div className="bg-mainbg rounded-[10px] border border-cardbg px-4 py-3">
              <div className="flex items-center gap-2 text-[13px]">
                <span className="font-medium text-primary">
                  {fromEntity?.icon ?? "📋"} {fromEntity?.display_name}
                </span>
                <span className="font-mono text-[11px] text-primary/40 bg-white px-1.5 py-0.5 rounded border border-cardbg">
                  {effectiveFromField || suggestedFrom || "…"}
                </span>
                <svg viewBox="0 0 32 10" className="w-8 text-primary/30" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M0 5h28M24 2l4 3-4 3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {relationType === "many_to_many" && (
                  <span className="font-mono text-[11px] text-primary/40 bg-white px-1.5 py-0.5 rounded border border-cardbg">
                    {effectiveToField || suggestedTo || "…"}
                  </span>
                )}
                <span className="font-medium text-primary">
                  {toEntity.icon ?? "📋"} {toEntity.display_name}
                </span>
              </div>
              <p className="text-[11px] text-primary/40 mt-1.5">
                {relationType === "many_to_many"
                  ? `Поля «${effectiveFromField || suggestedFrom}» и «${effectiveToField || suggestedTo}» будут созданы автоматически`
                  : `Поле «${effectiveFromField || suggestedFrom}» будет создано автоматически`}
              </p>
            </div>
          )}

          {/* Название */}
          <FormField label="Название связи">
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Необязательно"
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
            />
          </FormField>

          {/* Кастомные имена полей */}
          <div>
            <button
              onClick={() => setCustomFields((v) => !v)}
              className="flex items-center gap-1.5 text-[12px] text-primary/50 hover:text-cta transition-colors"
            >
              <svg
                viewBox="0 0 12 12"
                className={cn("w-3 h-3 transition-transform", customFields && "rotate-90")}
                fill="currentColor"
              >
                <path d="M3 2l5 4-5 4V2z" />
              </svg>
              Изменить имена полей
            </button>
            {customFields && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <FormField label={`Поле на «${fromEntity?.display_name ?? "…"}»`}>
                  <input
                    value={fromFieldName || suggestedFrom}
                    onChange={(e) =>
                      setFromFieldName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))
                    }
                    placeholder={suggestedFrom}
                    className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
                  />
                </FormField>
                {relationType !== "one_to_one" && (
                  <FormField
                    label={
                      relationType === "many_to_many"
                        ? `Поле на «${toEntity?.display_name ?? "…"}»`
                        : "Обратное поле (опц.)"
                    }
                  >
                    <input
                      value={toFieldName || (relationType === "many_to_many" ? suggestedTo : "")}
                      onChange={(e) =>
                        setToFieldName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))
                      }
                      placeholder={relationType === "many_to_many" ? suggestedTo : "—"}
                      className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
                    />
                  </FormField>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="px-6 pb-6 border-t border-cardbg pt-4">
          {error && (
            <p className="text-[12px] text-red-500 mb-3">{error}</p>
          )}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-[13px] text-primary/60 hover:text-primary">
              Отмена
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving || !toEntityId || !effectiveFromField}
              className="px-5 py-2 bg-cta text-white text-[13px] font-medium rounded-[10px] hover:bg-active disabled:opacity-50"
            >
              {saving ? "Создание…" : "Создать связь"}
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─────────────────────────────────────────────
// RelationEditModal
// ─────────────────────────────────────────────

function RelationEditModal({
  relation,
  entities,
  onClose,
  onUpdate,
  saving,
  error,
}: {
  relation: RelationRead;
  entities: EntityRead[];
  onClose: () => void;
  onUpdate: (body: RelationUpdate) => void;
  saving: boolean;
  error?: string | null;
}) {
  const fromEntity = entities.find((e) => e.id === relation.from_entity_id);
  const toEntity   = entities.find((e) => e.id === relation.to_entity_id);

  const [displayName,   setDisplayName]   = useState(relation.display_name ?? "");
  const [fromFieldName, setFromFieldName] = useState(relation.from_field_name);
  const [toFieldName,   setToFieldName]   = useState(relation.to_field_name ?? "");

  const handleSubmit = () => {
    const body: RelationUpdate = {};
    if (displayName !== (relation.display_name ?? "")) body.display_name = displayName || null;
    if (fromFieldName !== relation.from_field_name) body.from_field_name = fromFieldName;
    if (toFieldName !== (relation.to_field_name ?? "")) body.to_field_name = toFieldName || null;
    onUpdate(body);
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-[20px] shadow-2xl w-[480px]">
        <div className="px-6 pt-6 pb-4 border-b border-cardbg">
          <h3 className="text-[18px] font-bold text-primary">Редактировать связь</h3>
          <p className="text-[12px] text-primary/50 mt-1">
            Тип и сущности изменить нельзя — только имена полей и название.
          </p>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Readonly: тип + сущности */}
          <div className="flex items-center gap-3 px-3 py-2.5 bg-mainbg rounded-[10px]">
            <span className="px-2 py-0.5 text-[12px] font-bold font-mono rounded bg-cta/10 text-cta shrink-0">
              {RELATION_BADGE[relation.relation_type]}
            </span>
            <span className="text-[13px] font-medium text-primary">
              {fromEntity?.display_name ?? "…"}
            </span>
            <svg viewBox="0 0 24 24" className="w-4 h-4 text-primary/30 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M5 12h14M15 8l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="text-[13px] font-medium text-primary">
              {toEntity?.display_name ?? "…"}
            </span>
          </div>

          {/* display_name */}
          <FormField label="Название связи (опц.)">
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Например: Менеджер по клиентам"
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] text-primary focus:outline-none focus:border-cta"
            />
          </FormField>

          {/* from_field_name */}
          <FormField label={`Поле на «${fromEntity?.display_name ?? "…"}»`}>
            <input
              value={fromFieldName}
              onChange={(e) => setFromFieldName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
              className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
            />
          </FormField>

          {/* to_field_name */}
          {relation.to_field_name !== null && (
            <FormField label={`Поле на «${toEntity?.display_name ?? "…"}»`}>
              <input
                value={toFieldName}
                onChange={(e) => setToFieldName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                className="w-full px-3 py-2 border border-cardbg rounded-[8px] text-[14px] font-mono text-primary focus:outline-none focus:border-cta"
              />
            </FormField>
          )}
        </div>

        <div className="px-6 pb-6 border-t border-cardbg pt-4">
          {error && <p className="text-[12px] text-red-500 mb-3">{error}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-[13px] text-primary/60 hover:text-primary">
              Отмена
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving || !fromFieldName}
              className="px-5 py-2 bg-cta text-white text-[13px] font-medium rounded-[10px] hover:bg-active disabled:opacity-50"
            >
              {saving ? "Сохранение…" : "Сохранить"}
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─────────────────────────────────────────────
// RelationDiagram — mini SVG icon per type
// ─────────────────────────────────────────────

function RelationDiagram({ type, active }: { type: RelationType; active: boolean }) {
  const c = active ? "#00205F" : "#CBD5E1";
  if (type === "one_to_one") return (
    <svg viewBox="0 0 40 16" className="w-10 h-4 mx-auto">
      <rect x="1" y="4" width="10" height="8" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <path d="M12 8h16" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="6" x2="12" y2="10" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="28" y1="6" x2="28" y2="10" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <rect x="29" y="4" width="10" height="8" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
    </svg>
  );
  if (type === "one_to_many") return (
    <svg viewBox="0 0 40 20" className="w-10 h-5 mx-auto">
      <rect x="1" y="6" width="10" height="8" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <path d="M12 10h10" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="8" x2="12" y2="12" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <path d="M22 10l-4-4M22 10l-4 4" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <rect x="23" y="1" width="10" height="6" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <rect x="23" y="9" width="10" height="6" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <path d="M22 4h1M22 12h1" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
  return (
    <svg viewBox="0 0 40 20" className="w-10 h-5 mx-auto">
      <rect x="1" y="1" width="10" height="6" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <rect x="1" y="9" width="10" height="6" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <path d="M11 4h7M11 12h7" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
      <path d="M18 4l-3-3M18 4l-3 3M18 12l-3-3M18 12l-3 3" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
      <path d="M22 4h7M22 12h7" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
      <path d="M22 4l3-3M22 4l3 3M22 12l3-3M22 12l3 3" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
      <rect x="29" y="1" width="10" height="6" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
      <rect x="29" y="9" width="10" height="6" rx="2" fill={c} opacity="0.2" stroke={c} strokeWidth="1.2" />
    </svg>
  );
}

// ─────────────────────────────────────────────
// Utility components
// ─────────────────────────────────────────────

function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {children}
    </div>
  );
}

function ConfirmModal({
  title,
  body,
  confirmLabel,
  onClose,
  onConfirm,
  saving,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  onClose: () => void;
  onConfirm: () => void;
  saving: boolean;
}) {
  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-[20px] shadow-2xl w-[360px] p-6">
        <h3 className="text-[16px] font-bold text-primary mb-2">{title}</h3>
        <p className="text-[13px] text-primary/60 mb-5">{body}</p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-[13px] text-primary/60 hover:text-primary">
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={saving}
            className="px-4 py-2 bg-[#D32F2F] text-white text-[13px] font-medium rounded-[10px] hover:bg-red-700 disabled:opacity-50"
          >
            {saving ? "Удаление…" : confirmLabel}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

function FormField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <label className="text-[12px] font-semibold text-primary/60 uppercase tracking-wider">
          {label}
        </label>
        {hint && <span className="text-[11px] text-primary/40">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[13px] text-primary">{label}</span>
      <button
        onClick={() => onChange(!value)}
        className={cn(
          "w-10 h-5 rounded-full transition-colors relative",
          value ? "bg-cta" : "bg-cardbg",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all",
            value ? "left-5" : "left-0.5",
          )}
        />
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────
// Formula tokenizer (simple)
// ─────────────────────────────────────────────

type TokenType = "fn" | "field" | "op" | "literal" | "other";
interface Token { type: TokenType; value: string }

function tokenizeFormula(text: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  const FNS = new Set(FORMULA_FNS.map((f) => f.name).filter((n) => n.length > 1));
  while (i < text.length) {
    // Skip whitespace
    if (text[i] === " " || text[i] === "\t") {
      tokens.push({ type: "other", value: text[i] });
      i++;
      continue;
    }
    // Field reference {name} or {entity.field}
    if (text[i] === "{") {
      const end = text.indexOf("}", i);
      if (end !== -1) {
        tokens.push({ type: "field", value: text.slice(i, end + 1) });
        i = end + 1;
        continue;
      }
    }
    // String literal
    if (text[i] === "'" || text[i] === '"') {
      const q = text[i];
      let j = i + 1;
      while (j < text.length && text[j] !== q) j++;
      tokens.push({ type: "literal", value: text.slice(i, j + 1) });
      i = j + 1;
      continue;
    }
    // Number literal
    if (/\d/.test(text[i])) {
      let j = i;
      while (j < text.length && /[\d.]/.test(text[j])) j++;
      tokens.push({ type: "literal", value: text.slice(i, j) });
      i = j;
      continue;
    }
    // Function name (word before "(")
    if (/[A-Z]/.test(text[i])) {
      let j = i;
      while (j < text.length && /[A-Z_]/.test(text[j])) j++;
      const word = text.slice(i, j);
      tokens.push({ type: FNS.has(word) ? "fn" : "other", value: word });
      i = j;
      continue;
    }
    // Operators
    if (/[+\-*/=!<>%(),;]/.test(text[i])) {
      // Two-char operators
      const two = text.slice(i, i + 2);
      if (["==", "!=", ">=", "<="].includes(two)) {
        tokens.push({ type: "op", value: two });
        i += 2;
      } else {
        tokens.push({ type: "op", value: text[i] });
        i++;
      }
      continue;
    }
    tokens.push({ type: "other", value: text[i] });
    i++;
  }
  return tokens;
}

// ─────────────────────────────────────────────
// Field type icons
// ─────────────────────────────────────────────

function IconDefault({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="2" width="12" height="12" rx="2" />
    </svg>
  );
}
function IconText({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 5h10M3 8h7M3 11h5" strokeLinecap="round" />
    </svg>
  );
}
function IconLongText({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 4h12M2 7h12M2 10h12M2 13h7" strokeLinecap="round" />
    </svg>
  );
}
function IconRichText({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 4h7M3 8h10M3 12h5" strokeLinecap="round" />
      <path d="M11 2l2 2-6 6H5v-2l6-6z" />
    </svg>
  );
}
function IconNumber({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 2l-1 12M13 2l-1 12M2 6h12M2 10h12" strokeLinecap="round" />
    </svg>
  );
}
function IconDecimal({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 3v4M7 3v4M5 3h.01M5 9h.01" />
      <path d="M10 6h4l-2-3-2 3zM10 10h4l-2 3-2-3z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconCurrency({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 5v6M6 6.5h3a1.5 1.5 0 010 3H6" strokeLinecap="round" />
    </svg>
  );
}
function IconBoolean({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1" y="5" width="14" height="6" rx="3" />
      <circle cx="11" cy="8" r="2" fill="currentColor" />
    </svg>
  );
}
function IconDate({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="3" width="12" height="11" rx="2" />
      <path d="M5 1v4M11 1v4M2 7h12" strokeLinecap="round" />
    </svg>
  );
}
function IconDatetime({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="3" width="8" height="9" rx="1.5" />
      <path d="M3 7h6M5 1v3" strokeLinecap="round" />
      <circle cx="12" cy="11" r="3" />
      <path d="M12 9.5v1.5l1 1" strokeLinecap="round" />
    </svg>
  );
}
function IconTime({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 5v3l2 2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconSelect({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="4" width="12" height="8" rx="2" />
      <path d="M5 8l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconMultiSelect({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="2" width="5" height="5" rx="1" />
      <path d="M3.5 4.5l1 1 2-2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <path d="M10.5 4.5l1 1 2-2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="2" y="9" width="5" height="5" rx="1" />
      <path d="M3.5 11.5l1 1 2-2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconFile({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 2h5l4 4v8a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z" />
      <path d="M9 2v4h4" strokeLinecap="round" />
    </svg>
  );
}
function IconImage({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="2" width="12" height="12" rx="2" />
      <circle cx="5.5" cy="5.5" r="1.5" />
      <path d="M2 10l4-4 3 3 2-2 3 3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconRelation({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="4" cy="8" r="2.5" />
      <circle cx="12" cy="8" r="2.5" />
      <path d="M6.5 8h3" />
    </svg>
  );
}
function IconLookup({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="6" cy="6" r="4" />
      <path d="M9 9l4 4" strokeLinecap="round" />
      <path d="M4 6h4M6 4v4" strokeLinecap="round" />
    </svg>
  );
}
function IconFormula({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 8h4l1-5 2 10 1-5h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconSignature({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 12c2-4 3-7 4-7s1 3 2 3 2-4 3-3 1 3 3 2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2 14h12" strokeLinecap="round" />
    </svg>
  );
}
function IconUrl({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M6 10a4 4 0 005.66-5.66L10.24 2.9A4 4 0 004.58 8.56" strokeLinecap="round" />
      <path d="M10 6a4 4 0 00-5.66 5.66l1.42 1.42A4 4 0 0011.42 7.44" strokeLinecap="round" />
      <path d="M7 7l2 2" strokeLinecap="round" />
    </svg>
  );
}
function IconEmail({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="4" width="12" height="9" rx="1.5" />
      <path d="M2 5l6 5 6-5" strokeLinecap="round" />
    </svg>
  );
}
function IconPhone({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 2h3l1 3-2 1.5a9 9 0 004.5 4.5L12 9l3 1v3a1 1 0 01-1 1A13 13 0 013 3a1 1 0 011-1z" />
    </svg>
  );
}
function IconJson({ cls = "w-4 h-4" }: { cls?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cls} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M5 2H3a1 1 0 00-1 1v3l-1 2 1 2v3a1 1 0 001 1h2M11 2h2a1 1 0 011 1v3l1 2-1 2v3a1 1 0 01-1 1h-2" strokeLinecap="round" />
    </svg>
  );
}

// ─────────────────────────────────────────────
// SequencesTab
// ─────────────────────────────────────────────

function SequencesTab({
  sequences,
  onAdd,
  onEdit,
  onDelete,
}: {
  sequences: Sequence[];
  onAdd: () => void;
  onEdit: (s: Sequence) => void;
  onDelete: (s: Sequence) => void;
}) {
  return (
    <div className="max-w-[900px]">
      <div className="flex items-center justify-between mb-4">
        <p className="text-[13px] text-primary/60">
          Последовательности автоматически генерируют уникальные номера для записей (например: ORD-0001, ORD-0002…).
        </p>
        <button
          onClick={onAdd}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-cta text-white text-[13px] font-medium rounded-[8px] hover:bg-active transition-colors shrink-0 ml-4"
        >
          <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3v10M3 8h10" strokeLinecap="round" />
          </svg>
          Добавить
        </button>
      </div>

      {sequences.length === 0 ? (
        <div className="bg-white rounded-[12px] border border-dashed border-cardbg p-8 text-center">
          <p className="text-[13px] text-primary/40 mb-2">Нет последовательностей</p>
          <button onClick={onAdd} className="text-[13px] text-cta hover:underline font-medium">
            Добавить первую последовательность
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-[12px] border border-cardbg overflow-hidden">
          {sequences.map((s, i) => (
            <div
              key={s.id}
              className={cn(
                "group flex items-center gap-4 px-4 py-3",
                i < sequences.length - 1 && "border-b border-cardbg",
              )}
            >
              <span className="px-2 py-0.5 text-[12px] font-bold rounded font-mono bg-cta/10 text-cta shrink-0">
                SEQ
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-[13px] font-medium text-primary">{s.field_name}</span>
                <span className="ml-3 text-[12px] font-mono text-primary/40">
                  {[s.prefix, "N".padStart(s.padding, "0"), s.suffix].filter(Boolean).join("")}
                </span>
              </div>
              <span className="text-[12px] text-primary/40 shrink-0">
                шаг: {s.step} · следующий: {s.next_value}
              </span>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => onEdit(s)}
                  className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-mainbg text-primary/40 hover:text-primary"
                  title="Редактировать"
                >
                  <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M11 2l3 3-8 8H3v-3l8-8z" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <button
                  onClick={() => onDelete(s)}
                  className="w-7 h-7 flex items-center justify-center rounded-[6px] hover:bg-mainbg text-[#D32F2F]/60"
                  title="Удалить"
                >
                  <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 4h10M5 4V3h6v1M6 7v5M10 7v5M4 4l1 9h6l1-9" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// SequenceModal
// ─────────────────────────────────────────────

function SequenceModal({
  mode,
  seq,
  appId,
  entityId,
  onClose,
  onCreate,
  onUpdate,
  saving,
}: {
  mode: "create" | "edit";
  seq?: Sequence;
  appId: string;
  entityId: string;
  onClose: () => void;
  onCreate: (data: SequenceCreate) => void;
  onUpdate: (data: SequenceUpdate) => void;
  saving: boolean;
}) {
  const [fieldName, setFieldName] = useState(seq?.field_name ?? "");
  const [prefix, setPrefix]       = useState(seq?.prefix ?? "");
  const [suffix, setSuffix]       = useState(seq?.suffix ?? "");
  const [padding, setPadding]     = useState(seq?.padding ?? 4);
  const [step, setStep]           = useState(seq?.step ?? 1);
  const [start, setStart]         = useState(seq?.next_value ?? 1);
  const [resetOn, setResetOn]     = useState(seq?.reset_on ?? "");
  const previewM = usePreviewNextSequenceValue(appId, entityId);
  const [previewValue, setPreviewValue] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (mode === "create") {
      onCreate({ field_name: fieldName, prefix, suffix, padding, step, start: start, reset_on: resetOn || null });
    } else {
      onUpdate({ prefix, suffix, padding, step, reset_on: resetOn || null });
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,32,95,0.35)" }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[20px] w-[480px] flex flex-col"
        style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-[30px] pt-[28px] pb-[16px] border-b border-cardbg">
          <span className="text-[18px] font-bold text-primary">
            {mode === "create" ? "Новая последовательность" : "Изменить последовательность"}
          </span>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg text-primary/40 text-[22px] leading-none">×</button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-[30px] py-[20px] pb-[28px]">
          <div className="flex flex-col gap-1.5">
            <label className="text-[13px] font-medium text-primary/60">Поле <span className="text-red-500">*</span></label>
            <input
              required
              value={fieldName}
              onChange={(e) => setFieldName(e.target.value)}
              disabled={mode === "edit"}
              placeholder="например: order_number"
              className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta placeholder:text-primary/30 disabled:opacity-50"
            />
          </div>

          <div className="flex gap-3">
            <div className="flex flex-col gap-1.5 flex-1">
              <label className="text-[13px] font-medium text-primary/60">Префикс</label>
              <input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="ORD-" className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta placeholder:text-primary/30" />
            </div>
            <div className="flex flex-col gap-1.5 flex-1">
              <label className="text-[13px] font-medium text-primary/60">Суффикс</label>
              <input value={suffix} onChange={(e) => setSuffix(e.target.value)} placeholder="-2025" className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta placeholder:text-primary/30" />
            </div>
          </div>

          <div className="flex gap-3">
            <div className="flex flex-col gap-1.5 flex-1">
              <label className="text-[13px] font-medium text-primary/60">Длина числа</label>
              <input type="number" min={1} max={20} value={padding} onChange={(e) => setPadding(Number(e.target.value))} className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta" />
            </div>
            <div className="flex flex-col gap-1.5 flex-1">
              <label className="text-[13px] font-medium text-primary/60">Шаг</label>
              <input type="number" min={1} value={step} onChange={(e) => setStep(Number(e.target.value))} className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta" />
            </div>
            {mode === "create" && (
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-[13px] font-medium text-primary/60">Начало</label>
                <input type="number" min={1} value={start} onChange={(e) => setStart(Number(e.target.value))} className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta" />
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[13px] font-medium text-primary/60">Сброс по полю</label>
            <input value={resetOn} onChange={(e) => setResetOn(e.target.value)} placeholder="например: created_year (необязательно)" className="h-[38px] px-3 bg-mainbg border border-cardbg rounded-[8px] text-[14px] text-primary outline-none focus:border-cta placeholder:text-primary/30" />
          </div>

          {/* Preview */}
          {mode === "edit" && seq && (
            <div className="flex items-center gap-[10px]">
              <button
                type="button"
                onClick={() =>
                  previewM.mutate(seq.id, { onSuccess: (r) => setPreviewValue(r.value) })
                }
                disabled={previewM.isPending}
                className="h-[34px] px-4 text-[13px] font-medium border border-cardbg rounded-[8px] text-primary hover:border-cta hover:text-cta transition-colors disabled:opacity-50"
              >
                {previewM.isPending ? "…" : "Тест — следующее значение"}
              </button>
              {previewValue && (
                <span className="text-[13px] font-mono bg-mainbg px-3 py-1 rounded-[6px] text-cta">
                  {previewValue}
                </span>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <button type="button" onClick={onClose} className="h-[36px] px-4 text-[13px] font-medium text-primary/60 hover:text-primary rounded-[8px] hover:bg-mainbg transition-colors">
              Отмена
            </button>
            <button type="submit" disabled={saving} className="h-[36px] px-5 bg-cta text-white text-[13px] font-medium rounded-[8px] hover:bg-active transition-colors disabled:opacity-50">
              {saving ? "Сохранение…" : mode === "create" ? "Создать" : "Сохранить"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
