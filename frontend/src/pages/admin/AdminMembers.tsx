import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { membershipsApi } from '../../api/memberships';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { StatusChip, RoleBadge } from '../../components/ui/StatusChip';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { formatDate } from '../../lib/formatDate';
import type { Membership, Role } from '../../types/api';
import { Users, Search, Filter, ShieldCheck } from 'lucide-react';

export function AdminMembers() {
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['adminMembers', currentPage, pageSize, roleFilter, statusFilter, searchQuery],
    queryFn: () =>
      membershipsApi.getMemberships({
        page: currentPage,
        page_size: pageSize,
        role: roleFilter !== 'all' ? (roleFilter as Role) : undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        search: searchQuery ? searchQuery : undefined,
      }),
  });

  const columns = [
    {
      header: 'Member Code',
      accessor: (m: Membership) => (
        <span className="font-mono text-xs font-bold text-emerald-400 bg-emerald-950/40 px-2 py-1 rounded border border-emerald-500/20">
          {m.member_code}
        </span>
      ),
    },
    {
      header: 'Member Name',
      accessor: (m: Membership) => (
        <div>
          <div className="font-semibold text-white">{m.user?.full_name || 'Student'}</div>
          <div className="text-xs text-slate-400">{m.user?.email}</div>
        </div>
      ),
    },
    {
      header: 'Role',
      accessor: (m: Membership) => <RoleBadge role={m.user?.role || 'member'} />,
    },
    {
      header: 'Plan',
      accessor: (m: Membership) => (
        <span className="text-xs text-slate-300 font-medium">{m.plan_name}</span>
      ),
    },
    {
      header: 'Status',
      accessor: (m: Membership) => <StatusChip status={m.status} />,
    },
    {
      header: 'Valid Until',
      accessor: (m: Membership) => (
        <span className="text-xs text-slate-400 font-mono">
          {formatDate(m.valid_until)}
        </span>
      ),
    },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-2">
            <Users className="w-3.5 h-3.5" />
            Admin Operations
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Member Roster
          </h1>
          <p className="text-sm text-slate-400">
            View, filter, and audit all club members and active subscriptions.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Refresh List
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card className="border-slate-800 bg-slate-900/60">
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
            <div className="sm:col-span-6">
              <Input
                placeholder="Search by name, email, or member code..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                leftIcon={<Search className="w-4 h-4 text-slate-400" />}
              />
            </div>

            <div className="sm:col-span-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-slate-500 shrink-0" />
                <select
                  aria-label="Filter by Role"
                  className="w-full h-10 px-3 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                >
                  <option value="all">All Roles</option>
                  <option value="guest">Guest</option>
                  <option value="member">Member</option>
                  <option value="volunteer">Volunteer</option>
                  <option value="organizer">Organizer</option>
                  <option value="treasurer">Treasurer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>

            <div className="sm:col-span-3">
              <select
                aria-label="Filter by Status"
                className="w-full h-10 px-3 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="all">All Statuses</option>
                <option value="active">Active</option>
                <option value="expired">Expired</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Table / State */}
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
        </div>
      ) : error ? (
        <ErrorState
          title="Failed to load member roster"
          message="Could not retrieve members from server."
          onRetry={() => refetch()}
        />
      ) : (
        <Card className="border-slate-800 bg-slate-900/60 overflow-hidden">
          <CardHeader className="py-4 border-b border-slate-800/80 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Registered Members ({data?.total || 0})
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Page {currentPage} of {data ? Math.ceil(data.total / pageSize) || 1 : 1}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <DataTable
              columns={columns}
              data={data?.items || []}
              keyField="id"
              page={currentPage}
              pageSize={pageSize}
              totalItems={data?.total || 0}
              onPageChange={(page) => setCurrentPage(page)}
              emptyMessage="No members match the selected criteria."
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
