import { apiClient } from './client';
import type { MembershipPlan, PaginatedResponse } from '../types/api';

export interface CreatePlanPayload {
  name: string;
  description?: string | null;
  price: number; // paise
  duration_months: number;
  ticket_discount_pct?: number;
  merch_discount_pct?: number;
  is_active?: boolean;
}

export interface UpdatePlanPayload {
  name?: string;
  description?: string | null;
  price?: number; // paise
  duration_months?: number;
  ticket_discount_pct?: number;
  merch_discount_pct?: number;
  is_active?: boolean;
}

/** A plan's perks are its discounts - the contract has no free-text perks list (DESIGN.md 5). */
export function planPerks(
  plan: Pick<MembershipPlan, 'ticket_discount_pct' | 'merch_discount_pct'>
): string[] {
  return [
    'Standard SSA Hub member privileges',
    ...(plan.ticket_discount_pct > 0 ? [`${plan.ticket_discount_pct}% off event tickets`] : []),
    ...(plan.merch_discount_pct > 0 ? [`${plan.merch_discount_pct}% off club merchandise`] : []),
  ];
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
