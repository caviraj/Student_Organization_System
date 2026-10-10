import { apiClient } from './client';
import type {
  CheckoutResponse,
  MemberCard,
  Membership,
  PaginatedResponse,
  RenewalDueItem,
  User,
  VerifyResponse,
} from '../types/api';

export const membershipsApi = {
  checkout: async (planId: string): Promise<CheckoutResponse> => {
    return apiClient<CheckoutResponse>('/memberships/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan_id: planId }),
    });
  },

  getMyCard: async (): Promise<MemberCard> => {
    return apiClient<MemberCard>('/members/me/card');
  },

  verifyMember: async (query: string | { code?: string; q?: string }): Promise<VerifyResponse> => {
    const params = typeof query === 'string' ? (query.startsWith('SSA-') ? { code: query } : { q: query }) : query;
    return apiClient<VerifyResponse>('/members/verify', {
      params,
    });
  },

  getMemberships: async (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    role?: string;
    search?: string;
  }): Promise<PaginatedResponse<Membership>> => {
    return apiClient<PaginatedResponse<Membership>>('/memberships', {
      params,
    });
  },

  getRenewalsDue: async (params?: {
    days_ahead?: number;
  } | number): Promise<{ items: RenewalDueItem[]; total: number }> => {
    const queryParams = typeof params === 'number' ? { days_ahead: params } : params;
    return apiClient<{ items: RenewalDueItem[]; total: number }>(
      '/memberships/renewals-due',
      { params: queryParams }
    );
  },

  getUsers: async (params?: {
    page?: number;
    page_size?: number;
    role?: string;
    q?: string;
  }): Promise<PaginatedResponse<User>> => {
    return apiClient<PaginatedResponse<User>>('/users', {
      params,
    });
  },
};
