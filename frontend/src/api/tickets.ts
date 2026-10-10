import { apiClient } from './client';
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

  getMyTickets: async () => {
    return apiClient<TicketItem[]>('/tickets/me', {
      method: 'GET',
    });
  },

  checkIn: async (data: CheckInRequest) => {
    return apiClient<CheckInResponse>('/checkin', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
