import { ApiError, type ApiErrorShape } from '../types/api';

const TOKEN_KEY = 'ssa_token';

export const getStoredToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

export const setStoredToken = (token: string | null) => {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
};

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
}

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, ...restOptions } = options;

  let url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString;
    }
  }

  const token = getStoredToken();
  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(headers as Record<string, string>),
  };

  if (token) {
    requestHeaders['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...restOptions,
    headers: requestHeaders,
  });

  if (response.status === 401) {
    // Notify application of expired or invalid session
    setStoredToken(null);
    window.dispatchEvent(new CustomEvent('ssa_auth_unauthorized'));
  }

  if (!response.ok) {
    let errorData: ApiErrorShape | null = null;
    try {
      errorData = (await response.json()) as ApiErrorShape;
    } catch {
      // response is not json
    }

    const code = errorData?.error?.code || 'UNKNOWN_ERROR';
    const message = errorData?.error?.message || response.statusText || 'An error occurred';
    const details = errorData?.error?.details;

    throw new ApiError(response.status, code, message, details);
  }

  // Handle empty bodies (204 No Content, etc.)
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}
