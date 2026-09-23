import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acquireAppLock,
  addAppMember,
  checkPublish,
  cloneApp,
  createApp,
  createSnapshot,
  deleteApp,
  getApp,
  getAppLock,
  listAppMembers,
  listInviteLinks,
  createInviteLink,
  revokeInviteLink,
  type InviteLinkCreate,
  listApps,
  listSnapshots,
  publishApp,
  releaseAppLock,
  removeAppMember,
  rollbackSnapshot,
  updateApp,
  type AppCloneCreate,
  type AppCreate,
  type AppUpdate,
  type LockInfo,
} from "../api/apps";

const APPS_KEY = ["apps"] as const;

export function useApps() {
  return useQuery({
    queryKey: APPS_KEY,
    queryFn: () => listApps(),
  });
}

export function useApp(appId: string | undefined) {
  return useQuery({
    queryKey: ["app", appId],
    queryFn: () => getApp(appId!),
    enabled: !!appId,
  });
}

export function useAppLock(appId: string | undefined) {
  return useQuery<LockInfo | null>({
    queryKey: ["app-lock", appId],
    queryFn: () => getAppLock(appId!),
    enabled: !!appId,
    refetchInterval: 15_000,
  });
}

export function useAcquireAppLock(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => acquireAppLock(appId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["app-lock", appId] }); },
  });
}

export function useReleaseAppLock(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => releaseAppLock(appId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["app-lock", appId] }); },
  });
}

export function useCreateApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AppCreate) => createApp(body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: APPS_KEY }); },
  });
}

export function useUpdateApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appId, body }: { appId: string; body: AppUpdate }) => updateApp(appId, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: APPS_KEY }); },
  });
}

export function useDeleteApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (appId: string) => deleteApp(appId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: APPS_KEY }); },
  });
}

export function useCheckPublish(appId: string | undefined) {
  return useQuery({
    queryKey: ["publish-check", appId],
    queryFn: () => checkPublish(appId!),
    enabled: !!appId,
  });
}

export function usePublishApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (appId: string) => publishApp(appId),
    onSuccess: (_data, appId) => {
      void qc.invalidateQueries({ queryKey: APPS_KEY });
      void qc.invalidateQueries({ queryKey: ["publish-check", appId] });
    },
  });
}

export function useCloneApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appId, body }: { appId: string; body: AppCloneCreate }) =>
      cloneApp(appId, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: APPS_KEY }); },
  });
}

export function useAppSnapshots(appId: string | null | undefined) {
  return useQuery({
    queryKey: ["app-snapshots", appId],
    queryFn: () => listSnapshots(appId!),
    enabled: !!appId,
  });
}

export function useCreateSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appId, comment }: { appId: string; comment?: string | null }) =>
      createSnapshot(appId, comment),
    onSuccess: (_, { appId }) => {
      void qc.invalidateQueries({ queryKey: ["app-snapshots", appId] });
    },
  });
}

export function useRollbackSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appId, snapshotNum }: { appId: string; snapshotNum: number }) =>
      rollbackSnapshot(appId, snapshotNum),
    onSuccess: (_, { appId }) => {
      void qc.invalidateQueries({ queryKey: APPS_KEY });
      void qc.invalidateQueries({ queryKey: ["app-snapshots", appId] });
    },
  });
}

export function useAppMembers(appId: string | null | undefined) {
  return useQuery({
    queryKey: ["app-members", appId],
    queryFn: () => listAppMembers(appId!),
    enabled: !!appId,
  });
}

export function useAddAppMember(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      addAppMember(appId, userId, role),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["app-members", appId] }); },
  });
}

export function useRemoveAppMember(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeAppMember(appId, userId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["app-members", appId] }); },
  });
}

export function useInviteLinks(appId: string | null | undefined) {
  return useQuery({
    queryKey: ["app-invite-links", appId],
    queryFn: () => listInviteLinks(appId!),
    enabled: !!appId,
    retry: false,
  });
}

export function useCreateInviteLink(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: InviteLinkCreate) => createInviteLink(appId, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["app-invite-links", appId] }); },
  });
}

export function useRevokeInviteLink(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => revokeInviteLink(appId, linkId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["app-invite-links", appId] }); },
  });
}
