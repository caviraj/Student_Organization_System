import { apiClient } from './client';
import type { MembershipPlan, PaginatedResponse } from '../types/api';

export interface CreatePlanPayload {
  name: string;
  description?: string | null;
  price: number; // paise
  duration_days: number;
  perks: string[];
  is_active?: boolean;
}

export interface UpdatePlanPayload {
  name?: string;
  description?: string | null;
  price?: number; // paise
  duration_days?: number;
  perks?: string[];
  is_active?: boolean;
}

export const plansApi = {
  getPlans: async (includeInactive = false): Promise<MembershipPlan[]> => {
    // /plans answers with a page envelope, not a bare array. 100 is the API's max page_size.
    // shortcut: plans past the first 100 need real pagination, which no screen asks for yet.
    const page = await apiClient<PaginatedResponse<MembershipPlan>>('/plans', {
      params: { page_size: 100, include_inactive: includeInactive || undefined },
    });
    return page.items;
  },

  createPlan: async (payload: CreatePlanPayload): Promise<MembershipPlan> => {
    return apiClient<MembershipPlan>('/plans', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  updatePlan: async (planId: string, payload: UpdatePlanPayload): Promise<MembershipPlan> => {
    return apiClient<MembershipPlan>(`/plans/${planId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },
};
