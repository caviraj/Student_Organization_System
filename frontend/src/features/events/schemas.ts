import { z } from 'zod';

export const eventFormSchema = z
  .object({
    title: z.string().trim().min(1, 'Title is required').max(200, 'Title is too long'),
    description: z.string().trim().min(1, 'Description is required'),
    venue: z.string().trim().min(1, 'Venue is required').max(200, 'Venue is too long'),
    starts_at: z.string().min(1, 'Start date and time are required'),
    ends_at: z.string().min(1, 'End date and time are required'),
    banner_url: z
      .string()
      .trim()
      .optional()
      .refine(
        (val) => !val || val === '' || /^https?:\/\/.+/i.test(val),
        'Must be a valid web URL starting with http:// or https://'
      ),
    status: z.enum(['draft', 'published', 'closed']).default('draft'),
  })
  .refine(
    (data) => {
      if (!data.starts_at || !data.ends_at) return true;
      const start = new Date(data.starts_at).getTime();
      const end = new Date(data.ends_at).getTime();
      return end > start;
    },
    {
      message: 'End date and time must be strictly after the start date and time',
      path: ['ends_at'],
    }
  );

export type EventFormData = z.infer<typeof eventFormSchema>;

export const ticketTypeFormSchema = z
  .object({
    name: z.string().trim().min(1, 'Ticket name is required').max(100, 'Name is too long'),
    member_price_inr: z.number().min(0, 'Member price cannot be negative'),
    non_member_price_inr: z.number().min(0, 'Non-member price cannot be negative'),
    capacity: z.number().int().min(1, 'Capacity must be at least 1 seat'),
    sale_starts_at: z.string().optional().nullable(),
    sale_ends_at: z.string().optional().nullable(),
  })
  .refine((data) => data.member_price_inr <= data.non_member_price_inr, {
    message: 'Member price cannot exceed regular price',
    path: ['member_price_inr'],
  });

export type TicketTypeFormData = z.infer<typeof ticketTypeFormSchema>;

export const checkInSchema = z.object({
  event_id: z.string().min(1, 'Event ID is required'),
  code: z.string().trim().min(1, 'Ticket code is required'),
});

export type CheckInFormData = z.infer<typeof checkInSchema>;
