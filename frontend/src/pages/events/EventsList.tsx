import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { eventsApi } from '../../api/events';
import { formatDateTime } from '../../lib/formatDate';
import { formatINR } from '../../lib/formatINR';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import type { EventItem } from '../../types/events';
import {
  Calendar,
  MapPin,
  Search,
  Sparkles,
  ArrowRight,
  Clock,
} from 'lucide-react';

export function EventsList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'free' | 'selling_fast'>('all');

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['events', 'published'],
    queryFn: () => eventsApi.getEvents({ status: 'published' }),
  });

  const events = useMemo(() => data?.items ?? [], [data?.items]);

  const filteredEvents = useMemo(() => {
    return events.filter((evt) => {
      const matchesSearch =
        evt.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        evt.venue.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (evt.description && evt.description.toLowerCase().includes(searchQuery.toLowerCase()));

      if (!matchesSearch) return false;

      if (filterType === 'free') {
        return evt.min_price === 0;
      }
      if (filterType === 'selling_fast') {
        const totalSeatsLeft = evt.ticket_types?.reduce((acc, t) => acc + (t.seats_left ?? 0), 0);
        return totalSeatsLeft !== undefined && totalSeatsLeft > 0 && totalSeatsLeft <= 10;
      }

      return true;
    });
  }, [events, searchQuery, filterType]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
      {/* Hero Header */}
      <div className="relative mb-8 sm:mb-12 overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 p-6 sm:p-10 text-white shadow-xl shadow-indigo-950/20">
        <div className="absolute top-0 right-0 -mt-8 -mr-8 w-64 h-64 rounded-full bg-indigo-500/10 blur-3xl pointer-events-none" />
        <div className="relative z-10 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 text-xs font-semibold mb-4 border border-indigo-500/30">
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            <span>Campus Happenings & Workshops</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-white mb-3">
            Explore Events & Reserve Tickets
          </h1>
          <p className="text-sm sm:text-base text-slate-300 leading-relaxed">
            Connect with peers, learn cutting-edge tech, and join club socials. Members enjoy exclusive discounts and priority access!
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 mb-8">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by event title, venue, or topic..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all shadow-sm"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          <button
            onClick={() => setFilterType('all')}
            className={`px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
              filterType === 'all'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            All Events
          </button>
          <button
            onClick={() => setFilterType('free')}
            className={`px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
              filterType === 'free'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Free Entry
          </button>
          <button
            onClick={() => setFilterType('selling_fast')}
            className={`px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
              filterType === 'selling_fast'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Selling Fast 🔥
          </button>
        </div>
      </div>

      {/* Content Rendering */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="overflow-hidden p-0">
              <Skeleton className="h-48 w-full rounded-none" />
              <div className="p-5 space-y-3">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <div className="pt-4 border-t border-slate-100 flex justify-between items-center">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-9 w-28" />
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          title="Could not load events"
          message={error instanceof Error ? error.message : 'Please check your connection and try again.'}
          onRetry={() => refetch()}
        />
      ) : filteredEvents.length === 0 ? (
        <EmptyState
          icon={<Calendar className="w-7 h-7 text-indigo-600" />}
          title={searchQuery ? 'No matching events found' : 'No upcoming events'}
          description={
            searchQuery
              ? `No events matched your search "${searchQuery}". Try a different keyword.`
              : 'There are no published events scheduled right now. Check back soon or join our community announcements!'
          }
          actionLabel={searchQuery ? 'Clear Search' : undefined}
          onAction={searchQuery ? () => setSearchQuery('') : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredEvents.map((evt) => (
            <EventCard key={evt.id} event={evt} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventCard({ event }: { event: EventItem }) {
  const totalSeatsLeft = event.ticket_types?.reduce((acc, t) => acc + (t.seats_left ?? 0), 0);
  const isSoldOut = totalSeatsLeft !== undefined && totalSeatsLeft <= 0;
  const isLowStock = totalSeatsLeft !== undefined && totalSeatsLeft > 0 && totalSeatsLeft <= 5;

  return (
    <Card className="flex flex-col h-full overflow-hidden p-0 group hover:shadow-lg hover:border-indigo-200 transition-all duration-300">
      {/* Banner / Header Image */}
      <div className="relative h-48 w-full bg-slate-900 overflow-hidden">
        {event.banner_url ? (
          <img
            src={event.banner_url}
            alt={event.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            onError={(e) => {
              // Fallback to placeholder if banner fails to load
              e.currentTarget.style.display = 'none';
            }}
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-tr from-slate-900 via-indigo-950 to-indigo-900 flex items-center justify-center p-6 text-center">
            <div className="space-y-2">
              <Calendar className="w-10 h-10 text-indigo-400 mx-auto opacity-70" />
              <p className="text-xs font-semibold text-indigo-200 uppercase tracking-wider">
                SSA Club Event
              </p>
            </div>
          </div>
        )}

        {/* Badges Overlay */}
        <div className="absolute top-3 right-3 flex items-center gap-1.5">
          {isSoldOut ? (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-rose-600 text-white shadow-md">
              Sold Out
            </span>
          ) : isLowStock ? (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500 text-white shadow-md animate-pulse">
              Only {totalSeatsLeft} left!
            </span>
          ) : null}
        </div>
      </div>

      {/* Card Content */}
      <div className="p-5 flex-1 flex flex-col justify-between space-y-4">
        <div className="space-y-2.5">
          {/* Date & Time */}
          <div className="flex items-center gap-1.5 text-xs font-medium text-indigo-600">
            <Clock className="w-3.5 h-3.5" />
            <span>{formatDateTime(event.starts_at)}</span>
          </div>

          {/* Title */}
          <h2 className="text-lg font-bold text-slate-900 line-clamp-1 group-hover:text-indigo-600 transition-colors">
            {event.title}
          </h2>

          {/* Venue */}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <MapPin className="w-3.5 h-3.5 shrink-0 text-slate-400" />
            <span className="truncate">{event.venue}</span>
          </div>

          {/* Description snippet */}
          <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
            {event.description || 'Join us for this exciting student event!'}
          </p>
        </div>

        {/* Pricing & CTA Footer */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-between gap-2">
          <div>
            <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Price</p>
            <p className="text-base font-extrabold text-slate-900">
              {event.min_price !== undefined
                ? event.min_price === 0
                  ? 'Free'
                  : `From ${formatINR(event.min_price)}`
                : 'Free'}
            </p>
          </div>

          <Link to={`/events/${event.id}`}>
            <Button
              variant={isSoldOut ? 'outline' : 'primary'}
              size="sm"
              rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
              className="text-xs font-semibold"
            >
              {isSoldOut ? 'View Details' : 'Get Tickets'}
            </Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
