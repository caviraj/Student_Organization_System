/**
 * Announcement Types & Contracts conforming to docs/DESIGN.md §3 and §5.
 * Golden Rule 1: Never rename/remove fields or endpoints silently.
 */

export type AnnouncementCategory = 'meeting' | 'deadline' | 'change' | 'general';
export type AnnouncementAudience = 'all' | 'members' | 'event';
export type DeliveryChannel = 'email' | 'inapp';
export type DeliveryStatus = 'queued' | 'sent' | 'failed';

export interface Announcement {
  id: string;
  title: string;
  body: string;
  category: AnnouncementCategory;
  audience: AnnouncementAudience;
  event_id: string | null;
  is_pinned: boolean;
  author_id: string;
  author_name: string;
  published_at: string;
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
