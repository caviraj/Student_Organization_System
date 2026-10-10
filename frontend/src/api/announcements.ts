import { apiClient } from './client';
import type {
  Announcement,
  AnnouncementDetail,
  AnnouncementDelivery,
  CreateAnnouncementPayload,
  UpdateAnnouncementPayload,
  AnnouncementFilterParams,
} from '../types/announcements';
import type { PaginatedResponse } from '../types/api';

/** POST answers with the announcement itself plus what the post queued (DESIGN.md §5). */
export interface CreateAnnouncementResponse extends AnnouncementDetail {
  delivery_summary: {
    inapp_queued: number;
    email_queued: number;
    skipped_opted_out: number;
  };
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
    return apiClient<AnnouncementDetail>(`/announcements/${id}`, {
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
    return apiClient<AnnouncementDetail>(`/announcements/${id}`, {
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
