import { api } from "./api";

export type AccessRequestStatus = "pending" | "approved" | "rejected";

export interface AccessRequest {
  id: string;
  user_id: string;
  name: string;
  email: string;
  student_id: string | null;
  reason: string | null;
  status: AccessRequestStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export const accessRequestService = {
  mine: () => api.get<AccessRequest | null>("/api/access-requests/me"),

  submit: (reason?: string) =>
    api.post<AccessRequest>("/api/access-requests", {
      reason: reason?.trim() || undefined,
    }),
};
