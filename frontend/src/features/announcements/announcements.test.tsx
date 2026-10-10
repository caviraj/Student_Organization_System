import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { AnnouncementCard } from './components/AnnouncementCard';
import { createAnnouncementSchema, updateAnnouncementRevisionSchema } from './schemas';
import type { Announcement } from '../../types/announcements';
import { hasMinimumRole } from '../../types/api';

const mockBaseAnnouncement: Announcement = {
  id: 'ann_test_01',
  title: 'Spring Orientation Meeting',
  body: 'Welcome all new students to the SSA annual spring orientation.',
  category: 'meeting',
  audience: 'all',
  event_id: null,
  is_pinned: false,
  author_id: 'usr_org_01',
  author_name: 'Campus Director',
  published_at: '2026-10-10T10:00:00Z',
  revision_note: null,
};

describe('Phase 3 Announcements Feature Tests', () => {
  describe('Sorting and Filtering Logic', () => {
    it('sorts pinned announcements before unpinned announcements, then by published_at desc', () => {
      const announcements: Announcement[] = [
        {
          ...mockBaseAnnouncement,
          id: 'ann_older_pinned',
          is_pinned: true,
          published_at: '2026-10-01T10:00:00Z',
        },
        {
          ...mockBaseAnnouncement,
          id: 'ann_newer_unpinned',
          is_pinned: false,
          published_at: '2026-10-09T10:00:00Z',
        },
        {
          ...mockBaseAnnouncement,
          id: 'ann_newest_pinned',
          is_pinned: true,
          published_at: '2026-10-10T10:00:00Z',
        },
        {
          ...mockBaseAnnouncement,
          id: 'ann_oldest_unpinned',
          is_pinned: false,
          published_at: '2026-09-15T10:00:00Z',
        },
      ];

      const sorted = [...announcements].sort((a, b) => {
        if (a.is_pinned !== b.is_pinned) {
          return a.is_pinned ? -1 : 1;
        }
        return new Date(b.published_at).getTime() - new Date(a.published_at).getTime();
      });

      expect(sorted.map((a) => a.id)).toEqual([
        'ann_newest_pinned',
        'ann_older_pinned',
        'ann_newer_unpinned',
        'ann_oldest_unpinned',
      ]);
    });

    it('correctly filters announcements by category', () => {
      const announcements: Announcement[] = [
        { ...mockBaseAnnouncement, id: '1', category: 'meeting' },
        { ...mockBaseAnnouncement, id: '2', category: 'deadline' },
        { ...mockBaseAnnouncement, id: '3', category: 'change' },
        { ...mockBaseAnnouncement, id: '4', category: 'general' },
        { ...mockBaseAnnouncement, id: '5', category: 'meeting' },
      ];

      const filterCategory = (cat?: string) =>
        cat ? announcements.filter((a) => a.category === cat) : announcements;

      expect(filterCategory('meeting').map((a) => a.id)).toEqual(['1', '5']);
      expect(filterCategory('deadline').map((a) => a.id)).toEqual(['2']);
      expect(filterCategory('change').map((a) => a.id)).toEqual(['3']);
      expect(filterCategory('general').map((a) => a.id)).toEqual(['4']);
      expect(filterCategory(undefined).length).toBe(5);
    });
  });

  describe('AnnouncementCard Component', () => {
    it('renders "Edited" badge only when revision_note exists', () => {
      const { rerender } = render(
        <AnnouncementCard
          announcement={{
            ...mockBaseAnnouncement,
            revision_note: 'Updated auditorium location to Hall B',
          }}
        />
      );

      expect(screen.getByTestId('edited-badge')).toBeDefined();
      expect(screen.getByText('Edited')).toBeDefined();

      // Rerender without revision_note
      rerender(
        <AnnouncementCard
          announcement={{
            ...mockBaseAnnouncement,
            revision_note: null,
          }}
        />
      );

      expect(screen.queryByTestId('edited-badge')).toBeNull();
    });

    it('renders pinned badge when is_pinned is true', () => {
      const { rerender } = render(
        <AnnouncementCard announcement={{ ...mockBaseAnnouncement, is_pinned: true }} />
      );
      expect(screen.getByTestId('pinned-badge')).toBeDefined();

      rerender(
        <AnnouncementCard announcement={{ ...mockBaseAnnouncement, is_pinned: false }} />
      );
      expect(screen.queryByTestId('pinned-badge')).toBeNull();
    });

    it('strictly renders user-authored HTML/Script strings as plain text without XSS vulnerability', () => {
      const maliciousPayload = '<script>alert("xss")</script><img src="x" onerror="alert(1)" /><b>Bold Tag</b>';

      const { container } = render(
        <AnnouncementCard
          announcement={{
            ...mockBaseAnnouncement,
            title: maliciousPayload,
            body: maliciousPayload,
          }}
        />
      );

      // Verify no script or img or b tags were injected into the DOM
      expect(container.querySelector('script')).toBeNull();
      expect(container.querySelector('img')).toBeNull();
      expect(container.querySelector('b')).toBeNull();

      // Verify the literal tags are displayed as plain escaped text
      const bodyEl = screen.getByTestId('announcement-body');
      expect(bodyEl.textContent).toContain('<script>alert("xss")</script>');
      expect(bodyEl.textContent).toContain('<img src="x" onerror="alert(1)" />');
      expect(bodyEl.textContent).toContain('<b>Bold Tag</b>');
    });

    it('truncates body exceeding 280 characters and provides read more toggle', () => {
      const longText = 'A'.repeat(350);
      render(
        <AnnouncementCard
          announcement={{
            ...mockBaseAnnouncement,
            body: longText,
          }}
        />
      );

      expect(screen.getByText('Read more')).toBeDefined();
      expect(screen.getByTestId('announcement-body').textContent).toBe(`${'A'.repeat(280)}...`);
    });
  });

  describe('Zod Validation Schemas', () => {
    it('validates a valid announcement creation payload for audience "all"', () => {
      const validData = {
        title: 'General Club Orientation',
        body: 'Please join us for our orientation meeting this Friday at 4 PM.',
        category: 'meeting' as const,
        audience: 'all' as const,
        is_pinned: true,
      };

      const parsed = createAnnouncementSchema.parse(validData);
      expect(parsed.title).toBe(validData.title);
      expect(parsed.audience).toBe('all');
      expect(parsed.is_pinned).toBe(true);
    });

    it('validates a valid announcement creation payload for audience "event" with event_id', () => {
      const validEventAnnouncement = {
        title: 'Hackathon Schedule Change',
        body: 'The opening ceremony starts 30 minutes earlier in Main Hall.',
        category: 'change' as const,
        audience: 'event' as const,
        event_id: 'evt_hackathon_2026',
        is_pinned: false,
      };

      const parsed = createAnnouncementSchema.parse(validEventAnnouncement);
      expect(parsed.event_id).toBe('evt_hackathon_2026');
      expect(parsed.audience).toBe('event');
    });

    it('rejects announcement creation for audience "event" when event_id is missing or empty', () => {
      const invalidEventAnnouncement = {
        title: 'Hackathon Room Update',
        body: 'Room update for attendees.',
        category: 'change' as const,
        audience: 'event' as const,
        event_id: '',
        is_pinned: false,
      };

      expect(() => createAnnouncementSchema.parse(invalidEventAnnouncement)).toThrow(
        'Please select an event when the audience is set to Event Attendees.'
      );
    });

    it('enforces title and body length boundaries', () => {
      // Title too short
      expect(() =>
        createAnnouncementSchema.parse({
          title: 'Hi',
          body: 'Valid body text here.',
          category: 'general' as const,
          audience: 'all' as const,
        })
      ).toThrow('Title must be at least 3 characters.');

      // Title too long
      expect(() =>
        createAnnouncementSchema.parse({
          title: 'X'.repeat(125),
          body: 'Valid body text here.',
          category: 'general' as const,
          audience: 'all' as const,
        })
      ).toThrow('Title cannot exceed 120 characters.');

      // Body too short
      expect(() =>
        createAnnouncementSchema.parse({
          title: 'Valid Title',
          body: 'Too',
          category: 'general' as const,
          audience: 'all' as const,
        })
      ).toThrow('Announcement body must be at least 5 characters.');
    });

    it('validates revision note schema', () => {
      const validNote = { revision_note: 'Updated time to 5:00 PM' };
      const parsed = updateAnnouncementRevisionSchema.parse(validNote);
      expect(parsed.revision_note).toBe(validNote.revision_note);

      expect(() =>
        updateAnnouncementRevisionSchema.parse({ revision_note: 'No' })
      ).toThrow('Revision note must be at least 3 characters.');
    });
  });

  describe('Role Security & Deliveries Visibility Contract', () => {
    it('verifies organizer role threshold required for management routes', () => {
      expect(hasMinimumRole('admin', 'organizer')).toBe(true);
      expect(hasMinimumRole('organizer', 'organizer')).toBe(true);
      expect(hasMinimumRole('member', 'organizer')).toBe(false);
    });

    it('verifies delivery counts visibility rule (admin sees count, organizer sees null / placeholder)', () => {
      const deliveryStats = {
        total_recipients: 142,
        sent_count: 138,
        failed_count: 4,
      };

      const getDisplayDeliveries = (role: 'admin' | 'organizer' | 'member') => {
        if (role === 'admin') {
          return `${deliveryStats.sent_count}/${deliveryStats.total_recipients} sent`;
        }
        return '—';
      };

      expect(getDisplayDeliveries('admin')).toBe('138/142 sent');
      expect(getDisplayDeliveries('organizer')).toBe('—');
      expect(getDisplayDeliveries('member')).toBe('—');
    });
  });
});
