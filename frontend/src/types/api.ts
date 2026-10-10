/**
 * Strictly typed API contract conforming to docs/DESIGN.md §5 and backend Pydantic schemas.
 * Golden Rule 1: Never rename/remove fields or endpoints silently.
 * Golden Rule 3: Money = integer paise.
 */

export type Role = 'guest' | 'member' | 'volunteer' | 'organizer' | 'treasurer' | 'admin';

export const ROLE_HIERARCHY: Record<Role, number> = {
  guest: 0,
  member: 1,
  volunteer: 2,
  organizer: 3,
  treasurer: 4,
  admin: 5,
};

export function hasMinimumRole(userRole: Role, requiredRole: Role): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole];
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  department?: string | null;
  year?: number | null;
  role: Role;
  email_opt_in?: boolean;
  created_at: string;
  updated_at: string;
}

export interface MembershipSummary {
  status: 'active' | 'expired' | 'none';
  plan_name: string | null;
  plan_id?: string | null;
  end_date: string | null;
  days_left: number | null;
}

export interface UserMe extends User {
  membership: MembershipSummary | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface MembershipPlan {
  id: string;
  name: string;
  description?: string | null;
  price: number; // in integer paise!
  duration_months: number;
  /** What the plan is worth to a member: both discounts are applied at purchase time. */
  ticket_discount_pct: number;
  merch_discount_pct: number;
  is_active: boolean;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  phone?: string;
  department?: string;
  year?: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface Membership {
  id: string;
  user_id: string;
  plan_id: string;
  status: 'active' | 'expired';
  start_date: string;
  end_date: string;
  auto_renew: boolean;
  created_at: string;
  user?: User;
  plan?: MembershipPlan;
  member_code?: string;
  plan_name?: string;
  valid_until?: string;
}

export interface RenewalDueItem {
  membership_id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  plan_name: string;
  end_date: string;
  days_left: number;
  status: string;
  member_code?: string;
  full_name?: string;
  email?: string;
  valid_until?: string;
  days_remaining?: number;
}

export interface CheckoutResponse {
  order_id: string;
  payment_id: string;
  amount: number; // in integer paise
  provider: string;
  status: string;
  plan_name?: string;
}

// One shape for both settlement paths: the mock confirm and the real gateway callback answer
// exactly the same body, because both go through the same dispatcher.
export interface PaymentResultResponse {
  order_id: string;
  payment_id: string;
  order_status: string;
  payment_status: string;
  provider_ref: string;
  status?: string;
  message?: string;
  membership?: {
    id: string;
    status: string;
    end_date: string;
  } | null;
}

export interface MemberCard {
  member_code: string;
  full_name: string;
  status: 'active' | 'expired' | 'none';
  valid_until: string;
  days_remaining?: number | null;
  role?: Role;
  plan_name?: string | null;
  qr_payload?: string;
}

export interface VerifyResponse {
  valid: boolean;
  status?: string | null;
  name?: string | null;
  member_code?: string | null;
  valid_until?: string | null;
  reason?: string | null;
  member?: {
    full_name: string;
    member_code: string;
    role?: Role;
    plan_name?: string | null;
    valid_until?: string | null;
  };
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiErrorShape {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface PaymentIntent {
  order_id: string;
  kind: 'membership' | 'ticket' | 'merch';
  order_status: string;
  amount: number; // integer paise
  currency: string;
  provider: 'mock' | 'razorpay';
  payment_status: string | null;
  key_id: string | null;
  gateway_order_id: string | null;
}

export interface RazorpayVerifyPayload {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}
