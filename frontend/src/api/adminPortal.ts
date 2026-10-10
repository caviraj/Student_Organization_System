import { apiClient } from './client';

export interface DepartmentSummary {
  department: string;
  events_count: number;
  registered_count: number;
  students_count: number;
}

export interface RegisteredStudent {
  student_name: string;
  student_email: string;
  ticket_code: string;
  status: string;
  registered_at: string | null;
}

export interface DepartmentEvent {
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
  ticket_type_name: string;
  price_inr: number;
  registered_students: RegisteredStudent[];
}

export interface DepartmentEventsResponse {
  department: string;
  events: DepartmentEvent[];
  total_events: number;
}

export interface CreateDepartmentEventInput {
  title: string;
  description: string;
  venue?: string;
  department: string;
  starts_at: string;
  ends_at: string;
  capacity: number;
  price_inr?: number;
  banner_url?: string;
}

export interface CompanyProduct {
  id: string;
  name: string;
  description: string | null;
  image_url: string | null;
  price_inr: number;
  base_price_paise: number;
  stock: number;
  is_active: boolean;
  company_name: string;
  note: string;
  variant_id: string | null;
}

export interface CreateCompanyProductInput {
  name: string;
  description?: string;
  price_inr: number;
  stock: number;
  image_url?: string;
  company_name?: string;
}

export const adminPortalApi = {
  getDepartments: async (): Promise<{ departments: DepartmentSummary[] }> => {
    return apiClient('/admin-portal/departments');
  },

  getDepartmentEvents: async (department: string): Promise<DepartmentEventsResponse> => {
    return apiClient(`/admin-portal/departments/${encodeURIComponent(department)}/events`);
  },

  createDepartmentEvent: async (data: CreateDepartmentEventInput): Promise<{ message: string; event_id: string }> => {
    return apiClient('/admin-portal/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getCompanyProducts: async (): Promise<{ products: CompanyProduct[]; total: number; notice: string }> => {
    return apiClient('/admin-portal/products');
  },

  createCompanyProduct: async (data: CreateCompanyProductInput): Promise<{ message: string; product: CompanyProduct }> => {
    return apiClient('/admin-portal/products', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  deleteCompanyProduct: async (productId: string): Promise<{ message: string }> => {
    return apiClient(`/admin-portal/products/${productId}`, {
      method: 'DELETE',
    });
  },

  resetData: async (password: string): Promise<{ success: boolean; message: string }> => {
    return apiClient('/admin-portal/reset-data', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
  },
};

