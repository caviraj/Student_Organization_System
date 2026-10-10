import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { HeartHandshake, Plus, Search, Filter, Sparkles, TrendingUp, Target, AlertCircle } from 'lucide-react';
import { fundraisersApi } from '../../../api/fundraisers';
import { Button } from '../../../components/ui/Button';
import { FundraiserCard } from '../components/FundraiserCard';
import { CreateFundraiserModal } from '../components/CreateFundraiserModal';
import { formatINR } from '../../../lib/formatINR';
import type { Fundraiser } from '../types';

export function FundraiserList() {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['fundraisers'],
    queryFn: () => fundraisersApi.getFundraisers(1, 50),
  });

  const fundraisers: Fundraiser[] = useMemo(() => {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    const res = data as unknown as { items?: Fundraiser[] };
    if (res && Array.isArray(res.items)) {
      return res.items;
    }
    return [];
  }, [data]);

  // Summary Metrics
  const stats = useMemo(() => {
    const total = fundraisers.length;
    const active = fundraisers.filter((f) => f.status === 'active').length;
    const totalRaisedPaise = fundraisers.reduce((sum, f) => sum + (f.progress?.raised ?? 0), 0);
    const totalGoalPaise = fundraisers.reduce(
      (sum, f) => sum + (f.progress?.goal ?? f.goal_amount ?? 0),
      0
    );
    return {
      total,
      active,
      totalRaisedPaise,
      totalGoalPaise,
    };
  }, [fundraisers]);

  // Filtering
  const filteredFundraisers = useMemo(() => {
    return fundraisers.filter((f) => {
      const matchesSearch =
        f.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (f.description && f.description.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchesStatus = statusFilter === 'all' || f.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [fundraisers, searchTerm, statusFilter]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200 mb-2">
            <HeartHandshake className="w-3.5 h-3.5" />
            <span>Fundraising & Task Operations</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Fundraisers & Campaigns
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Track club fundraising targets, log money raised, and coordinate volunteer task boards.
          </p>
        </div>
        <div>
          <Button
            variant="primary"
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={() => setIsCreateOpen(true)}
            className="shadow-sm shadow-indigo-600/20"
          >
            New Fundraiser
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 my-6">
        <div className="bg-white rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Total Campaigns</span>
            <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900">{stats.total}</div>
          <div className="text-xs text-slate-500 mt-1">All recorded campaigns</div>
        </div>

        <div className="bg-white rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Active Now</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600">{stats.active}</div>
          <div className="text-xs text-slate-500 mt-1">Currently taking funds</div>
        </div>

        <div className="bg-white rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Total Raised</span>
            <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
              <HeartHandshake className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900">{formatINR(stats.totalRaisedPaise)}</div>
          <div className="text-xs text-slate-500 mt-1">Across all fundraisers</div>
        </div>

        <div className="bg-white rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Cumulative Goal</span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <Target className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900">{formatINR(stats.totalGoalPaise)}</div>
          <div className="text-xs text-slate-500 mt-1">Target fund value</div>
        </div>
      </div>

      {/* Controls: Search & Status Filters */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search campaigns..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:text-slate-400"
          />
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          <span className="text-xs text-slate-400 flex items-center gap-1 mr-1">
            <Filter className="w-3.5 h-3.5" />
          </span>
          {[
            { id: 'all', label: 'All' },
            { id: 'active', label: 'Active' },
            { id: 'completed', label: 'Completed' },
            { id: 'paused', label: 'Paused' },
            { id: 'draft', label: 'Draft' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all whitespace-nowrap ${
                statusFilter === tab.id
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" aria-label="Loading campaigns">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm animate-pulse space-y-4"
            >
              <div className="flex justify-between items-center">
                <div className="h-4 bg-slate-200 rounded w-20" />
                <div className="h-4 bg-slate-200 rounded w-16" />
              </div>
              <div className="h-6 bg-slate-200 rounded w-3/4" />
              <div className="h-4 bg-slate-200 rounded w-full" />
              <div className="h-4 bg-slate-200 rounded w-2/3" />
              <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                <div className="w-12 h-12 bg-slate-200 rounded-full" />
                <div className="h-4 bg-slate-200 rounded w-24" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {isError && (
        <div className="p-8 text-center bg-rose-50/50 border border-rose-200 rounded-2xl my-6">
          <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-3">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-base font-bold text-slate-900 mb-1">Failed to load fundraisers</h2>
          <p className="text-sm text-slate-600 mb-4 max-w-md mx-auto">
            {error instanceof Error ? error.message : 'An error occurred while fetching fundraisers.'}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !isError && filteredFundraisers.length === 0 && (
        <div className="text-center py-16 px-4 bg-white rounded-2xl border border-dashed border-slate-300">
          <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
            <HeartHandshake className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 mb-1">
            {searchTerm || statusFilter !== 'all' ? 'No matching fundraisers' : 'No fundraisers yet'}
          </h2>
          <p className="text-sm text-slate-500 max-w-sm mx-auto mb-6">
            {searchTerm || statusFilter !== 'all'
              ? 'Try adjusting your search criteria or filter to see more campaigns.'
              : 'Launch your first fundraising campaign to raise money for club goals and organize tasks.'}
          </p>
          {searchTerm || statusFilter !== 'all' ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearchTerm('');
                setStatusFilter('all');
              }}
            >
              Clear Filters
            </Button>
          ) : (
            <Button
              variant="primary"
              leftIcon={<Plus className="w-4 h-4" />}
              onClick={() => setIsCreateOpen(true)}
            >
              Create Campaign
            </Button>
          )}
        </div>
      )}

      {/* Fundraiser Cards Grid */}
      {!isLoading && !isError && filteredFundraisers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredFundraisers.map((fundraiser: Fundraiser) => (
            <FundraiserCard key={fundraiser.id} fundraiser={fundraiser} />
          ))}
        </div>
      )}

      {/* Create Modal */}
      <CreateFundraiserModal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
    </div>
  );
}
