import { apiClient } from './client';
import type { MockConfirmResponse } from '../types/api';

export const paymentsApi = {
  mockConfirm: async (
    orderId: string,
    outcome: 'success' | 'fail'
  ): Promise<MockConfirmResponse> => {
    return apiClient<MockConfirmResponse>(`/payments/${orderId}/mock-confirm`, {
      method: 'POST',
      body: JSON.stringify({ outcome }),
    });
  },
};
