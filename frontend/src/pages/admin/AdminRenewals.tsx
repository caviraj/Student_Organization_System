import { useQuery } from '@tanstack/react-query';
import { membershipsApi } from '../../api/memberships';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { formatDate } from '../../lib/formatDate';
import type { RenewalDueItem } from '../../types/api';
import { Clock, AlertTriangle, AlertCircle, CheckCircle, BellRing, RefreshCw } from 'lucide-react';

export function AdminRenewals() {
  const { data: renewals, isLoading, error, refetch } = useQuery({
    queryKey: ['adminRenewalsDue'],
    queryFn: () => membershipsApi.getRenewalsDue(30),
  });

  const items = renewals?.items || (Array.isArray(renewals) ? (renewals as RenewalDueItem[]) : []);
  const expiredCount = items.filter((r) => (r.days_remaining ?? r.days_left ?? 0) <= 0).length;
  const criticalCount = items.filter((r) => {
    const days = r.days_remaining ?? r.days_left ?? 0;
    return days > 0 && days <= 7;
  }).length;
  const upcomingCount = items.filter((r) => (r.days_remaining ?? r.days_left ?? 0) > 7).length;

  const columns = [
    {
      header: 'Member Code',
      accessor: (r: RenewalDueItem) => (
        <span className="font-mono text-xs font-bold text-slate-300 bg-slate-800 px-2 py-0.5 rounded">
          {r.member_code || r.user_id.slice(0, 8)}
        </span>
      ),
    },
    {
      header: 'Member Name',
      accessor: (r: RenewalDueItem) => (
        <div>
          <div className="font-semibold text-white">{r.full_name || r.user_name}</div>
          <div className="text-xs text-slate-400">{r.email || r.user_email}</div>
        </div>
      ),
    },
    {
      header: 'Plan',
      accessor: (r: RenewalDueItem) => (
        <span className="text-xs text-slate-300">{r.plan_name}</span>
      ),
    },
    {
      header: 'Expiration Date',
      accessor: (r: RenewalDueItem) => (
        <span className="font-mono text-xs text-slate-400">{formatDate(r.valid_until || r.end_date)}</span>
      ),
    },
    {
      header: 'Urgency',
      accessor: (r: RenewalDueItem) => {
        const days = r.days_remaining ?? r.days_left ?? 0;
        if (days <= 0) {
          return (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
              <AlertCircle className="w-3 h-3 text-rose-400" />
              Expired
            </span>
          );
        }
        if (days <= 7) {
          return (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              {days}d Left (Critical)
            </span>
          );
        }
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-500/10 text-teal-300 border border-teal-500/20">
            <Clock className="w-3 h-3 text-teal-400" />
            {days}d Left
          </span>
        );
      },
    },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 mb-2">
            <BellRing className="w-3.5 h-3.5" />
            Retention Monitoring
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Renewals Due
          </h1>
          <p className="text-sm text-slate-400">
            Track members expiring within 30 days or recently lapsed to coordinate reminders.
          </p>
        </div>

        <div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-1.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="border-rose-500/20 bg-slate-900/80">
          <CardContent className="pt-6 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-rose-400 font-semibold">
                Already Expired
              </p>
              <h3 className="text-3xl font-black text-white mt-1">{expiredCount}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center">
              <AlertCircle className="w-6 h-6" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-amber-500/20 bg-slate-900/80">
          <CardContent className="pt-6 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-amber-400 font-semibold">
                Critical (≤ 7 Days)
              </p>
              <h3 className="text-3xl font-black text-white mt-1">{criticalCount}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <AlertTriangle className="w-6 h-6" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-teal-500/20 bg-slate-900/80">
          <CardContent className="pt-6 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-teal-400 font-semibold">
                Upcoming (8-30 Days)
              </p>
              <h3 className="text-3xl font-black text-white mt-1">{upcomingCount}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-teal-500/10 text-teal-400 flex items-center justify-center">
              <Clock className="w-6 h-6" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Table / List */}
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
        </div>
      ) : error ? (
        <ErrorState
          title="Could not load renewals data"
          message="Failed to retrieve renewal urgency queue."
          onRetry={() => refetch()}
        />
      ) : (
        <Card className="border-slate-800 bg-slate-900/60 overflow-hidden">
          <CardHeader className="py-4 border-b border-slate-800/80">
            <CardTitle className="text-base font-bold text-white flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              Members Requiring Renewal ({items.length})
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Members expiring within the 30-day window
            </CardDescription>
          </CardHeader>

          <CardContent className="p-0">
            <DataTable
              columns={columns}
              data={items}
              keyField="member_code"
              emptyMessage="No members currently due for renewal! All active memberships are in good standing."
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
