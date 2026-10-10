import { apiClient } from './client';
import type { MembershipPlan } from '../types/api';

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
    return apiClient<MembershipPlan[]>('/plans', {
      params: includeInactive ? { include_inactive: true } : undefined,
    });
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
