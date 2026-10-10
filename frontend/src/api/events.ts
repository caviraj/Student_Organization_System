import { apiClient } from './client';
import type {
  EventItem,
  EventDetail,
  EventCreateInput,
  EventUpdateInput,
  TicketType,
  TicketTypeCreateInput,
  EventReport,
  AttendeeItem,
} from '../types/events';

export const eventsApi = {
  getEvents: async (params?: { page?: number; page_size?: number; status?: string }) => {
    return apiClient<{ items: EventItem[]; total: number; page: number; page_size: number }>('/events', {
      method: 'GET',
      params,
    });
  },

  getEvent: async (id: string) => {
    return apiClient<EventDetail>(`/events/${id}`, {
      method: 'GET',
    });
  },

  createEvent: async (data: EventCreateInput) => {
    return apiClient<EventDetail>('/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateEvent: async (id: string, data: EventUpdateInput) => {
    return apiClient<EventDetail>(`/events/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  createTicketType: async (eventId: string, data: TicketTypeCreateInput) => {
    return apiClient<TicketType>(`/events/${eventId}/ticket-types`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getReport: async (eventId: string) => {
    return apiClient<EventReport>(`/events/${eventId}/report`, {
      method: 'GET',
    });
  },

  getEventReport: async (eventId: string) => {
    return apiClient<EventReport>(`/events/${eventId}/report`, {
      method: 'GET',
    });
  },

  getAttendees: async (
    eventId: string,
    params?: { page?: number; page_size?: number; status?: string; search?: string }
  ) => {
    return apiClient<{ items: AttendeeItem[]; total: number; page: number; page_size: number }>(
      `/events/${eventId}/attendees`,
      {
        method: 'GET',
        params,
      }
    );
  },
};
