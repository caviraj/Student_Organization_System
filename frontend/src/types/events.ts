export type EventStatus = 'draft' | 'published' | 'closed';

export interface TicketType {
  id: string;
  event_id: string;
  name: string;
  member_price: number; // Integer paise
  non_member_price: number; // Integer paise
  capacity: number;
  sold_count?: number;
  seats_left?: number;
  sale_starts_at?: string | null;
  sale_ends_at?: string | null;
  created_at?: string;
}

export interface EventItem {
  id: string;
  title: string;
  description: string;
  venue: string;
  starts_at: string;
  ends_at: string;
  banner_url?: string | null;
  status: EventStatus;
  created_at?: string;
  min_price?: number; // Integer paise, lowest price among ticket types
  ticket_types?: TicketType[];
}

export interface EventDetail extends EventItem {
  ticket_types: TicketType[];
}

export interface EventCreateInput {
  title: string;
  description: string;
  venue: string;
  starts_at: string;
  ends_at: string;
  banner_url?: string | null;
  status?: EventStatus;
}

export type EventUpdateInput = Partial<EventCreateInput>;

export interface TicketTypeCreateInput {
  name: string;
  member_price: number; // Integer paise
  non_member_price: number; // Integer paise
  capacity: number;
  sale_starts_at?: string | null;
  sale_ends_at?: string | null;
}

export interface TicketCheckoutRequest {
  ticket_type_id: string;
  quantity: number;
}

export interface TicketCheckoutResponse {
  order_id: string;
  payment_id: string;
  amount: number; // Integer paise
  provider: string;
  status: string;
  event_title?: string;
  ticket_type_name?: string;
  quantity?: number;
  unit_price?: number; // Integer paise
  is_member_price?: boolean;
}

export type TicketStatus = 'valid' | 'used' | 'void';

export interface TicketItem {
  id: string;
  order_id: string;
  event_id: string;
  event_title: string;
  venue: string;
  starts_at: string;
  ends_at?: string;
  ticket_type_name: string;
  code: string;
  status: TicketStatus;
  price_paid: number; // Integer paise
  is_member_price: boolean;
  checked_in_at?: string | null;
  user_name?: string;
  user_email?: string;
}

export type CheckInResult = 'VALID' | 'ALREADY_USED' | 'INVALID' | 'WRONG_EVENT';

export interface CheckInRequest {
  event_id: string;
  code: string;
}

export interface CheckInResponse {
  result: CheckInResult;
  ticket?: TicketItem | null;
  checked_in_at?: string | null;
}

export interface RevenueBreakdown {
  member: number; // Integer paise
  non_member: number; // Integer paise
  total: number; // Integer paise
}

export interface EventReport {
  sold: number;
  seats_left: number;
  checked_in: number;
  no_shows: number;
  attendance_rate: number; // Percentage, e.g. 85.5
  revenue: RevenueBreakdown;
}

export interface AttendeeItem {
  id: string;
  ticket_code: string;
  user_name: string;
  user_email: string;
  ticket_type_name: string;
  price_paid: number; // Integer paise
  is_member_price: boolean;
  status: TicketStatus;
  checked_in_at?: string | null;
}
