import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Megaphone, Lock, ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react';
import { announcementsApi } from '../../api/announcements';
import { AnnouncementCard } from '../../features/announcements/components/AnnouncementCard';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useAuth } from '../../context/AuthContext';
import type { AnnouncementCategory } from '../../types/announcements';

const CATEGORIES: { id: AnnouncementCategory | 'all'; label: string }[] = [
  { id: 'all', label: 'All Notices' },
  { id: 'meeting', label: 'Meetings' },
  { id: 'deadline', label: 'Deadlines' },
  { id: 'change', label: 'Updates & Changes' },
  { id: 'general', label: 'General' },
];

export function AnnouncementsFeed() {
  const { user } = useAuth();
  const [activeCategory, setActiveCategory] = useState<AnnouncementCategory | 'all'>('all');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['announcements', activeCategory, page],
    queryFn: () =>
      announcementsApi.getAnnouncements({
        category: activeCategory === 'all' ? undefined : activeCategory,
        page,
        page_size: pageSize,
      }),
  });

  const announcements = data?.items ?? [];
  const totalItems = data?.total ?? 0;
  const totalPages = Math.ceil(totalItems / pageSize);

  const isGuestOrUnauth = !user || user.role === 'guest';

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12">
      {/* Header Banner */}
      <div className="mb-8">
        <div className="flex items-center gap-2.5 text-indigo-600 font-semibold text-xs tracking-wider uppercase mb-1">
          <Megaphone className="w-4 h-4" />
          <span>Bulletin & Dispatch</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
          Club Announcements
        </h1>
        <p className="mt-2 text-base text-slate-600 max-w-2xl">
          Stay informed with official SSA notices, quarterly meeting schedules, application deadlines, and critical venue updates.
        </p>
      </div>

      {/* Guest Nudge Card */}
      {isGuestOrUnauth && (
        <div
          className="mb-8 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
          data-testid="guest-nudge-banner"
        >
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-indigo-100 text-indigo-700 shrink-0">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Viewing public club announcements
              </h2>
              <p className="text-xs text-slate-600 mt-0.5">
                Sign in with an active club membership to access exclusive notices, grant applications, and registered event bulletins.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-xs"
            >
              <span>Sign In</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link
              to="/memberships"
              className="inline-flex items-center justify-center px-3.5 py-2 rounded-lg text-xs font-semibold bg-white text-indigo-700 border border-indigo-200 hover:bg-indigo-50 transition-colors"
            >
              Join SSA
            </Link>
          </div>
        </div>
      )}

      {/* Category Filter Chips */}
      <div
        className="flex items-center gap-2 overflow-x-auto pb-3 mb-6 scrollbar-none"
        role="tablist"
        aria-label="Filter announcements by category"
      >
        {CATEGORIES.map((cat) => {
          const isActive = activeCategory === cat.id;
          return (
            <button
              key={cat.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => {
                setActiveCategory(cat.id);
                setPage(1);
              }}
              data-testid={`filter-${cat.id}`}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all shrink-0 cursor-pointer ${
                isActive
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              {cat.label}
            </button>
          );
        })}
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="space-y-4" data-testid="announcements-skeleton">
          <Skeleton className="h-36 w-full rounded-xl" />
          <Skeleton className="h-36 w-full rounded-xl" />
          <Skeleton className="h-36 w-full rounded-xl" />
        </div>
      )}

      {/* Error State */}
      {isError && (
        <ErrorState
          title="Failed to load announcements"
          message={error?.message || 'We could not fetch the bulletin feed right now.'}
          onRetry={refetch}
        />
      )}

      {/* Empty State */}
      {!isLoading && !isError && announcements.length === 0 && (
        <EmptyState
          title="No announcements found"
          description={
            activeCategory === 'all'
              ? 'No announcements have been published yet. Please check back later!'
              : `There are currently no announcements categorized under "${CATEGORIES.find((c) => c.id === activeCategory)?.label}".`
          }
          actionLabel={activeCategory !== 'all' ? 'Clear filter & show all' : undefined}
          onAction={
            activeCategory !== 'all'
              ? () => {
                  setActiveCategory('all');
                  setPage(1);
                }
              : undefined
          }
        />
      )}

      {/* Feed List */}
      {!isLoading && !isError && announcements.length > 0 && (
        <div className="space-y-4" data-testid="announcements-list">
          {announcements.map((announcement) => (
            <AnnouncementCard key={announcement.id} announcement={announcement} />
          ))}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="mt-8 pt-4 border-t border-slate-100 flex items-center justify-between">
          <span className="text-xs text-slate-500">
            Page {page} of {totalPages} ({totalItems} notices)
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
