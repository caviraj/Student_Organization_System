import { apiClient } from './client';
import type { PaginatedResponse } from '../types/api';
import type {
  Fundraiser,
  FundraiserDetail,
  Task,
  CreateFundraiserInput,
  CreateTaskInput,
  PatchTaskInput,
  LogIncomeInput,
} from '../features/fundraisers/types';

export const fundraisersApi = {
  getFundraisers: async (page = 1, pageSize = 20): Promise<PaginatedResponse<Fundraiser>> => {
    return apiClient<PaginatedResponse<Fundraiser>>('/fundraisers', {
      params: { page, page_size: pageSize },
    });
  },

  getFundraiser: async (id: string): Promise<FundraiserDetail> => {
    return apiClient<FundraiserDetail>(`/fundraisers/${id}`);
  },

  createFundraiser: async (data: CreateFundraiserInput): Promise<Fundraiser> => {
    return apiClient<Fundraiser>('/fundraisers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getFundraiserTasks: async (fundraiserId: string): Promise<Task[]> => {
    // The board answers with TaskBoardOut ({columns, counts, items}), not a bare array.
    const board = await apiClient<{ items: Task[] }>(`/fundraisers/${fundraiserId}/tasks`);
    return board.items;
  },

  createTask: async (fundraiserId: string, data: CreateTaskInput): Promise<Task> => {
    return apiClient<Task>(`/fundraisers/${fundraiserId}/tasks`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  patchTask: async (taskId: string, data: PatchTaskInput): Promise<Task> => {
    return apiClient<Task>(`/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  logIncome: async (fundraiserId: string, data: LogIncomeInput): Promise<{ message: string; raised: number }> => {
    return apiClient<{ message: string; raised: number }>(`/fundraisers/${fundraiserId}/income`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // ASSUMED ENDPOINT per Gap (a) for volunteers to view their tasks across fundraisers
  getMyTasks: async (): Promise<Task[]> => {
    // /tasks/me answers with a page envelope, not a bare array. 200 is the API's max page_size.
    // shortcut: tasks past the first 200 need real pagination, which no screen asks for yet.
    const page = await apiClient<PaginatedResponse<Task>>('/tasks/me', {
      params: { page_size: 200 },
    });
    return page.items;
  },
};
