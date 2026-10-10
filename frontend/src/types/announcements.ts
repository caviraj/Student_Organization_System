/**
 * Announcement Types & Contracts conforming to docs/DESIGN.md §3 and §5.
 * Golden Rule 1: Never rename/remove fields or endpoints silently.
 */

export type AnnouncementCategory = 'meeting' | 'deadline' | 'change' | 'general';
export type AnnouncementAudience = 'all' | 'members' | 'event';
export type DeliveryChannel = 'email' | 'inapp';
export type DeliveryStatus = 'queued' | 'sent' | 'failed';

/** The fields every announcement carries, in the list and on its own page alike (DESIGN.md §5). */
export interface AnnouncementBase {
  id: string;
  title: string;
  category: AnnouncementCategory;
  audience: AnnouncementAudience;
  event_id: string | null;
  is_pinned: boolean;
  author_name: string | null;
  published_at: string;
  /** Null until the post is edited. The list carries this, not the revision note. */
  edited_at: string | null;
}

/** GET /announcements - the feed. The body arrives truncated to its first 200 characters. */
export interface Announcement extends AnnouncementBase {
  body_preview: string;
}

/** GET /announcements/{id}, and what POST/PATCH answer with. The only shape with the whole body. */
export interface AnnouncementDetail extends AnnouncementBase {
  body: string;
  revision_note: string | null;
}

export interface AnnouncementDelivery {
  id: string;
  announcement_id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  channel: DeliveryChannel;
  status: DeliveryStatus;
  sent_at: string | null;
}

export interface AnnouncementDeliveryCounts {
  queued: number;
  sent: number;
  failed: number;
  total: number;
}

export interface CreateAnnouncementPayload {
  title: string;
  body: string;
  category: AnnouncementCategory;
  audience: AnnouncementAudience;
  event_id?: string | null;
  is_pinned?: boolean;
}

export interface UpdateAnnouncementPayload {
  revision_note: string;
}

export interface AnnouncementFilterParams {
  category?: AnnouncementCategory;
  page?: number;
  page_size?: number;
}
