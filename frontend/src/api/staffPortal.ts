import { apiClient } from './client';

export interface VerifyTicketResult {
  is_real: boolean;
  status: 'VALID' | 'ALREADY_USED' | 'FAKE';
  message: string;
  scanned_code?: string;
  verified_at?: string;
  ticket_id?: string;
  ticket_code?: string;
  student_name?: string;
  student_email?: string;
  department?: string;
  year?: string;
  section?: string;
  gender?: string;
  event_id?: string;
  event_title?: string;
  event_department?: string;
  event_venue?: string | null;
  event_starts_at?: string | null;
  checked_in_at?: string | null;
  registered_at?: string | null;
  product_bought?: boolean;
  product_name?: string | null;
  payment_status?: string;
  razorpay_payment_id?: string | null;
  total_paid_inr?: number;
}

export interface StaffDepartmentSummary {
  department: string;
  events_count: number;
  registered_students_count: number;
}

export interface StaffDepartmentStudent {
  ticket_id: string;
  ticket_code: string;
  status: string;
  event_id: string;
  event_title: string;
  student_name: string;
  student_email: string;
  department: string;
  year: string;
  section: string;
  gender: string;
  registered_at: string | null;
  checked_in_at: string | null;
  product_bought: boolean;
  product_name: string | null;
  payment_status?: string;
  razorpay_payment_id?: string | null;
  total_paid_inr?: number;
}

export interface StaffDepartmentStudentsResponse {
  department: string;
  events: Array<{
    id: string;
    title: string;
    venue: string | null;
    starts_at: string;
    registered_count: number;
  }>;
  students: StaffDepartmentStudent[];
  total_students: number;
}

export const staffPortalApi = {
  verifyTicket: async (code: string, autoCheckin = true): Promise<VerifyTicketResult> => {
    return apiClient('/staff-portal/verify-ticket', {
      method: 'POST',
      body: JSON.stringify({ code, auto_checkin: autoCheckin }),
    });
  },

  getDepartments: async (): Promise<{ departments: StaffDepartmentSummary[] }> => {
    return apiClient('/staff-portal/departments');
  },

  getDepartmentStudents: async (department: string): Promise<StaffDepartmentStudentsResponse> => {
    return apiClient(`/staff-portal/departments/${encodeURIComponent(department)}/students`);
  },
};
