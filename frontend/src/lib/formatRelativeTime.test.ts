import { describe, it, expect } from 'vitest';
import { formatRelativeTime } from './formatRelativeTime';

describe('formatRelativeTime', () => {
  const base = new Date('2026-10-10T12:00:00Z');

  it('handles null, undefined, and invalid date strings gracefully', () => {
    expect(formatRelativeTime(null, base)).toBe('—');
    expect(formatRelativeTime(undefined, base)).toBe('—');
    expect(formatRelativeTime('invalid-date', base)).toBe('—');
  });

  it('formats recent times as "Just now"', () => {
    const justNow = new Date('2026-10-10T11:59:30Z').toISOString();
    expect(formatRelativeTime(justNow, base)).toBe('Just now');
  });

  it('formats minutes ago properly', () => {
    const oneMinAgo = new Date('2026-10-10T11:59:00Z').toISOString();
    expect(formatRelativeTime(oneMinAgo, base)).toBe('1 minute ago');

    const tenMinAgo = new Date('2026-10-10T11:50:00Z').toISOString();
    expect(formatRelativeTime(tenMinAgo, base)).toBe('10 minutes ago');
  });

  it('formats hours ago properly', () => {
    const oneHourAgo = new Date('2026-10-10T11:00:00Z').toISOString();
    expect(formatRelativeTime(oneHourAgo, base)).toBe('1 hour ago');

    const fourHoursAgo = new Date('2026-10-10T08:00:00Z').toISOString();
    expect(formatRelativeTime(fourHoursAgo, base)).toBe('4 hours ago');
  });

  it('formats days ago and yesterday properly', () => {
    const yesterday = new Date('2026-10-09T10:00:00Z').toISOString();
    expect(formatRelativeTime(yesterday, base)).toBe('Yesterday');

    const threeDaysAgo = new Date('2026-10-07T12:00:00Z').toISOString();
    expect(formatRelativeTime(threeDaysAgo, base)).toBe('3 days ago');
  });

  it('formats weeks ago and older dates', () => {
    const twoWeeksAgo = new Date('2026-09-26T12:00:00Z').toISOString();
    expect(formatRelativeTime(twoWeeksAgo, base)).toBe('2 weeks ago');

    const twoMonthsAgo = new Date('2026-08-01T12:00:00Z').toISOString();
    // Falls back to formatDate (e.g. "01 Aug 2026" or locale string)
    expect(formatRelativeTime(twoMonthsAgo, base)).toContain('2026');
  });
});
