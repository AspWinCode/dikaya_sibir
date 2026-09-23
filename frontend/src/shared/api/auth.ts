import { apiClient } from "./client";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginPayload {
  email: string;
  password: string;
  totp_code?: string;
}

export interface Role {
  id: string;
  display_name: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  is_superuser: boolean;
  totp_enabled: boolean;
  /** Temp (invite) password — user must set their own before using the app. */
  must_change_password?: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  roles: Role[];
}

export async function login(payload: LoginPayload): Promise<TokenPair> {
  const { data } = await apiClient.post<TokenPair>("/auth/login", payload);
  return data;
}

export async function ldapLogin(payload: { email: string; password: string }): Promise<TokenPair> {
  const { data } = await apiClient.post<TokenPair>("/auth/ldap-login", payload);
  return data;
}

export interface SessionPolicy {
  timeout_minutes: number;
  max_concurrent_sessions: number;
  updated_at: string;
}

export async function fetchSessionPolicy(): Promise<SessionPolicy> {
  const { data } = await apiClient.get<SessionPolicy>("/auth/session-policy");
  return data;
}

export async function updateSessionPolicy(body: Partial<Omit<SessionPolicy, "updated_at">>): Promise<SessionPolicy> {
  const { data } = await apiClient.put<SessionPolicy>("/auth/session-policy", body);
  return data;
}

export interface LdapStatus {
  enabled: boolean;
  url: string | null;
  search_base: string | null;
  bind_dn: string | null;
}

export interface PasswordPolicy {
  min_length: number;
  require_uppercase: boolean;
  require_lowercase: boolean;
  require_digit: boolean;
  require_special: boolean;
  max_age_days: number;
  history_depth: number;
  updated_at: string;
}

export type PasswordPolicyUpdate = Partial<Omit<PasswordPolicy, "updated_at">>;

export async function fetchPasswordPolicy(): Promise<PasswordPolicy> {
  const { data } = await apiClient.get<PasswordPolicy>("/auth/password-policy");
  return data;
}

export async function updatePasswordPolicy(body: PasswordPolicyUpdate): Promise<PasswordPolicy> {
  const { data } = await apiClient.put<PasswordPolicy>("/auth/password-policy", body);
  return data;
}

export interface FilePolicy {
  max_file_size_mb: number;
  max_files_per_record: number;
  allowed_extensions: string[];
  updated_at: string;
}

export type FilePolicyUpdate = Partial<Omit<FilePolicy, "updated_at">>;

export async function fetchFilePolicy(): Promise<FilePolicy> {
  const { data } = await apiClient.get<FilePolicy>("/auth/file-policy");
  return data;
}

export async function updateFilePolicy(body: FilePolicyUpdate): Promise<FilePolicy> {
  const { data } = await apiClient.put<FilePolicy>("/auth/file-policy", body);
  return data;
}

export async function fetchLdapStatus(): Promise<LdapStatus> {
  const { data } = await apiClient.get<LdapStatus>("/auth/ldap-status");
  return data;
}

export async function testLdapConnection(): Promise<{ ok: boolean; message?: string; error?: string }> {
  const { data } = await apiClient.post<{ ok: boolean; message?: string; error?: string }>("/auth/ldap-test");
  return data;
}

export async function yandexCallback(code: string): Promise<TokenPair> {
  const { data } = await apiClient.post<TokenPair>("/auth/yandex/callback", { code });
  return data;
}

export async function vkCallback(code: string): Promise<TokenPair> {
  const { data } = await apiClient.post<TokenPair>("/auth/vk/callback", { code });
  return data;
}

export function getYandexAuthUrl(): string {
  return `${apiClient.defaults.baseURL ?? ""}/auth/yandex`;
}

export function getVkAuthUrl(): string {
  return `${apiClient.defaults.baseURL ?? ""}/auth/vk`;
}

export async function logout(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
}

export async function fetchMe(): Promise<CurrentUser> {
  const { data } = await apiClient.get<CurrentUser>("/users/me");
  return data;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiClient.post("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export async function logoutAll(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout-all", { refresh_token: refreshToken });
}

export interface TOTPSetupResponse {
  secret: string;
  provisioning_uri: string;
}

export async function totpSetup(): Promise<TOTPSetupResponse> {
  const { data } = await apiClient.post<TOTPSetupResponse>("/auth/totp/setup");
  return data;
}

export async function totpEnable(code: string): Promise<void> {
  await apiClient.post("/auth/totp/enable", { code });
}

export async function totpDisable(code: string): Promise<void> {
  await apiClient.post("/auth/totp/disable", { code });
}
