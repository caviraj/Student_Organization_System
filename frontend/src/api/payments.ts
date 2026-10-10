import { apiClient } from './client';
import type { PaymentIntent, PaymentResultResponse, RazorpayVerifyPayload } from '../types/api';

export const paymentsApi = {
  // Read, not passed down the route: after a reload - or a return from a bank page, which drops
  // the router state the checkout was navigated with - this is the only thing that still knows
  // which order is being paid and how much it costs.
  getIntent: async (orderId: string): Promise<PaymentIntent> => {
    return apiClient<PaymentIntent>(`/payments/${orderId}`);
  },

  // The Checkout widget says the payment succeeded; this is where the backend decides whether to
  // believe it, by checking the signature the widget handed back.
  verify: async (orderId: string, payload: RazorpayVerifyPayload): Promise<PaymentResultResponse> => {
    return apiClient<PaymentResultResponse>(`/payments/${orderId}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Only reachable while the backend runs PAYMENTS_PROVIDER=mock (it answers 409 otherwise).
  mockConfirm: async (
    orderId: string,
    outcome: 'success' | 'fail'
  ): Promise<PaymentResultResponse> => {
    return apiClient<PaymentResultResponse>(`/payments/${orderId}/mock-confirm`, {
      method: 'POST',
      body: JSON.stringify({ outcome }),
    });
  },
};
