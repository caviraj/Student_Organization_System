import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { eventsApi } from '../../api/events';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { formatINR } from '../../lib/formatINR';
import { formatDate } from '../../lib/formatDate';
import type { AttendeeItem } from '../../types/events';
import {
  ArrowLeft,
  Users,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
  IndianRupee,
  Download,
  Search,
  Calendar,
  MapPin,
  RefreshCw,
  AlertTriangle,
  QrCode,
} from 'lucide-react';

export function EventReport() {
  const { id } = useParams<{ id: string }>();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'valid' | 'used'>('all');

  // 1. Fetch Event Detail
  const {
    data: event,
    isLoading: eventLoading,
    error: eventError,
    refetch: refetchEvent,
  } = useQuery({
    queryKey: ['event', id],
    queryFn: () => eventsApi.getEvent(id!),
    enabled: !!id,
  });

  // 2. Fetch Event KPI Report
  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
    refetch: refetchReport,
  } = useQuery({
    queryKey: ['event-report', id],
    queryFn: () => eventsApi.getEventReport(id!),
    enabled: !!id,
    refetchInterval: 10000, // Live poll every 10s during event check-ins
  });

  // 3. Fetch Event Attendee Roster
  const {
    data: attendeesData,
    isLoading: attendeesLoading,
    refetch: refetchAttendees,
  } = useQuery({
    queryKey: ['event-attendees', id, statusFilter, searchTerm],
    queryFn: () =>
      eventsApi.getAttendees(id!, {
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: searchTerm.trim() || undefined,
      }),
    enabled: !!id,
    refetchInterval: 10000,
  });

  const attendees = attendeesData?.items || [];

  // CSV Exporter
  const handleExportCSV = () => {
    if (!attendees || attendees.length === 0) return;

    const headers = [
      'Ticket Code',
      'Attendee Name',
      'Email',
      'Tier',
      'Price Paid (INR)',
      'Member Pass',
      'Status',
      'Checked In At',
    ];

    const rows = attendees.map((a: AttendeeItem) => [
      a.ticket_code,
      `"${a.user_name.replace(/"/g, '""')}"`,
      `"${a.user_email.replace(/"/g, '""')}"`,
      `"${a.ticket_type_name.replace(/"/g, '""')}"`,
      (a.price_paid / 100).toFixed(2),
      a.is_member_price ? 'Yes' : 'No',
      a.status.toUpperCase(),
      a.checked_in_at ? formatDate(a.checked_in_at) : 'Not Checked In',
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `attendees_${event?.title ? event.title.replace(/[^a-zA-Z0-9]/g, '_') : id}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleRefreshAll = () => {
    refetchEvent();
    refetchReport();
    refetchAttendees();
  };

  if (eventLoading || reportLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-pulse">
        <div className="h-6 w-32 bg-slate-200 rounded mb-4" />
        <div className="h-10 w-64 bg-slate-200 rounded mb-8" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-28 bg-slate-200 rounded-2xl" />
          ))}
        </div>
        <div className="h-44 bg-slate-200 rounded-2xl mb-8" />
        <div className="h-96 bg-slate-200 rounded-2xl" />
      </div>
    );
  }

  if (eventError || reportError || !event || !report) {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center">
        <div className="w-14 h-14 rounded-2xl bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-7 h-7" />
        </div>
        <h2 className="text-xl font-bold text-slate-900 mb-2">Report Not Available</h2>
        <p className="text-sm text-slate-600 mb-6">
          Unable to generate event report. You might not have organizer permissions or the event does not exist.
        </p>
        <div className="flex gap-3 justify-center">
          <Link to="/manage/events">
            <Button variant="outline">Back to Manage</Button>
          </Link>
          <Button variant="primary" onClick={handleRefreshAll} leftIcon={<RefreshCw className="w-4 h-4" />}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Navigation & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <Link
            to="/manage/events"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 mb-2 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Managed Events
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
              {event.title}
            </h1>
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                event.status === 'published'
                  ? 'bg-emerald-100 text-emerald-800'
                  : event.status === 'draft'
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-slate-100 text-slate-700'
              }`}
            >
              {event.status}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 mt-2">
            <span className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              {formatDate(event.starts_at)}
            </span>
            <span className="flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-slate-400" />
              {event.venue}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefreshAll}
            leftIcon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          <Link to="/staff/scan">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<QrCode className="w-4 h-4 text-emerald-600" />}
            >
              Door Scanner
            </Button>
          </Link>
          <Button
            variant="primary"
            size="sm"
            onClick={handleExportCSV}
            disabled={attendees.length === 0}
            leftIcon={<Download className="w-4 h-4" />}
          >
            Download Roster CSV
          </Button>
        </div>
      </div>

      {/* 5 KPI Summary Cards (DESIGN.md / TASKS.md spec) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4 mb-8">
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Sold</span>
            <Users className="w-4 h-4 text-indigo-600" />
          </div>
          <p className="text-2xl font-black text-slate-900">{report.sold}</p>
          <p className="text-[11px] text-slate-500 mt-1">Confirmed attendees</p>
        </div>

        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Seats Left</span>
            <Clock className="w-4 h-4 text-blue-600" />
          </div>
          <p className="text-2xl font-black text-slate-900">{report.seats_left}</p>
          <p className="text-[11px] text-slate-500 mt-1">Remaining capacity</p>
        </div>

        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Checked In</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <p className="text-2xl font-black text-emerald-600">{report.checked_in}</p>
          <p className="text-[11px] text-emerald-700/80 mt-1">Scanned at the door</p>
        </div>

        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">No-shows</span>
            <XCircle className="w-4 h-4 text-amber-600" />
          </div>
          <p className="text-2xl font-black text-amber-600">{report.no_shows}</p>
          <p className="text-[11px] text-slate-500 mt-1">Pending arrival</p>
        </div>

        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Attendance</span>
            <TrendingUp className="w-4 h-4 text-violet-600" />
          </div>
          <p className="text-2xl font-black text-violet-600">{report.attendance_rate}%</p>
          <p className="text-[11px] text-slate-500 mt-1">Turnout conversion</p>
        </div>
      </div>

      {/* Financial Revenue Breakdown Card */}
      <Card className="mb-8 border-slate-200/80 overflow-hidden shadow-sm">
        <CardHeader className="bg-slate-50/60 border-b border-slate-100 pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <IndianRupee className="w-4 h-4 text-indigo-600" />
                Revenue & Ticket Sales Breakdown
              </CardTitle>
              <CardDescription className="text-xs">
                Accurate financial tally split by membership tiers (all values computed from integer paise)
              </CardDescription>
            </div>
            <div className="text-right">
              <span className="text-xs text-slate-500 block">Total Gross Revenue</span>
              <span className="text-xl font-black text-slate-900">
                {formatINR(report.revenue.total)}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-indigo-50/60 border border-indigo-100">
              <span className="text-xs font-semibold text-indigo-700 block mb-1">
                SSA Member Revenue
              </span>
              <p className="text-2xl font-black text-indigo-900">
                {formatINR(report.revenue.member)}
              </p>
              <p className="text-xs text-indigo-600 mt-1">
                Discounted student membership sales
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-xs font-semibold text-slate-700 block mb-1">
                Non-Member Revenue
              </span>
              <p className="text-2xl font-black text-slate-900">
                {formatINR(report.revenue.non_member)}
              </p>
              <p className="text-xs text-slate-500 mt-1">Standard public admissions</p>
            </div>

            <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-100">
              <span className="text-xs font-semibold text-emerald-800 block mb-1">
                Combined Total
              </span>
              <p className="text-2xl font-black text-emerald-900">
                {formatINR(report.revenue.total)}
              </p>
              <p className="text-xs text-emerald-700 mt-1">100% verified order settlement</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Live Attendee Roster Table */}
      <Card className="border-slate-200/80 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Users className="w-4 h-4 text-indigo-600" />
                Live Attendee Roster
              </CardTitle>
              <CardDescription className="text-xs">
                Real-time check-in ledger for door security and attendance tracking
              </CardDescription>
            </div>

            {/* Table Filters & Search */}
            <div className="flex flex-wrap items-center gap-2.5">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input
                  type="text"
                  placeholder="Search attendee or code..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 py-1.5 text-xs w-48 sm:w-60 bg-white"
                />
              </div>

              <div className="inline-flex rounded-xl p-0.5 bg-slate-100 border border-slate-200 text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => setStatusFilter('all')}
                  className={`px-3 py-1 rounded-lg transition-colors ${
                    statusFilter === 'all'
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setStatusFilter('used')}
                  className={`px-3 py-1 rounded-lg transition-colors ${
                    statusFilter === 'used'
                      ? 'bg-white text-emerald-700 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Checked In
                </button>
                <button
                  type="button"
                  onClick={() => setStatusFilter('valid')}
                  className={`px-3 py-1 rounded-lg transition-colors ${
                    statusFilter === 'valid'
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Pending
                </button>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {attendeesLoading ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-600" />
              Loading attendee list...
            </div>
          ) : attendees.length === 0 ? (
            <div className="py-12 text-center text-slate-500">
              <Users className="w-10 h-10 mx-auto mb-3 text-slate-300" />
              <p className="text-sm font-semibold text-slate-700 mb-1">No attendees found</p>
              <p className="text-xs text-slate-500">
                {searchTerm || statusFilter !== 'all'
                  ? 'No results match your current search or filter.'
                  : 'No tickets have been claimed for this event yet.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50/70 border-b border-slate-200/70 text-slate-500 text-xs uppercase font-bold tracking-wider">
                  <tr>
                    <th className="px-6 py-3.5">Attendee</th>
                    <th className="px-6 py-3.5">Ticket Code</th>
                    <th className="px-6 py-3.5">Tier / Price</th>
                    <th className="px-6 py-3.5">Door Status</th>
                    <th className="px-6 py-3.5">Scan Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {attendees.map((a: AttendeeItem) => (
                    <tr key={a.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-slate-900">{a.user_name}</div>
                        <div className="text-xs text-slate-500">{a.user_email}</div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="font-mono text-xs font-bold px-2 py-1 bg-slate-100 rounded text-slate-800 border border-slate-200">
                          {a.ticket_code}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-xs text-slate-900 font-semibold">{a.ticket_type_name}</div>
                        <div className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
                          <span>{formatINR(a.price_paid)}</span>
                          {a.is_member_price && (
                            <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 rounded">
                              Member
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        {a.status === 'used' ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                            Checked In
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700">
                            <Clock className="w-3.5 h-3.5 text-slate-400" />
                            Pending
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-xs text-slate-500">
                        {a.checked_in_at ? formatDate(a.checked_in_at) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
