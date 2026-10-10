import { apiClient } from './client';
import type {
  Announcement,
  AnnouncementDelivery,
  CreateAnnouncementPayload,
  UpdateAnnouncementPayload,
  AnnouncementFilterParams,
} from '../types/announcements';
import type { PaginatedResponse } from '../types/api';

export interface CreateAnnouncementResponse {
  announcement: Announcement;
  deliveries_created: number;
}

export const announcementsApi = {
  getAnnouncements: async (params?: AnnouncementFilterParams) => {
    return apiClient<PaginatedResponse<Announcement>>('/announcements', {
      method: 'GET',
      params: {
        page: params?.page ?? 1,
        page_size: params?.page_size ?? 20,
        ...(params?.category ? { category: params.category } : {}),
      },
    });
  },

  getAnnouncement: async (id: string) => {
    return apiClient<Announcement>(`/announcements/${id}`, {
      method: 'GET',
    });
  },

  createAnnouncement: async (data: CreateAnnouncementPayload) => {
    return apiClient<CreateAnnouncementResponse>('/announcements', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateRevision: async (id: string, data: UpdateAnnouncementPayload) => {
    return apiClient<Announcement>(`/announcements/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  getDeliveries: async (id: string, params?: { status?: string; page?: number; page_size?: number }) => {
    return apiClient<PaginatedResponse<AnnouncementDelivery>>(`/announcements/${id}/deliveries`, {
      method: 'GET',
      params,
    });
  },
};
