/** Activity / notification / occupancy API clients. */
import { api } from "./api";
import type { ActivityItem, NotificationItem, OccupancyResponse, CalendarResponse, WeeklyUsage } from "@/src/types/booking";

export const activityService = {
  recent: (limit = 20) => api.get<ActivityItem[]>(`/api/activity?limit=${limit}`),
};

export const notificationService = {
  mine: () => api.get<NotificationItem[]>("/api/notifications/me"),
  markRead: (id: string) => api.put<{ ok: boolean }>(`/api/notifications/${id}/read`),
  markAllRead: () => api.put<{ ok: boolean }>("/api/notifications/read-all"),
};

export const usageService = {
  weekly: () => api.get<WeeklyUsage>("/api/bookings/usage/weekly"),
  occupancy: (date: string) => api.get<OccupancyResponse>(`/api/bookings/occupancy/${date}`),
  calendar: (year: number, month: number) =>
    api.get<CalendarResponse>(`/api/bookings/calendar/${year}/${month}`),
};
