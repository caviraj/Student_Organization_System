import { apiClient } from './client';
import type { PaginatedResponse } from '../types/api';
import type {
  TicketCheckoutRequest,
  TicketCheckoutResponse,
  TicketItem,
  CheckInRequest,
  CheckInResponse,
} from '../types/events';

export const ticketsApi = {
  checkout: async (data: TicketCheckoutRequest) => {
    return apiClient<TicketCheckoutResponse>('/tickets/checkout', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getMyTickets: async (): Promise<TicketItem[]> => {
    // /tickets/me answers with a page envelope, not a bare array. 100 is the API's max page_size.
    // shortcut: tickets past the first 100 need real pagination, which no screen asks for yet.
    const page = await apiClient<PaginatedResponse<TicketItem>>('/tickets/me', {
      params: { page_size: 100 },
    });
    return page.items;
  },

  checkIn: async (data: CheckInRequest) => {
    return apiClient<CheckInResponse>('/checkin', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
