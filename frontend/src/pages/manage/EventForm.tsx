import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { eventsApi } from '../../api/events';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { useToast } from '../../components/ui/Toast';
import { formatINR } from '../../lib/formatINR';
import type { EventStatus } from '../../types/events';
import {
  Calendar,
  Plus,
  Trash2,
  ArrowLeft,
  Save,
  CheckCircle2,
  AlertTriangle,
  Ticket,
  Sparkles,
} from 'lucide-react';

interface TierDraft {
  id?: string; // If existing tier
  name: string;
  member_price_inr: number;
  non_member_price_inr: number;
  capacity: number;
  sold_count?: number;
}

export function EventForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  // Load existing event data if editing
  const { data: event, isLoading: isLoadingEvent, error: loadError } = useQuery({
    queryKey: ['event', id],
    queryFn: () => eventsApi.getEvent(id!),
    enabled: isEdit,
  });

  // Form State
  const [title, setTitle] = useState('');
  const [venue, setVenue] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [description, setDescription] = useState('');
  const [bannerUrl, setBannerUrl] = useState('');
  const [status, setStatus] = useState<EventStatus>('draft');

  // Ticket Tiers state
  const [tiers, setTiers] = useState<TierDraft[]>([
    {
      name: 'General Admission',
      member_price_inr: 0,
      non_member_price_inr: 100,
      capacity: 50,
    },
  ]);

  // Validation errors
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Helper to format ISO to datetime-local
  const toLocalInputFormat = (isoString?: string) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '';
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
      date.getHours()
    )}:${pad(date.getMinutes())}`;
  };

  // Populate data when editing
  useEffect(() => {
    if (event) {
      setTitle(event.title || '');
      setVenue(event.venue || '');
      setStartsAt(toLocalInputFormat(event.starts_at));
      setEndsAt(toLocalInputFormat(event.ends_at));
      setDescription(event.description || '');
      setBannerUrl(event.banner_url || '');
      setStatus(event.status || 'draft');

      if (event.ticket_types && event.ticket_types.length > 0) {
        setTiers(
          event.ticket_types.map((t) => ({
            id: t.id,
            name: t.name,
            member_price_inr: Math.round(t.member_price / 100),
            non_member_price_inr: Math.round(t.non_member_price / 100),
            capacity: t.capacity,
            sold_count: t.sold_count,
          }))
        );
      }
    }
  }, [event]);

  // Validation function
  const validateForm = () => {
    const errors: Record<string, string> = {};

    if (!title.trim()) errors.title = 'Title is required';
    if (!venue.trim()) errors.venue = 'Venue is required';
    if (!startsAt) errors.startsAt = 'Start date and time are required';
    if (!endsAt) errors.endsAt = 'End date and time are required';

    if (startsAt && endsAt) {
      const startTime = new Date(startsAt).getTime();
      const endTime = new Date(endsAt).getTime();
      if (endTime <= startTime) {
        errors.endsAt = 'End date and time must be strictly after the start date and time';
      }
    }

    if (!description.trim()) errors.description = 'Description is required';

    if (bannerUrl.trim() && !/^https?:\/\/.+/i.test(bannerUrl.trim())) {
      errors.bannerUrl = 'Must be a valid URL starting with http:// or https://';
    }

    // Ticket tiers validation
    if (tiers.length === 0) {
      errors.tiers = 'At least one ticket tier must be configured';
    } else {
      tiers.forEach((t, idx) => {
        if (!t.name.trim()) {
          errors[`tier_${idx}_name`] = 'Tier name is required';
        }
        if (t.capacity < 1) {
          errors[`tier_${idx}_capacity`] = 'Capacity must be at least 1';
        }
        if (t.member_price_inr < 0) {
          errors[`tier_${idx}_member_price`] = 'Price cannot be negative';
        }
        if (t.non_member_price_inr < 0) {
          errors[`tier_${idx}_non_member_price`] = 'Price cannot be negative';
        }
      });
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Add tier row
  const handleAddTier = () => {
    setTiers((prev) => [
      ...prev,
      {
        name: `Tier ${prev.length + 1}`,
        member_price_inr: 0,
        non_member_price_inr: 150,
        capacity: 30,
      },
    ]);
  };

  // Remove tier row
  const handleRemoveTier = (index: number) => {
    if (tiers.length <= 1) {
      toast.show('An event must have at least one ticket tier', 'warning');
      return;
    }
    setTiers((prev) => prev.filter((_, idx) => idx !== index));
  };

  // Update specific tier field
  const handleTierChange = <K extends keyof TierDraft>(index: number, field: K, value: TierDraft[K]) => {
    setTiers((prev) =>
      prev.map((t, idx) => (idx === index ? { ...t, [field]: value } : t))
    );
  };

  // Submit Handler
  const handleSave = async (targetStatus?: EventStatus) => {
    const finalStatus = targetStatus ?? status;

    if (!validateForm()) {
      toast.show('Please resolve the errors highlighted below', 'error');
      return;
    }

    // If publishing, confirm first
    if (finalStatus === 'published' && status !== 'published' && !targetStatus) {
      setIsPublishModalOpen(true);
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = {
        title: title.trim(),
        venue: venue.trim(),
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        description: description.trim(),
        banner_url: bannerUrl.trim() || null,
        status: finalStatus,
      };

      let targetEventId = id;

      if (isEdit && id) {
        await eventsApi.updateEvent(id, payload);
      } else {
        const created = await eventsApi.createEvent(payload);
        targetEventId = created.id;
      }

      // Process new ticket tiers
      if (targetEventId) {
        for (const tier of tiers) {
          // If it's a new tier without an ID, create it
          if (!tier.id) {
            await eventsApi.createTicketType(targetEventId, {
              name: tier.name.trim(),
              member_price: Math.round(tier.member_price_inr * 100), // Integer paise
              non_member_price: Math.round(tier.non_member_price_inr * 100), // Integer paise
              capacity: Number(tier.capacity),
            });
          }
        }
      }

      queryClient.invalidateQueries({ queryKey: ['manageEvents'] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
      if (targetEventId) {
        queryClient.invalidateQueries({ queryKey: ['event', targetEventId] });
      }

      toast.show(
        isEdit ? 'Event successfully updated!' : 'Event successfully created!',
        'success'
      );
      navigate('/manage/events');
    } catch (err: any) {
      toast.show(err.message || 'Failed to save event. Please try again.', 'error');
    } finally {
      setIsSubmitting(false);
      setIsPublishModalOpen(false);
    }
  };

  if (isEdit && isLoadingEvent) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-10 space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-96 rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    );
  }

  if (isEdit && loadError) {
    return (
      <div className="max-w-md mx-auto px-4 py-16">
        <ErrorState
          title="Failed to load event"
          message="Could not load event information for editing."
          onRetry={() => navigate('/manage/events')}
        />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Top back navigation */}
      <button
        onClick={() => navigate('/manage/events')}
        className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 transition-colors mb-6"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Event Management
      </button>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            {isEdit ? 'Edit Event Details' : 'Create New Event'}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Configure schedule, venue, promotional details, and admission ticket tiers.
          </p>
        </div>

        {/* Quick status indicator */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Current Status:</span>
          <span
            className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
              status === 'published'
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-amber-50 text-amber-700 border border-amber-200'
            }`}
          >
            {status}
          </span>
        </div>
      </div>

      <div className="space-y-8">
        {/* Section 1: Basic Event Information */}
        <Card className="border-slate-200 bg-white">
          <CardHeader>
            <CardTitle className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-emerald-600" />
              1. Event Overview & Schedule
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Provide the primary details where and when the event will take place.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-5">
            <Input
              label="Event Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Annual Tech Symposium & Hackathon 2026"
              error={formErrors.title}
              required
            />

            <Input
              label="Venue / Location"
              value={venue}
              onChange={(e) => setVenue(e.target.value)}
              placeholder="e.g. Main Auditorium, Building B / Hybrid Zoom Link"
              error={formErrors.venue}
              required
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  Starts At (Date & Time) <span className="text-rose-600">*</span>
                </label>
                <input
                  type="datetime-local"
                  value={startsAt}
                  onChange={(e) => setStartsAt(e.target.value)}
                  className={`w-full px-3 py-2 text-sm rounded-xl bg-white border ${
                    formErrors.startsAt ? 'border-rose-500' : 'border-slate-300'
                  } text-slate-900 focus:outline-none focus:border-indigo-600 transition-colors`}
                />
                {formErrors.startsAt && (
                  <p className="mt-1 text-xs text-rose-600">{formErrors.startsAt}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  Ends At (Date & Time) <span className="text-rose-600">*</span>
                </label>
                <input
                  type="datetime-local"
                  value={endsAt}
                  onChange={(e) => setEndsAt(e.target.value)}
                  className={`w-full px-3 py-2 text-sm rounded-xl bg-white border ${
                    formErrors.endsAt ? 'border-rose-500' : 'border-slate-300'
                  } text-slate-900 focus:outline-none focus:border-indigo-600 transition-colors`}
                />
                {formErrors.endsAt && (
                  <p className="mt-1 text-xs text-rose-600">{formErrors.endsAt}</p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                Detailed Description <span className="text-rose-600">*</span>
              </label>
              <textarea
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe agenda, guest speakers, refreshments, and guidelines for attendees..."
                className={`w-full px-3 py-2 text-sm rounded-xl bg-white border ${
                  formErrors.description ? 'border-rose-500' : 'border-slate-300'
                } text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-600 transition-colors`}
              />
              {formErrors.description && (
                <p className="mt-1 text-xs text-rose-600">{formErrors.description}</p>
              )}
            </div>

            {/* Banner URL & Live Preview */}
            <div className="space-y-3">
              <Input
                label="Banner Image URL (Optional)"
                value={bannerUrl}
                onChange={(e) => setBannerUrl(e.target.value)}
                placeholder="https://images.unsplash.com/photo-..."
                error={formErrors.bannerUrl}
                hint="Provide a direct image URL to display on the public event card."
              />

              {bannerUrl.trim() && /^https?:\/\/.+/i.test(bannerUrl.trim()) && (
                <div className="mt-2 rounded-2xl overflow-hidden border border-slate-200 bg-slate-50 max-h-48 relative">
                  <img
                    src={bannerUrl.trim()}
                    alt="Event banner preview"
                    className="w-full h-48 object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-1 rounded bg-white text-[10px] text-slate-600 font-mono">
                    Banner Preview
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Section 2: Ticket Tiers Manager */}
        <Card className="border-slate-200 bg-white">
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Ticket className="w-5 h-5 text-emerald-600" />
                2. Admission Ticket Tiers
              </CardTitle>
              <CardDescription className="text-xs text-slate-500">
                Set up pricing and seat limits. All prices are in ₹ INR. SSA Members can receive special discounted rates.
              </CardDescription>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleAddTier}
              className="text-xs text-emerald-600 border-emerald-200 hover:bg-emerald-50"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              Add Another Tier
            </Button>
          </CardHeader>

          <CardContent className="space-y-4">
            {formErrors.tiers && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                {formErrors.tiers}
              </div>
            )}

            {tiers.map((tier, index) => (
              <div
                key={tier.id || index}
                className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-4 relative group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider font-mono">
                    Tier #{index + 1} {tier.id && '(Saved)'}
                  </span>

                  {!tier.id && tiers.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveTier(index)}
                      className="text-slate-500 hover:text-rose-600 p-1 transition-colors"
                      title="Remove Tier"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <div className="sm:col-span-1">
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1">
                      Tier Name
                    </label>
                    <input
                      type="text"
                      value={tier.name}
                      disabled={Boolean(tier.id)}
                      onChange={(e) => handleTierChange(index, 'name', e.target.value)}
                      placeholder="e.g. VIP / Early Bird"
                      className="w-full px-3 py-1.5 text-xs rounded-xl bg-white border border-slate-300 text-slate-900 focus:outline-none focus:border-indigo-600 disabled:opacity-60"
                    />
                    {formErrors[`tier_${index}_name`] && (
                      <p className="mt-1 text-[10px] text-rose-600">
                        {formErrors[`tier_${index}_name`]}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1">
                      Member Price (₹)
                    </label>
                    <input
                      type="number"
                      min={0}
                      step={1}
                      disabled={Boolean(tier.id)}
                      value={tier.member_price_inr}
                      onChange={(e) =>
                        handleTierChange(index, 'member_price_inr', Number(e.target.value))
                      }
                      className="w-full px-3 py-1.5 text-xs rounded-xl bg-white border border-slate-300 text-slate-900 focus:outline-none focus:border-indigo-600 disabled:opacity-60"
                    />
                    <span className="text-[10px] text-slate-500">
                      {tier.member_price_inr === 0 ? 'Free Entry' : formatINR(tier.member_price_inr * 100)}
                    </span>
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1">
                      Standard Price (₹)
                    </label>
                    <input
                      type="number"
                      min={0}
                      step={1}
                      disabled={Boolean(tier.id)}
                      value={tier.non_member_price_inr}
                      onChange={(e) =>
                        handleTierChange(index, 'non_member_price_inr', Number(e.target.value))
                      }
                      className="w-full px-3 py-1.5 text-xs rounded-xl bg-white border border-slate-300 text-slate-900 focus:outline-none focus:border-indigo-600 disabled:opacity-60"
                    />
                    <span className="text-[10px] text-slate-500">
                      {tier.non_member_price_inr === 0
                        ? 'Free Entry'
                        : formatINR(tier.non_member_price_inr * 100)}
                    </span>
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1">
                      Seat Capacity
                    </label>
                    <input
                      type="number"
                      min={1}
                      step={1}
                      disabled={Boolean(tier.id)}
                      value={tier.capacity}
                      onChange={(e) =>
                        handleTierChange(index, 'capacity', Number(e.target.value))
                      }
                      className="w-full px-3 py-1.5 text-xs rounded-xl bg-white border border-slate-300 text-slate-900 focus:outline-none focus:border-indigo-600 disabled:opacity-60"
                    />
                    {tier.sold_count !== undefined && (
                      <span className="text-[10px] text-emerald-600 font-mono">
                        {tier.sold_count} sold
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Section 3: Publishing Controls & Actions */}
        <Card className="border-slate-200 bg-white">
          <CardHeader>
            <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-emerald-600" />
              3. Event Visibility & Publish Status
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Draft events are only visible to club organizers. Published events appear immediately on the public events directory.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl bg-slate-50 border border-slate-200">
              <div>
                <p className="text-sm font-semibold text-slate-900">Event Publication Status</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {status === 'published'
                    ? 'Published: Visible to all students for ticket purchases.'
                    : 'Draft: Work in progress. Invisible to students.'}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStatus('draft')}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    status === 'draft'
                      ? 'bg-amber-500 text-slate-950 font-bold shadow'
                      : 'bg-slate-100 text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Draft
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (status !== 'published') {
                      setIsPublishModalOpen(true);
                    }
                  }}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    status === 'published'
                      ? 'bg-emerald-500 text-slate-950 font-bold shadow'
                      : 'bg-slate-100 text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Published
                </button>
              </div>
            </div>
          </CardContent>

          <CardFooter className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-200 pt-5">
            <Button
              variant="outline"
              onClick={() => navigate('/manage/events')}
              disabled={isSubmitting}
            >
              Cancel
            </Button>

            <div className="flex items-center gap-3 w-full sm:w-auto">
              <Button
                variant="outline"
                onClick={() => handleSave('draft')}
                disabled={isSubmitting}
                className="w-full sm:w-auto"
              >
                <Save className="w-4 h-4 mr-1.5" />
                Save as Draft
              </Button>

              <Button
                variant="primary"
                onClick={() => handleSave(status === 'published' ? 'published' : undefined)}
                disabled={isSubmitting}
                className="w-full sm:w-auto"
              >
                <CheckCircle2 className="w-4 h-4 mr-1.5" />
                {status === 'published' ? 'Save & Update' : 'Save & Publish Event'}
              </Button>
            </div>
          </CardFooter>
        </Card>
      </div>

      {/* Confirmation Modal when toggling/saving as Published */}
      <Modal
        isOpen={isPublishModalOpen}
        onClose={() => setIsPublishModalOpen(false)}
        title="Publish Event to Campus?"
        description="Verify event configuration before making it live."
      >
        <div className="space-y-4 pt-2">
          <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-700 space-y-1.5">
            <p className="font-semibold flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
              Public Visibility Notice
            </p>
            <p>
              Once published, this event will appear in the main Campus Events directory. Students will be able to immediately register and purchase passes according to the {tiers.length} configured ticket tier(s).
            </p>
          </div>

          <div className="text-xs text-slate-600 space-y-1 bg-slate-50 p-3 rounded-xl border border-slate-200">
            <p><span className="text-slate-500">Title:</span> {title || 'Untitled Event'}</p>
            <p><span className="text-slate-500">Venue:</span> {venue || 'Not specified'}</p>
            <p><span className="text-slate-500">Starts:</span> {startsAt ? new Date(startsAt).toLocaleString() : 'Not set'}</p>
            <p><span className="text-slate-500">Tiers:</span> {tiers.map(t => `${t.name} (${t.capacity} seats)`).join(', ')}</p>
          </div>

          <div className="flex justify-end gap-3 pt-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsPublishModalOpen(false)}
            >
              Keep as Draft
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setStatus('published');
                setIsPublishModalOpen(false);
                handleSave('published');
              }}
            >
              Confirm & Publish Now
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
