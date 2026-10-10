import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { eventsApi } from '../../api/events';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { formatDate } from '../../lib/formatDate';
import { formatINR } from '../../lib/formatINR';
import type { EventItem, EventStatus } from '../../types/events';
import {
  Calendar,
  Plus,
  MapPin,
  Ticket,
  BarChart3,
  Edit,
  ExternalLink,
  Search,
} from 'lucide-react';

export function ManageEvents() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<'all' | EventStatus>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['manageEvents'],
    queryFn: () => eventsApi.getEvents(),
  });

  const allEvents = useMemo(() => data?.items ?? [], [data?.items]);

  const filteredEvents = useMemo(() => {
    return allEvents.filter((evt) => {
      const matchesStatus = statusFilter === 'all' || evt.status === statusFilter;
      const matchesSearch =
        searchQuery.trim() === '' ||
        evt.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        evt.venue.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStatus && matchesSearch;
    });
  }, [allEvents, statusFilter, searchQuery]);

  // Aggregate metrics
  const totalEvents = allEvents.length;
  const publishedEvents = allEvents.filter((e) => e.status === 'published').length;
  const draftEvents = allEvents.filter((e) => e.status === 'draft').length;

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
        <div className="flex justify-between items-center">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-36 rounded-xl" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
        </div>
        <Skeleton className="h-96 rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-md mx-auto px-4 py-16">
        <ErrorState
          title="Could not load events"
          message="Failed to retrieve organizer events list. Please check your connection and retry."
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-2">
            <Calendar className="w-3.5 h-3.5" />
            Organizer Workspace
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">Event Management</h1>
          <p className="text-sm text-slate-400 mt-1">
            Create, configure ticket tiers, and monitor attendance reports for SSA events.
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() => navigate('/manage/events/new')}
          className="self-start sm:self-auto flex items-center gap-2 shadow-lg shadow-emerald-950/40"
        >
          <Plus className="w-4 h-4" />
          Create New Event
        </Button>
      </div>

      {/* KPI Stats Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader className="pb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Events</span>
            <CardTitle className="text-2xl font-black text-white">{totalEvents}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-slate-400">
            Across draft, published, and closed
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader className="pb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Published & Live</span>
            <CardTitle className="text-2xl font-black text-emerald-400">{publishedEvents}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-slate-400">
            Visible to students for ticket registration
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader className="pb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-400">Drafts Pending</span>
            <CardTitle className="text-2xl font-black text-amber-400">{draftEvents}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-slate-400">
            Configure dates and ticket tiers before launch
          </CardContent>
        </Card>
      </div>

      {/* Controls: Search & Status Tabs */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 mb-6">
        {/* Status Tabs */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-slate-800 md:border-b-0">
          <button
            onClick={() => setStatusFilter('all')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              statusFilter === 'all'
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-400 hover:text-white bg-slate-900/50'
            }`}
          >
            All Events ({totalEvents})
          </button>
          <button
            onClick={() => setStatusFilter('published')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              statusFilter === 'published'
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-400 hover:text-white bg-slate-900/50'
            }`}
          >
            Published ({publishedEvents})
          </button>
          <button
            onClick={() => setStatusFilter('draft')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              statusFilter === 'draft'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                : 'text-slate-400 hover:text-white bg-slate-900/50'
            }`}
          >
            Drafts ({draftEvents})
          </button>
          <button
            onClick={() => setStatusFilter('closed')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              statusFilter === 'closed'
                ? 'bg-slate-700 text-slate-200 border border-slate-600'
                : 'text-slate-400 hover:text-white bg-slate-900/50'
            }`}
          >
            Closed
          </button>
        </div>

        {/* Search */}
        <div className="relative w-full md:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by title or venue..."
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-900/90 border border-slate-800 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
          />
        </div>
      </div>

      {/* Events List / Table */}
      {filteredEvents.length === 0 ? (
        <EmptyState
          icon={<Calendar className="w-12 h-12 text-slate-500" />}
          title="No events found"
          description={
            searchQuery
              ? `No events matching "${searchQuery}". Try adjusting your filters.`
              : 'You have not created any events in this status yet.'
          }
          actionLabel="Create Event"
          onAction={() => navigate('/manage/events/new')}
        />
      ) : (
        <div className="space-y-4">
          {filteredEvents.map((event: EventItem) => {
            const ticketTypes = event.ticket_types || [];
            const totalCapacity = ticketTypes.reduce((acc, t) => acc + (t.capacity || 0), 0);
            const totalSold = ticketTypes.reduce((acc, t) => acc + (t.sold_count || 0), 0);

            return (
              <Card
                key={event.id}
                className="border-slate-800 bg-slate-900/70 hover:border-slate-700 transition-all p-5"
              >
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
                  {/* Event Details */}
                  <div className="space-y-2 min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <StatusChip
                        status={
                          event.status === 'published'
                            ? 'active'
                            : event.status === 'draft'
                            ? 'pending'
                            : 'expired'
                        }
                        label={event.status.toUpperCase()}
                      />
                      <h3 className="text-lg font-bold text-white tracking-tight truncate">
                        {event.title}
                      </h3>
                    </div>

                    <div className="flex flex-wrap items-center gap-y-1 gap-x-4 text-xs text-slate-400">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-500" />
                        <span>{formatDate(event.starts_at)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <MapPin className="w-3.5 h-3.5 text-slate-500" />
                        <span className="truncate">{event.venue}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Ticket className="w-3.5 h-3.5 text-slate-500" />
                        <span>
                          {ticketTypes.length} Tier{ticketTypes.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                    </div>

                    {/* Ticket Tiers Overview Chips */}
                    {ticketTypes.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        {ticketTypes.map((t) => (
                          <span
                            key={t.id}
                            className="text-[11px] px-2 py-0.5 rounded-md bg-slate-950/80 border border-slate-800/80 text-slate-300 font-mono"
                          >
                            {t.name}: {t.member_price === 0 ? 'Free' : formatINR(t.member_price)} /{' '}
                            {t.non_member_price === 0 ? 'Free' : formatINR(t.non_member_price)} (
                            {t.sold_count ?? 0}/{t.capacity})
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Capacity & Attendance Badge */}
                  <div className="flex items-center gap-3 shrink-0 lg:border-l lg:border-slate-800/80 lg:pl-6">
                    <div className="text-right">
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 block">
                        Registrations
                      </span>
                      <span className="text-base font-extrabold text-white">
                        {totalSold}{' '}
                        <span className="text-xs font-normal text-slate-500">
                          / {totalCapacity > 0 ? totalCapacity : '—'}
                        </span>
                      </span>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 pl-3">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/manage/events/${event.id}/report`)}
                        className="text-xs text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
                        title="View Attendance & Financial Report"
                      >
                        <BarChart3 className="w-3.5 h-3.5 mr-1" />
                        Report
                      </Button>

                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/manage/events/${event.id}/edit`)}
                        className="text-xs text-slate-300"
                        title="Edit Event Details and Ticket Tiers"
                      >
                        <Edit className="w-3.5 h-3.5 mr-1" />
                        Edit
                      </Button>

                      {event.status === 'published' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/events/${event.id}`)}
                          className="text-xs text-slate-400 hover:text-white p-2"
                          title="View Public Event Page"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
