import { apiClient, setStoredToken } from './client';
import type { AuthResponse, UserMe } from '../types/api';

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

export const authApi = {
  register: async (payload: RegisterPayload): Promise<AuthResponse> => {
    const res = await apiClient<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setStoredToken(res.access_token);
    return res;
  },

  login: async (payload: LoginPayload): Promise<AuthResponse> => {
    const res = await apiClient<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setStoredToken(res.access_token);
    return res;
  },

  getMe: async (): Promise<UserMe> => {
    return apiClient<UserMe>('/auth/me');
  },

  updateEmailPreferences: async (payload: { email_opt_in: boolean }): Promise<UserMe> => {
    return apiClient<UserMe>('/users/me/email-preferences', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  logout: () => {
    setStoredToken(null);
  },
};
