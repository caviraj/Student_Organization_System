import { apiClient } from './client';

export interface StudentDepartmentSummary {
  department: string;
  events_count: number;
  registered_count: number;
}

export interface StudentEventProduct {
  id: string;
  name: string;
  description: string | null;
  price_inr: number;
  image_url: string | null;
}

export interface StudentEventItem {
  id: string;
  title: string;
  description: string | null;
  venue: string | null;
  starts_at: string;
  ends_at: string;
  banner_url: string | null;
  status: string;
  department: string;
  capacity: number;
  sold_count: number;
  registered_count: number;
  ticket_type_id: string;
  ticket_type_name: string;
  price_inr: number;
  is_free?: boolean;
  is_sold_out?: boolean;
  is_registered?: boolean;
  user_ticket_code?: string | null;
  related_products: StudentEventProduct[];
}

export interface StudentCreateOrderPayload {
  event_id: string;
  buy_product?: boolean;
  product_id?: string | null;
}

export interface StudentCreateOrderResponse {
  is_free: boolean;
  key_id: string;
  gateway_order_id: string;
  amount: number;
  currency: string;
  total_inr: number;
}

export interface StudentRegisterPayload {
  event_id: string;
  name: string;
  department: string;
  year: string;
  section: string;
  gender: string;
  email: string;
  buy_product?: boolean;
  product_id?: string | null;
  razorpay_payment_id?: string | null;
  razorpay_order_id?: string | null;
  razorpay_signature?: string | null;
}

export interface StudentTicketItem {
  ticket_id: string;
  ticket_code: string;
  status: string;
  event_id: string;
  event_title: string;
  event_department: string;
  event_venue: string | null;
  event_starts_at: string | null;
  event_ends_at: string | null;
  student_name: string;
  student_email: string;
  department: string;
  year: string;
  section: string;
  gender: string;
  buy_product: boolean;
  product_name: string | null;
  product_price_inr: number;
  payment_status?: string;
  razorpay_payment_id?: string | null;
  total_paid_inr: number;
  registered_at: string | null;
  checked_in_at: string | null;
}

export const studentPortalApi = {
  getDepartments: async (): Promise<{ departments: StudentDepartmentSummary[] }> => {
    return apiClient('/student-portal/departments');
  },

  getDepartmentEvents: async (
    department: string
  ): Promise<{ department: string; events: StudentEventItem[]; total_events: number }> => {
    return apiClient(`/student-portal/departments/${encodeURIComponent(department)}/events`);
  },

  createOrder: async (payload: StudentCreateOrderPayload): Promise<StudentCreateOrderResponse> => {
    return apiClient('/student-portal/create-order', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  register: async (payload: StudentRegisterPayload): Promise<{
    message: string;
    ticket_id: string;
    ticket_code: string;
    order_id: string;
    event_id: string;
    event_title: string;
    student_name: string;
    student_email: string;
    department: string;
    year: string;
    section: string;
    gender: string;
    product_bought: boolean;
    product_name: string | null;
    payment_status?: string;
    razorpay_payment_id?: string | null;
    total_paid_inr: number;
    registered_at: string;
  }> => {
    return apiClient('/student-portal/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getMyTickets: async (): Promise<{ tickets: StudentTicketItem[]; total: number }> => {
    return apiClient('/student-portal/my-tickets');
  },
};
