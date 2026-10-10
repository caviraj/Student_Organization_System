import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Megaphone,
  ArrowLeft,
  Users,
  AlertTriangle,
  Pin,
  Send,
  Eye,
  CheckCircle2,
} from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../context/AuthContext';
import { announcementsApi } from '../../api/announcements';
import { eventsApi } from '../../api/events';
import { createAnnouncementSchema } from '../../features/announcements/schemas';
import { AnnouncementCard } from '../../features/announcements/components/AnnouncementCard';
import type {
  Announcement,
  AnnouncementCategory,
  AnnouncementAudience,
} from '../../types/announcements';

const AUDIENCE_DETAILS: Record<
  AnnouncementAudience,
  { label: string; description: string; estimate: string }
> = {
  all: {
    label: 'All Campus (Public)',
    description: 'Visible on the public feed and delivered to all opt-in subscribers.',
    estimate: '~500+ campus members & guests',
  },
  members: {
    label: 'Active Members Only',
    description: 'Exclusive to authenticated members with an active paid membership tier.',
    estimate: '~120 active members',
  },
  event: {
    label: 'Event Attendees',
    description: 'Targeted directly to registered ticket holders for a specific event.',
    estimate: 'Ticket holders for the selected event',
  },
};

const CATEGORIES: { value: AnnouncementCategory; label: string; desc: string }[] = [
  { value: 'general', label: 'General Announcement', desc: 'Club news, stories, community highlights' },
  { value: 'meeting', label: 'Meeting Notice', desc: 'General body meetings, officer syncs, workshops' },
  { value: 'deadline', label: 'Deadline Alert', desc: 'Registrations closing, fee due dates, submissions' },
  { value: 'change', label: 'Schedule / Venue Change', desc: 'Important time shifts, room updates, relocations' },
];

export function AnnouncementComposer() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { success, error: showError } = useToast();

  // Form State
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [category, setCategory] = useState<AnnouncementCategory>('general');
  const [audience, setAudience] = useState<AnnouncementAudience>('all');
  const [eventId, setEventId] = useState<string>('');
  const [isPinned, setIsPinned] = useState(false);

  // Validation & UI State
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  // Fetch events for audience === 'event'
  const { data: eventsData, isLoading: isLoadingEvents } = useQuery({
    queryKey: ['eventsForComposer'],
    queryFn: () => eventsApi.getEvents(),
    enabled: audience === 'event',
  });

  const availableEvents = eventsData?.items ?? [];

  const [previewPublishedAt] = useState(() => new Date().toISOString());

  // Live Preview Announcement
  const previewAnnouncement: Announcement = {
    id: 'preview-draft',
    title: title.trim() || 'Your Announcement Title',
    body:
      body.trim() ||
      'This is a real-time preview of how your announcement will render on the public feed and in email notifications.',
    category,
    audience,
    event_id: audience === 'event' && eventId ? eventId : null,
    is_pinned: isPinned,
    author_id: user?.id || 'preview-author',
    author_name: user?.full_name || 'Organizer',
    published_at: previewPublishedAt,
    revision_note: null,
  };

  const handleValidate = () => {
    setFieldErrors({});
    const validationResult = createAnnouncementSchema.safeParse({
      title,
      body,
      category,
      audience,
      event_id: audience === 'event' ? eventId : null,
      is_pinned: isPinned,
    });

    if (!validationResult.success) {
      const errors: Record<string, string> = {};
      validationResult.error.issues.forEach((err) => {
        if (err.path[0]) {
          errors[String(err.path[0])] = err.message;
        }
      });
      setFieldErrors(errors);
      return false;
    }

    return true;
  };

  const handleOpenConfirm = (e: React.FormEvent) => {
    e.preventDefault();
    if (handleValidate()) {
      setShowConfirmModal(true);
    }
  };

  const handleConfirmPublish = async () => {
    setIsSubmitting(true);
    try {
      await announcementsApi.createAnnouncement({
        title: title.trim(),
        body: body.trim(),
        category,
        audience,
        event_id: audience === 'event' ? eventId : undefined,
        is_pinned: isPinned,
      });

      success('Announcement published successfully.');
      setShowConfirmModal(false);
      navigate('/manage/announcements');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to publish announcement. Please try again.';
      showError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Breadcrumb / Back Link */}
      <div className="mb-6">
        <Link
          to="/manage/announcements"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Announcements Management
        </Link>
      </div>

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-2">
            <Megaphone className="w-3.5 h-3.5" />
            Announcement Composer
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">Draft New Announcement</h1>
          <p className="text-sm text-slate-400 mt-1">
            Broadcast updates to members, event attendees, or the broader campus community.
          </p>
        </div>
      </div>

      {/* Two-Column Grid: Form + Live Preview */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Form */}
        <div className="lg:col-span-7">
          <Card className="border-slate-800 bg-slate-900/90 text-slate-100 shadow-xl">
            <CardHeader className="border-b border-slate-800 pb-4">
              <CardTitle className="text-lg font-bold text-white flex items-center gap-2">
                <Megaphone className="w-5 h-5 text-indigo-400" />
                Announcement Details
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-6">
              <form onSubmit={handleOpenConfirm} className="space-y-6">
                {/* Title */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="announcement-title" className="text-sm font-semibold text-slate-200">
                      Title <span className="text-rose-400">*</span>
                    </label>
                    <span className={`text-xs ${title.length > 120 ? 'text-rose-400 font-bold' : 'text-slate-400'}`}>
                      {title.length}/120
                    </span>
                  </div>
                  <input
                    id="announcement-title"
                    type="text"
                    value={title}
                    onChange={(e) => {
                      setTitle(e.target.value);
                      if (fieldErrors.title) {
                        setFieldErrors((prev) => ({ ...prev, title: '' }));
                      }
                    }}
                    placeholder="e.g., General Body Meeting Rescheduled to Room 304"
                    maxLength={140}
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-700 text-white placeholder-slate-500 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 text-sm transition-all"
                    required
                  />
                  {fieldErrors.title && (
                    <p className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      {fieldErrors.title}
                    </p>
                  )}
                </div>

                {/* Category & Audience Row */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Category */}
                  <div>
                    <label htmlFor="announcement-category" className="block text-sm font-semibold text-slate-200 mb-1.5">
                      Category <span className="text-rose-400">*</span>
                    </label>
                    <select
                      id="announcement-category"
                      value={category}
                      onChange={(e) => setCategory(e.target.value as AnnouncementCategory)}
                      className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-700 text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
                    >
                      {CATEGORIES.map((cat) => (
                        <option key={cat.value} value={cat.value}>
                          {cat.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Audience */}
                  <div>
                    <label htmlFor="announcement-audience" className="block text-sm font-semibold text-slate-200 mb-1.5">
                      Target Audience <span className="text-rose-400">*</span>
                    </label>
                    <select
                      id="announcement-audience"
                      value={audience}
                      onChange={(e) => {
                        const newAudience = e.target.value as AnnouncementAudience;
                        setAudience(newAudience);
                        if (newAudience !== 'event') {
                          setEventId('');
                        }
                        if (fieldErrors.event_id) {
                          setFieldErrors((prev) => ({ ...prev, event_id: '' }));
                        }
                      }}
                      className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-700 text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
                    >
                      <option value="all">All Campus & Community</option>
                      <option value="members">Active Paid Members Only</option>
                      <option value="event">Specific Event Attendees</option>
                    </select>
                  </div>
                </div>

                {/* Event Selector (Conditional on audience === 'event') */}
                {audience === 'event' && (
                  <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-800/40 space-y-2">
                    <label htmlFor="announcement-event-id" className="block text-sm font-semibold text-indigo-200">
                      Select Target Event <span className="text-rose-400">*</span>
                    </label>
                    {isLoadingEvents ? (
                      <div className="h-10 bg-slate-800 animate-pulse rounded-lg" />
                    ) : (
                      <select
                        id="announcement-event-id"
                        value={eventId}
                        onChange={(e) => {
                          setEventId(e.target.value);
                          if (fieldErrors.event_id) {
                            setFieldErrors((prev) => ({ ...prev, event_id: '' }));
                          }
                        }}
                        className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/90 border border-indigo-700/50 text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                        required
                      >
                        <option value="">-- Choose an Event --</option>
                        {availableEvents.map((evt) => (
                          <option key={evt.id} value={evt.id}>
                            {evt.title} ({evt.status})
                          </option>
                        ))}
                      </select>
                    )}
                    {fieldErrors.event_id && (
                      <p className="text-xs text-rose-400 mt-1 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />
                        {fieldErrors.event_id}
                      </p>
                    )}
                    <p className="text-xs text-indigo-300/80">
                      Only students who hold tickets for this event will receive this notification.
                    </p>
                  </div>
                )}

                {/* Audience Reach Indicator */}
                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-start gap-3">
                  <Users className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <div className="text-xs space-y-0.5">
                    <span className="font-semibold text-slate-200">
                      {AUDIENCE_DETAILS[audience].label}:
                    </span>{' '}
                    <span className="text-slate-400">{AUDIENCE_DETAILS[audience].description}</span>
                    <div className="text-emerald-400 font-medium pt-0.5">
                      Estimated reach: {AUDIENCE_DETAILS[audience].estimate}
                    </div>
                  </div>
                </div>

                {/* Body */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="announcement-body" className="text-sm font-semibold text-slate-200">
                      Message Content <span className="text-rose-400">*</span>
                    </label>
                    <span className={`text-xs ${body.length > 2000 ? 'text-rose-400 font-bold' : 'text-slate-400'}`}>
                      {body.length}/2000
                    </span>
                  </div>
                  <textarea
                    id="announcement-body"
                    rows={6}
                    value={body}
                    onChange={(e) => {
                      setBody(e.target.value);
                      if (fieldErrors.body) {
                        setFieldErrors((prev) => ({ ...prev, body: '' }));
                      }
                    }}
                    placeholder="Provide full details, agenda, room changes, or action items. Markdown or special characters will be safely escaped and displayed as plain text."
                    className="w-full px-4 py-3 rounded-xl bg-slate-950/80 border border-slate-700 text-white placeholder-slate-500 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 text-sm transition-all"
                    required
                  />
                  {fieldErrors.body && (
                    <p className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      {fieldErrors.body}
                    </p>
                  )}
                  <p className="text-xs text-slate-500 mt-1">
                    Rendered securely as plain text. No HTML or script execution permitted.
                  </p>
                </div>

                {/* Pinned Checkbox */}
                <div className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-950/50 border border-slate-800">
                  <input
                    type="checkbox"
                    id="is-pinned"
                    checked={isPinned}
                    onChange={(e) => setIsPinned(e.target.checked)}
                    className="w-4 h-4 rounded-sm border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500/50 cursor-pointer"
                  />
                  <label htmlFor="is-pinned" className="text-sm font-medium text-slate-200 cursor-pointer flex items-center gap-2">
                    <Pin className="w-4 h-4 text-amber-400" />
                    Pin this announcement to top of feed
                  </label>
                </div>

                {/* Pre-submit actions */}
                <div className="pt-2 flex items-center justify-end gap-3 border-t border-slate-800">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => navigate('/manage/announcements')}
                    className="border-slate-700 text-slate-300 hover:bg-slate-800"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={isSubmitting || !title.trim() || !body.trim()}
                    className="bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-2 shadow-lg shadow-indigo-950/40"
                  >
                    <Send className="w-4 h-4" />
                    Review & Publish
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Live Feed Preview */}
        <div className="lg:col-span-5 sticky top-24 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5 text-indigo-400" />
              Live Feed Preview
            </h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
              Interactive
            </span>
          </div>

          <div className="p-2 rounded-2xl bg-slate-900/40 border border-slate-800/80">
            <AnnouncementCard announcement={previewAnnouncement} defaultExpanded />
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 space-y-2">
            <div className="font-semibold text-slate-200 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Publication Guarantees
            </div>
            <ul className="list-disc list-inside space-y-1 text-slate-400">
              <li>Instant inclusion in the Public Announcements feed.</li>
              <li>Emails queued for opted-in students matching the audience filter.</li>
              <li>Immutable log created: cannot be deleted, revisions tracked publicly.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      <Modal
        isOpen={showConfirmModal}
        onClose={() => !isSubmitting && setShowConfirmModal(false)}
        title="Confirm Publication"
        maxWidth="md"
      >
        <div className="space-y-4">
          <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold">Permanent Record:</span> Announcements cannot be deleted once published.
              If corrections are required later, you will need to append an immutable revision note.
            </div>
          </div>

          <div className="space-y-2 text-sm border-t border-b border-slate-100 py-3 text-slate-700">
            <div>
              <span className="text-xs text-slate-400 block">Title</span>
              <span className="font-semibold text-slate-900">{title}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs pt-1">
              <div>
                <span className="text-slate-400 block">Category</span>
                <span className="font-medium text-slate-800 uppercase">{category}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Target Audience</span>
                <span className="font-medium text-slate-800">{AUDIENCE_DETAILS[audience].label}</span>
              </div>
            </div>
            {isPinned && (
              <div className="text-xs font-semibold text-indigo-600 flex items-center gap-1 pt-1">
                <Pin className="w-3 h-3" />
                Will be pinned to the top of the feed
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={isSubmitting}
              onClick={() => setShowConfirmModal(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              disabled={isSubmitting}
              onClick={handleConfirmPublish}
              className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-2"
            >
              {isSubmitting ? 'Publishing...' : 'Confirm & Publish'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
