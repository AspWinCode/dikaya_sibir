import { apiClient } from "./client";

export interface Role {
  id: string;
  display_name: string;
  description: string | null;
  is_system: boolean;
}

export interface RoleCreate {
  display_name: string;
  description?: string | null;
  /** Function codes the new role may use (see the function catalog). */
  functions?: string[];
}

export interface RoleUpdate {
  display_name?: string;
  description?: string | null;
}

export interface ResourcePermission {
  id: string;
  role_id: string;
  resource_type: string;
  resource_id: string;
  action: string;
  allowed: boolean;
  created_at: string;
}

export interface ResourcePermissionUpsert {
  role_id: string;
  resource_type: string;
  resource_id: string;
  action: string;
  allowed: boolean;
}

export interface AbacCondition {
  field: string;
  op: string;
  // Plain value for most ops; a list for "in" / "not_in" (backend requires
  // an actual array there — comma-separated text is split on submit, see
  // SecurityPage's AbacSection).
  value: string | string[];
}

export interface AbacRule {
  id: string;
  role_id: string;
  resource_type: string;
  resource_id: string | null;
  condition_json: AbacCondition[];
  effect: "allow" | "deny";
  priority: number;
  description: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AbacRuleCreate {
  role_id: string;
  resource_type: string;
  resource_id?: string | null;
  condition_json?: AbacCondition[];
  effect?: "allow" | "deny";
  priority?: number;
  description?: string | null;
}

export interface AbacRuleUpdate {
  resource_type?: string;
  resource_id?: string | null;
  condition_json?: AbacCondition[];
  effect?: "allow" | "deny";
  priority?: number;
  description?: string | null;
}

export async function listRoles(): Promise<Role[]> {
  const { data } = await apiClient.get<Role[]>("/roles");
  return data;
}

export async function createRole(body: RoleCreate): Promise<Role> {
  const { data } = await apiClient.post<Role>("/roles", body);
  return data;
}

export async function updateRole(roleId: string, body: RoleUpdate): Promise<Role> {
  const { data } = await apiClient.patch<Role>(`/roles/${roleId}`, body);
  return data;
}

export async function deleteRole(roleId: string): Promise<void> {
  await apiClient.delete(`/roles/${roleId}`);
}

export async function listRolePermissions(roleId: string): Promise<ResourcePermission[]> {
  const { data } = await apiClient.get<ResourcePermission[]>(`/roles/${roleId}/permissions`);
  return data;
}

export async function replaceRolePermissions(
  roleId: string,
  permissions: ResourcePermissionUpsert[]
): Promise<ResourcePermission[]> {
  const { data } = await apiClient.put<ResourcePermission[]>(`/roles/${roleId}/permissions`, { permissions });
  return data;
}

export async function listAbacRules(roleId?: string): Promise<AbacRule[]> {
  const { data } = await apiClient.get<AbacRule[]>("/abac-rules", {
    params: roleId ? { role_id: roleId } : undefined,
  });
  return data;
}

export async function createAbacRule(body: AbacRuleCreate): Promise<AbacRule> {
  const { data } = await apiClient.post<AbacRule>("/abac-rules", body);
  return data;
}

export async function updateAbacRule(ruleId: string, body: AbacRuleUpdate): Promise<AbacRule> {
  const { data } = await apiClient.patch<AbacRule>(`/abac-rules/${ruleId}`, body);
  return data;
}

export async function deleteAbacRule(ruleId: string): Promise<void> {
  await apiClient.delete(`/abac-rules/${ruleId}`);
}

export interface FunctionCatalogItem {
  code: string;
  label: string;
  description: string;
  group: string;
}

export interface RoleFunctions {
  role_id: string;
  /** platform_admin: every function, can't be edited. */
  locked: boolean;
  is_system: boolean;
  /** Function codes the role may use right now. */
  allowed: string[];
  /** Function codes the role has out of the box. */
  defaults: string[];
}

export async function listFunctionCatalog(): Promise<FunctionCatalogItem[]> {
  const { data } = await apiClient.get<FunctionCatalogItem[]>("/permissions/catalog");
  return data;
}

export async function getRoleFunctions(roleId: string): Promise<RoleFunctions> {
  const { data } = await apiClient.get<RoleFunctions>(`/roles/${roleId}/functions`);
  return data;
}

export async function saveRoleFunctions(roleId: string, allowed: string[]): Promise<RoleFunctions> {
  const { data } = await apiClient.put<RoleFunctions>(`/roles/${roleId}/functions`, { allowed });
  return data;
}
