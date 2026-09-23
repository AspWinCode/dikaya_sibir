import { apiClient } from "./client";
import type { CursorPage } from "./apps";

export interface UserRole {
  id: string;
  display_name: string;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  is_blocked: boolean;
  is_superuser: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  roles: UserRole[];
}

export interface UserCreate {
  email: string;
  display_name: string;
  password: string;
  roles: string[];
}

export interface UserUpdate {
  display_name?: string;
  is_active?: boolean;
  is_blocked?: boolean;
  roles?: string[];
}

export interface UserListParams {
  search?: string;
  role?: string;
  is_active?: boolean;
  cursor?: string;
  limit?: number;
}

export async function listUsers(params?: UserListParams): Promise<CursorPage<User>> {
  const { data } = await apiClient.get<CursorPage<User>>("/users", { params });
  return data;
}

export async function getUser(userId: string): Promise<User> {
  const { data } = await apiClient.get<User>(`/users/${userId}`);
  return data;
}

export async function createUser(body: UserCreate): Promise<User> {
  const { data } = await apiClient.post<User>("/users", body);
  return data;
}

export async function updateUser(userId: string, body: UserUpdate): Promise<User> {
  const { data } = await apiClient.patch<User>(`/users/${userId}`, body);
  return data;
}

export async function deactivateUser(userId: string): Promise<void> {
  await apiClient.delete(`/users/${userId}`);
}

export async function hardDeleteUser(userId: string): Promise<void> {
  await apiClient.delete(`/users/${userId}/hard`);
}

export async function listRoles(): Promise<UserRole[]> {
  const { data } = await apiClient.get<UserRole[]>("/users/roles");
  return data;
}

export interface InviteUserRequest {
  email: string;
  display_name: string;
  roles: string[];
}

export interface InviteUserResult extends User {
  email_sent: boolean;
  /** Present only when the invitation email could not be delivered. */
  temp_password: string | null;
}

export async function inviteUser(body: InviteUserRequest): Promise<InviteUserResult> {
  const { data } = await apiClient.post<InviteUserResult>("/users/invite", body);
  return data;
}

export async function setUserPassword(userId: string, newPassword: string): Promise<void> {
  await apiClient.post(`/users/${userId}/set-password`, { new_password: newPassword });
}
