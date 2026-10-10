import React, { useState, useMemo } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Megaphone,
  Plus,
  Pin,
  Clock,
  AlertTriangle,
  Search,
  Edit3,
  Mail,
  Info,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ExternalLink,
} from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card, CardContent } from '../../components/ui/Card';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../context/AuthContext';
import { announcementsApi } from '../../api/announcements';
import { formatDate } from '../../lib/formatDate';
import { formatRelativeTime } from '../../lib/formatRelativeTime';
import { updateAnnouncementRevisionSchema } from '../../features/announcements/schemas';
import type {
  Announcement,
  AnnouncementCategory,
  AnnouncementAudience,
  AnnouncementDelivery,
} from '../../types/announcements';
import type { PaginatedResponse } from '../../types/api';

const CATEGORY_BADGES: Record<AnnouncementCategory, { label: string; className: string }> = {
  meeting: { label: 'Meeting', className: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20' },
  deadline: { label: 'Deadline', className: 'bg-rose-500/10 text-rose-400 border-rose-500/20' },
  change: { label: 'Update', className: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  general: { label: 'General', className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
};

const AUDIENCE_LABELS: Record<AnnouncementAudience, string> = {
  all: 'All Campus',
  members: 'Members Only',
  event: 'Event Attendees',
};

export function ManageAnnouncements() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { success, error: showError } = useToast();

  const isAdmin = user?.role === 'admin';

  // State
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<'all' | AnnouncementCategory>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Revision Modal State
  const [selectedAnnouncementForRevision, setSelectedAnnouncementForRevision] = useState<Announcement | null>(null);
  const [revisionNote, setRevisionNote] = useState('');
  const [revisionError, setRevisionError] = useState('');

  // Delivery Modal State (Admin only)
  const [selectedAnnouncementForDeliveries, setSelectedAnnouncementForDeliveries] = useState<Announcement | null>(null);

  // Queries
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['manageAnnouncements', categoryFilter, currentPage],
    queryFn: () =>
      announcementsApi.getAnnouncements({
        category: categoryFilter === 'all' ? undefined : categoryFilter,
        page: currentPage,
        page_size: 50, // Get enough for client filtering
      }),
  });

  const {
    data: deliveriesData,
    isLoading: isLoadingDeliveries,
    error: deliveriesError,
  } = useQuery<PaginatedResponse<AnnouncementDelivery>>({
    queryKey: ['announcementDeliveries', selectedAnnouncementForDeliveries?.id],
    queryFn: () =>
      selectedAnnouncementForDeliveries
        ? announcementsApi.getDeliveries(selectedAnnouncementForDeliveries.id)
        : Promise.resolve<PaginatedResponse<AnnouncementDelivery>>({
            items: [],
            total: 0,
            page: 1,
            page_size: 50,
          }),
    enabled: !!selectedAnnouncementForDeliveries && isAdmin,
  });

  // Revision Mutation
  const revisionMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      announcementsApi.updateRevision(id, { revision_note: note }),
    onSuccess: () => {
      success('Revision note appended successfully.');
      setSelectedAnnouncementForRevision(null);
      setRevisionNote('');
      setRevisionError('');
      queryClient.invalidateQueries({ queryKey: ['manageAnnouncements'] });
      queryClient.invalidateQueries({ queryKey: ['announcements'] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Failed to append revision note.';
      showError(msg);
    },
  });

  const allItems = useMemo(() => data?.items ?? [], [data?.items]);

  const filteredItems = useMemo(() => {
    return allItems.filter((item) => {
      const matchesSearch =
        searchQuery.trim() === '' ||
        item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.body.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.author_name.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesSearch;
    });
  }, [allItems, searchQuery]);

  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, currentPage, pageSize]);

  const handleOpenRevision = (announcement: Announcement) => {
    setSelectedAnnouncementForRevision(announcement);
    setRevisionNote(announcement.revision_note || '');
    setRevisionError('');
  };

  const handleSubmitRevision = (e: React.FormEvent) => {
    e.preventDefault();
    setRevisionError('');

    const parseResult = updateAnnouncementRevisionSchema.safeParse({ revision_note: revisionNote });
    if (!parseResult.success) {
      setRevisionError(parseResult.error.issues[0]?.message || 'Invalid revision note.');
      return;
    }

    if (selectedAnnouncementForRevision) {
      revisionMutation.mutate({
        id: selectedAnnouncementForRevision.id,
        note: revisionNote.trim(),
      });
    }
  };

  // Columns definition for DataTable
  const columns: Column<Announcement>[] = [
    {
      header: 'Title & Pinned',
      cell: (item) => (
        <div className="max-w-xs sm:max-w-sm">
          <div className="flex items-center gap-2">
            {item.is_pinned && (
              <span
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20"
                title="Pinned announcement"
              >
                <Pin className="w-2.5 h-2.5" />
                PIN
              </span>
            )}
            <span className="font-semibold text-slate-900 truncate block text-sm" title={item.title}>
              {item.title}
            </span>
          </div>
          <p className="text-xs text-slate-500 truncate mt-0.5" title={item.body}>
            {item.body}
          </p>
        </div>
      ),
    },
    {
      header: 'Category',
      cell: (item) => {
        const badge = CATEGORY_BADGES[item.category] || CATEGORY_BADGES.general;
        return (
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${badge.className}`}>
            {badge.label}
          </span>
        );
      },
    },
    {
      header: 'Audience',
      cell: (item) => (
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 bg-slate-100 px-2.5 py-1 rounded-md">
          {AUDIENCE_LABELS[item.audience] || item.audience}
        </span>
      ),
    },
    {
      header: 'Published',
      cell: (item) => (
        <div className="text-xs text-slate-600">
          <div>{formatDate(item.published_at)}</div>
          <div className="text-slate-400 text-[10px]">{formatRelativeTime(item.published_at)}</div>
        </div>
      ),
    },
    {
      header: 'Author',
      accessorKey: 'author_name',
      className: 'text-xs text-slate-700',
    },
    {
      header: 'Revision',
      cell: (item) =>
        item.revision_note ? (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200 cursor-help"
            title={`Revision: ${item.revision_note}`}
          >
            <Edit3 className="w-3 h-3" />
            Edited
          </span>
        ) : (
          <span className="text-xs text-slate-400 font-light">Original</span>
        ),
    },
    {
      header: 'Deliveries',
      cell: (item) => {
        if (!isAdmin) {
          return (
            <span
              className="text-xs text-slate-400 cursor-help flex items-center gap-1"
              title="Delivery logs and counts are visible to administrators only."
            >
              <span>—</span>
              <HelpCircle className="w-3 h-3 text-slate-300" />
            </span>
          );
        }

        return (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSelectedAnnouncementForDeliveries(item)}
            className="text-xs h-7 px-2.5 flex items-center gap-1.5 text-indigo-600 border-indigo-200 hover:bg-indigo-50"
          >
            <Mail className="w-3 h-3" />
            View
          </Button>
        );
      },
    },
    {
      header: 'Actions',
      cell: (item) => (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleOpenRevision(item)}
            className="text-xs h-7 px-2.5 flex items-center gap-1 text-slate-700 hover:text-slate-900"
            title="Append an immutable revision note"
          >
            <Edit3 className="w-3 h-3" />
            Revise
          </Button>
          <Link
            to="/announcements"
            className="text-xs text-slate-400 hover:text-indigo-600 p-1 rounded-md transition-colors"
            title="View in public feed"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </Link>
        </div>
      ),
    },
  ];

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
        <div className="flex justify-between items-center">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-36 rounded-xl" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-24 rounded-2xl" />
        </div>
        <Skeleton className="h-96 rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-md mx-auto px-4 py-16">
        <ErrorState
          title="Could not load announcements"
          message="Failed to retrieve organizer announcements history. Please check your connection and retry."
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-2">
            <Megaphone className="w-3.5 h-3.5" />
            Announcement Operations
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">Manage Announcements</h1>
          <p className="text-sm text-slate-400 mt-1">
            Review immutable announcement logs, append revision notes, and monitor notification delivery.
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() => navigate('/manage/announcements/new')}
          className="self-start sm:self-auto flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-950/40"
        >
          <Plus className="w-4 h-4" />
          Draft Announcement
        </Button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-8">
        <Card className="border-slate-800 bg-slate-900/80 text-white">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Total Announcements</p>
              <p className="text-2xl font-black text-white mt-1">{allItems.length}</p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Megaphone className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/80 text-white">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Pinned Posts</p>
              <p className="text-2xl font-black text-amber-400 mt-1">
                {allItems.filter((i) => i.is_pinned).length}
              </p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Pin className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/80 text-white">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Revisions Appended</p>
              <p className="text-2xl font-black text-emerald-400 mt-1">
                {allItems.filter((i) => !!i.revision_note).length}
              </p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Edit3 className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search announcements by title, content, or author..."
            className="w-full pl-10 pr-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/50"
          />
        </div>

        {/* Category Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {(['all', 'meeting', 'deadline', 'change', 'general'] as const).map((cat) => (
            <button
              key={cat}
              onClick={() => {
                setCategoryFilter(cat);
                setCurrentPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                categoryFilter === cat
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {cat === 'all' ? 'All' : cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Main Table */}
      {filteredItems.length === 0 ? (
        <Card className="border-slate-800 bg-slate-900/60 p-8 text-center">
          <EmptyState
            title="No announcements found"
            description={
              searchQuery
                ? `No announcements match the query "${searchQuery}".`
                : 'No announcements published under this category yet.'
            }
            actionLabel="Draft Announcement"
            onAction={() => navigate('/manage/announcements/new')}
          />
        </Card>
      ) : (
        <DataTable
          columns={columns}
          data={paginatedItems}
          keyExtractor={(item) => item.id}
          page={currentPage}
          pageSize={pageSize}
          total={filteredItems.length}
          onPageChange={(page) => setCurrentPage(page)}
          className="border-slate-800 shadow-xl"
        />
      )}

      {/* Revision Modal */}
      <Modal
        isOpen={!!selectedAnnouncementForRevision}
        onClose={() => {
          if (!revisionMutation.isPending) {
            setSelectedAnnouncementForRevision(null);
            setRevisionNote('');
            setRevisionError('');
          }
        }}
        title="Append Revision Note"
        maxWidth="md"
      >
        {selectedAnnouncementForRevision && (
          <form onSubmit={handleSubmitRevision} className="space-y-4">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-1">
              <span className="font-semibold text-slate-800 block truncate">
                Target: {selectedAnnouncementForRevision.title}
              </span>
              <p>
                In accordance with club governance, past announcements cannot be modified or deleted.
                Appended revision notes will appear on the public card with an &ldquo;Edited&rdquo; badge.
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="revision-note-input" className="text-xs font-semibold text-slate-700">
                  Revision Note <span className="text-rose-500">*</span>
                </label>
                <span className={`text-[10px] ${revisionNote.length > 255 ? 'text-rose-500 font-bold' : 'text-slate-400'}`}>
                  {revisionNote.length}/255
                </span>
              </div>
              <textarea
                id="revision-note-input"
                rows={3}
                value={revisionNote}
                onChange={(e) => setRevisionNote(e.target.value)}
                placeholder="e.g., Note: Start time shifted from 5:00 PM to 5:30 PM due to hall setup."
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 text-slate-900"
                required
              />
              {revisionError && (
                <p className="text-xs text-rose-600 mt-1 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  {revisionError}
                </p>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                disabled={revisionMutation.isPending}
                onClick={() => {
                  setSelectedAnnouncementForRevision(null);
                  setRevisionNote('');
                  setRevisionError('');
                }}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={revisionMutation.isPending || revisionNote.trim().length < 3}
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
              >
                {revisionMutation.isPending ? 'Saving...' : 'Save Revision Note'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      {/* Admin Deliveries Modal */}
      {isAdmin && (
        <Modal
          isOpen={!!selectedAnnouncementForDeliveries}
          onClose={() => setSelectedAnnouncementForDeliveries(null)}
          title="Notification Delivery Logs"
          maxWidth="lg"
        >
          {selectedAnnouncementForDeliveries && (
            <div className="space-y-4">
              {/* Simulated Notice */}
              <div className="p-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-900 text-xs flex items-center gap-2">
                <Info className="w-4 h-4 text-indigo-600 shrink-0" />
                <span>Deliveries are simulated in mock mode. Real background dispatch occurs via SMTP in production.</span>
              </div>

              <div className="border-b border-slate-100 pb-2">
                <h4 className="text-sm font-bold text-slate-900">
                  {selectedAnnouncementForDeliveries.title}
                </h4>
                <p className="text-xs text-slate-500">
                  Target Audience: {AUDIENCE_LABELS[selectedAnnouncementForDeliveries.audience]}
                </p>
              </div>

              {isLoadingDeliveries ? (
                <div className="space-y-2 py-4">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : deliveriesError ? (
                <p className="text-xs text-rose-600 py-4">
                  Failed to load delivery logs for this announcement.
                </p>
              ) : (deliveriesData?.items?.length ?? 0) === 0 ? (
                <p className="text-xs text-slate-500 py-6 text-center">
                  No delivery attempts logged for this announcement yet.
                </p>
              ) : (
                <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
                  {deliveriesData?.items.map((deliv: AnnouncementDelivery) => (
                    <div key={deliv.id} className="py-2.5 flex items-center justify-between text-xs">
                      <div>
                        <div className="font-semibold text-slate-800">{deliv.user_name}</div>
                        <div className="text-slate-400 text-[11px]">{deliv.user_email}</div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="uppercase text-[10px] font-mono px-1.5 py-0.5 rounded-sm bg-slate-100 text-slate-600">
                          {deliv.channel}
                        </span>
                        <span
                          className={`inline-flex items-center gap-1 font-semibold ${
                            deliv.status === 'sent'
                              ? 'text-emerald-600'
                              : deliv.status === 'queued'
                              ? 'text-amber-600'
                              : 'text-rose-600'
                          }`}
                        >
                          {deliv.status === 'sent' ? (
                            <CheckCircle2 className="w-3 h-3" />
                          ) : deliv.status === 'failed' ? (
                            <XCircle className="w-3 h-3" />
                          ) : (
                            <Clock className="w-3 h-3" />
                          )}
                          {deliv.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex justify-end pt-2 border-t border-slate-100">
                <Button variant="outline" size="sm" onClick={() => setSelectedAnnouncementForDeliveries(null)}>
                  Close
                </Button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
