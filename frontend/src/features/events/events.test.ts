import { describe, it, expect } from 'vitest';
import { eventFormSchema, ticketTypeFormSchema, checkInSchema } from './schemas';
import { formatINR } from '../../lib/formatINR';

describe('Phase 2 Event Schemas', () => {
  it('validates a correct ticket type', () => {
    const validTier = {
      name: 'General Admission',
      non_member_price_inr: 250,
      member_price_inr: 150,
      capacity: 100,
    };
    const parsed = ticketTypeFormSchema.parse(validTier);
    expect(parsed.name).toBe('General Admission');
    expect(parsed.non_member_price_inr).toBe(250);
    expect(parsed.member_price_inr).toBe(150);
    expect(parsed.capacity).toBe(100);
  });

  it('rejects tier when member_price_inr > non_member_price_inr', () => {
    const invalidTier = {
      name: 'VIP Pass',
      non_member_price_inr: 200,
      member_price_inr: 250,
      capacity: 50,
    };
    expect(() => ticketTypeFormSchema.parse(invalidTier)).toThrow(
      'Member price cannot exceed regular price'
    );
  });

  it('validates a complete event form payload', () => {
    const validEvent = {
      title: 'Annual Tech Symposium',
      description: 'The premier student tech festival with keynotes and workshops.',
      venue: 'Main Auditorium, North Wing',
      starts_at: '2026-10-15T09:00:00Z',
      ends_at: '2026-10-15T17:00:00Z',
      status: 'published' as const,
    };

    const parsed = eventFormSchema.parse(validEvent);
    expect(parsed.title).toBe('Annual Tech Symposium');
    expect(parsed.status).toBe('published');
  });

  it('rejects event when ends_at is before or equal to starts_at', () => {
    const invalidEvent = {
      title: 'Invalid Time Event',
      description: 'An event where time is broken.',
      venue: 'Lab 1',
      starts_at: '2026-10-15T17:00:00Z',
      ends_at: '2026-10-15T09:00:00Z', // ends before it starts
      status: 'draft' as const,
    };

    expect(() => eventFormSchema.parse(invalidEvent)).toThrow(
      'End date and time must be strictly after the start date and time'
    );
  });

  it('validates check-in payload', () => {
    const validCheckIn = {
      event_id: 'evt_tech_fest_2026',
      code: 'TCK-TECH-2026-0001',
    };
    const parsed = checkInSchema.parse(validCheckIn);
    expect(parsed.event_id).toBe('evt_tech_fest_2026');
    expect(parsed.code).toBe('TCK-TECH-2026-0001');
  });

  it('rejects empty ticket code in check-in', () => {
    const invalidCheckIn = {
      event_id: 'evt_tech_fest_2026',
      code: '   ',
    };
    expect(() => checkInSchema.parse(invalidCheckIn)).toThrow();
  });

  it('correctly calculates member savings in paise using formatINR', () => {
    const regularPricePaise = 25000;
    const memberPricePaise = 15000;
    const savingsPaise = regularPricePaise - memberPricePaise;

    expect(savingsPaise).toBe(10000);
    expect(formatINR(savingsPaise).replace(/\u00a0/g, ' ')).toBe('₹100');
    expect(formatINR(regularPricePaise).replace(/\u00a0/g, ' ')).toBe('₹250');
    expect(formatINR(memberPricePaise).replace(/\u00a0/g, ' ')).toBe('₹150');
  });
});
