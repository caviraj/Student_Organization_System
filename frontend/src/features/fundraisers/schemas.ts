import { z } from 'zod';

export const FundraiserStatusSchema = z.enum(['planning', 'active', 'done']);
export type FundraiserStatus = z.infer<typeof FundraiserStatusSchema>;

export const TaskStatusSchema = z.enum(['todo', 'doing', 'done']);
export type TaskStatus = z.infer<typeof TaskStatusSchema>;

export const FundraiserProgressSchema = z.object({
  tasks_total: z.number().int().nonnegative(),
  done: z.number().int().nonnegative(),
  overdue: z.number().int().nonnegative(),
  raised: z.number().int().nonnegative(), // integer paise
  goal: z.number().int().nonnegative(), // integer paise
});
export type FundraiserProgress = z.infer<typeof FundraiserProgressSchema>;

export const FundraiserSchema = z.object({
  id: z.string().uuid(),
  title: z.string().min(1, 'Title is required'),
  description: z.string().default(''),
  goal_amount: z.number().int().positive('Goal amount must be positive'), // paise
  event_date: z.string(), // YYYY-MM-DD
  status: FundraiserStatusSchema,
  owner_id: z.string().uuid(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  progress: FundraiserProgressSchema.optional(),
});
export type Fundraiser = z.infer<typeof FundraiserSchema>;

export const FundraiserDetailSchema = FundraiserSchema.extend({
  progress: FundraiserProgressSchema,
});
export type FundraiserDetail = z.infer<typeof FundraiserDetailSchema>;

export const TaskSchema = z.object({
  id: z.string().uuid(),
  fundraiser_id: z.string().uuid().nullable().optional(),
  event_id: z.string().uuid().nullable().optional(),
  title: z.string().min(1, 'Title is required'),
  description: z.string().default(''),
  category: z.string().min(1, 'Category is required'),
  assignee_id: z.string().nullable().optional(),
  assignee_name: z.string().optional(), // optimistic/fallback enhancement if available
  due_date: z.string(), // YYYY-MM-DD
  status: TaskStatusSchema,
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});
export type Task = z.infer<typeof TaskSchema>;

export const CreateFundraiserSchema = z.object({
  title: z.string().min(2, 'Title must be at least 2 characters'),
  description: z.string().default(''),
  goal_amount: z.number().int().positive('Goal must be greater than zero'), // paise
  event_date: z.string().min(1, 'Event date is required'),
  status: FundraiserStatusSchema.default('planning'),
});
export type CreateFundraiserInput = z.infer<typeof CreateFundraiserSchema>;

export const CreateTaskSchema = z.object({
  title: z.string().min(2, 'Title must be at least 2 characters'),
  description: z.string().default(''),
  category: z.string().min(1, 'Category is required'),
  due_date: z.string().min(1, 'Due date is required'),
  assignee_id: z.string().nullable().optional(),
  status: TaskStatusSchema.default('todo'),
});
export type CreateTaskInput = z.infer<typeof CreateTaskSchema>;

export const PatchTaskSchema = z.object({
  status: TaskStatusSchema.optional(),
  assignee_id: z.string().nullable().optional(),
});
export type PatchTaskInput = z.infer<typeof PatchTaskSchema>;

export const LogIncomeSchema = z.object({
  amount: z.number().int().positive('Amount must be greater than zero'), // paise
  note: z.string().optional(),
});
export type LogIncomeInput = z.infer<typeof LogIncomeSchema>;
