import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAbacRule,
  createRole,
  deleteAbacRule,
  deleteRole,
  listAbacRules,
  getRoleFunctions,
  listFunctionCatalog,
  listRolePermissions,
  listRoles,
  replaceRolePermissions,
  saveRoleFunctions,
  updateAbacRule,
  updateRole,
  type AbacRuleCreate,
  type AbacRuleUpdate,
  type ResourcePermissionUpsert,
  type RoleCreate,
  type RoleUpdate,
} from "@/shared/api/roles";

export function useAllRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: listRoles });
}

export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RoleCreate) => createRole(body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["roles"] }); },
  });
}

export function useUpdateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ roleId, body }: { roleId: string; body: RoleUpdate }) =>
      updateRole(roleId, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["roles"] }); },
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roleId: string) => deleteRole(roleId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["roles"] }); },
  });
}

export function useRolePermissions(roleId: string | null) {
  return useQuery({
    queryKey: ["role-permissions", roleId],
    queryFn: () => listRolePermissions(roleId!),
    enabled: !!roleId,
  });
}

export function useReplaceRolePermissions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      roleId,
      permissions,
    }: {
      roleId: string;
      permissions: ResourcePermissionUpsert[];
    }) => replaceRolePermissions(roleId, permissions),
    onSuccess: (_, { roleId }) => {
      void qc.invalidateQueries({ queryKey: ["role-permissions", roleId] });
    },
  });
}

export function useAbacRules(roleId?: string) {
  return useQuery({
    queryKey: ["abac-rules", roleId ?? "all"],
    queryFn: () => listAbacRules(roleId),
  });
}

export function useCreateAbacRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AbacRuleCreate) => createAbacRule(body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["abac-rules"] }); },
  });
}

export function useUpdateAbacRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId, body }: { ruleId: string; body: AbacRuleUpdate }) =>
      updateAbacRule(ruleId, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["abac-rules"] }); },
  });
}

export function useDeleteAbacRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) => deleteAbacRule(ruleId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["abac-rules"] }); },
  });
}

export function useFunctionCatalog() {
  return useQuery({ queryKey: ["function-catalog"], queryFn: listFunctionCatalog, staleTime: 5 * 60_000 });
}

export function useRoleFunctions(roleId: string | null) {
  return useQuery({
    queryKey: ["role-functions", roleId],
    queryFn: () => getRoleFunctions(roleId!),
    enabled: !!roleId,
  });
}

export function useSaveRoleFunctions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ roleId, allowed }: { roleId: string; allowed: string[] }) =>
      saveRoleFunctions(roleId, allowed),
    onSuccess: (data) => {
      qc.setQueryData(["role-functions", data.role_id], data);
    },
  });
}
