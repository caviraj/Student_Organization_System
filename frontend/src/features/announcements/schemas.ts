import { z } from 'zod';

export const announcementCategorySchema = z.enum(['meeting', 'deadline', 'change', 'general'], {
  message: 'Please select a valid announcement category.',
});

export const announcementAudienceSchema = z.enum(['all', 'members', 'event'], {
  message: 'Please select a valid audience group.',
});

export const createAnnouncementSchema = z
  .object({
    title: z
      .string()
      .min(3, 'Title must be at least 3 characters.')
      .max(120, 'Title cannot exceed 120 characters.')
      .trim(),
    body: z
      .string()
      .min(5, 'Announcement body must be at least 5 characters.')
      .max(2000, 'Announcement body cannot exceed 2000 characters.')
      .trim(),
    category: announcementCategorySchema,
    audience: announcementAudienceSchema,
    event_id: z.string().optional().nullable(),
    is_pinned: z.boolean().default(false),
  })
  .refine(
    (data) => {
      if (data.audience === 'event') {
        return !!data.event_id && data.event_id.trim().length > 0;
      }
      return true;
    },
    {
      message: 'Please select an event when the audience is set to Event Attendees.',
      path: ['event_id'],
    }
  );

export type CreateAnnouncementFormData = z.infer<typeof createAnnouncementSchema>;

export const updateAnnouncementRevisionSchema = z.object({
  revision_note: z
    .string()
    .min(3, 'Revision note must be at least 3 characters.')
    .max(255, 'Revision note cannot exceed 255 characters.')
    .trim(),
});

export type UpdateAnnouncementRevisionFormData = z.infer<typeof updateAnnouncementRevisionSchema>;
