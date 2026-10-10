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
        <span className="font-mono text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-1 rounded border border-emerald-200">
          {m.member_code}
        </span>
      ),
    },
    {
      header: 'Member Name',
      accessor: (m: Membership) => (
        <div>
          <div className="font-semibold text-slate-900">{m.user?.full_name || 'Student'}</div>
          <div className="text-xs text-slate-500">{m.user?.email}</div>
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
        <span className="text-xs text-slate-600 font-medium">{m.plan_name}</span>
      ),
    },
    {
      header: 'Status',
      accessor: (m: Membership) => <StatusChip status={m.status} />,
    },
    {
      header: 'Valid Until',
      accessor: (m: Membership) => (
        <span className="text-xs text-slate-500 font-mono">
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
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 mb-2">
            <Users className="w-3.5 h-3.5" />
            Admin Operations
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
            Member Roster
          </h1>
          <p className="text-sm text-slate-500">
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
      <Card className="border-slate-200 bg-white">
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
            <div className="sm:col-span-6">
              <Input
                placeholder="Search by name, email, or member code..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                leftIcon={<Search className="w-4 h-4 text-slate-500" />}
              />
            </div>

            <div className="sm:col-span-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-slate-500 shrink-0" />
                <select
                  aria-label="Filter by Role"
                  className="w-full h-10 px-3 rounded-xl bg-white border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-600"
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
                className="w-full h-10 px-3 rounded-xl bg-white border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-600"
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
        <Card className="border-slate-200 bg-white overflow-hidden">
          <CardHeader className="py-4 border-b border-slate-200 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              Registered Members ({data?.total || 0})
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
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
