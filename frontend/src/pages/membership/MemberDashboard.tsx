import { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { QRCodeSVG } from 'qrcode.react';
import { membershipsApi } from '../../api/memberships';
import { ticketsApi } from '../../api/tickets';
import { authApi } from '../../api/auth';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/ui/Toast';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { StatusChip, RoleBadge } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { formatDate } from '../../lib/formatDate';
import {
  ShieldCheck,
  Calendar,
  Sparkles,
  QrCode,
  ArrowRight,
  AlertCircle,
  Clock,
  Printer,
  UserCheck,
  Ticket,
  Mail,
} from 'lucide-react';

export function MemberDashboard() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const cardRef = useRef<HTMLDivElement>(null);
  const { success: showToastSuccess, error: showToastError } = useToast();

  const [emailOptIn, setEmailOptIn] = useState<boolean>(user?.email_opt_in ?? true);
  const [isUpdatingPreferences, setIsUpdatingPreferences] = useState(false);

  useEffect(() => {
    if (user?.email_opt_in !== undefined) {
      setEmailOptIn(user.email_opt_in);
    }
  }, [user?.email_opt_in]);

  const handleToggleEmailOptIn = async () => {
    const previous = emailOptIn;
    const next = !previous;
    setEmailOptIn(next);
    setIsUpdatingPreferences(true);

    try {
      await authApi.updateEmailPreferences({ email_opt_in: next });
      showToastSuccess(
        next
          ? 'Subscribed to announcement email notifications.'
          : 'Muted announcement email notifications.'
      );
      if (refreshUser) {
        await refreshUser();
      }
    } catch (err: unknown) {
      // Rollback on error
      setEmailOptIn(previous);
      const msg = err instanceof Error ? err.message : 'Failed to update email preferences.';
      showToastError(`${msg} Preference rolled back.`);
    } finally {
      setIsUpdatingPreferences(false);
    }
  };

  const { data: card, isLoading, error, refetch } = useQuery({
    queryKey: ['myMemberCard'],
    queryFn: membershipsApi.getMyCard,
  });

  const { data: myTickets } = useQuery({
    queryKey: ['myTickets'],
    queryFn: ticketsApi.getMyTickets,
  });

  const handlePrint = () => {
    window.print();
  };

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12 space-y-6">
        <Skeleton className="h-10 w-64 mx-auto" />
        <Skeleton className="h-96 w-full max-w-md mx-auto rounded-3xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-md mx-auto px-4 py-16">
        <ErrorState
          title="Could not load membership card"
          message="Unable to retrieve your digital credentials. Please try again."
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  const hasMembership = !!card && card.status !== 'none';
  const isActive = card?.status === 'active';
  const isExpiringSoon = typeof card?.days_remaining === 'number' && card.days_remaining <= 30 && card.days_remaining > 0;
  const isExpired = card?.status === 'expired' || (typeof card?.days_remaining === 'number' && card.days_remaining <= 0);

  if (!hasMembership) {
    return (
      <div className="max-w-xl mx-auto px-4 py-16 space-y-6">
        <EmptyState
          icon={<ShieldCheck className="w-14 h-14 text-slate-500" />}
          title="No Active Membership Found"
          description={`Hello ${user?.full_name || 'Student'}! You are currently registered as a Guest. Join SSA today to get your official verified Digital Member ID Card.`}
          actionLabel="Explore Membership Plans"
          onAction={() => navigate('/join')}
        />

        {/* Email Notification Preferences Card for Non-Members */}
        <Card className="border-slate-800/80 bg-slate-900/60 shadow-xl overflow-hidden">
          <CardHeader className="pb-3 border-b border-slate-800/60 flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                <Mail className="w-4 h-4" />
              </div>
              <div>
                <CardTitle className="text-base text-white">Email Notification Preferences</CardTitle>
                <CardDescription className="text-xs text-slate-400">
                  Manage club broadcasts
                </CardDescription>
              </div>
            </div>
            <span
              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                emailOptIn
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
            >
              {emailOptIn ? 'Subscribed' : 'Muted'}
            </span>
          </CardHeader>
          <CardContent className="pt-4 space-y-3">
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-0.5">
                <label
                  htmlFor="email-notifications-guest-switch"
                  className="text-xs font-semibold text-slate-200 cursor-pointer"
                >
                  Announcement Broadcasts
                </label>
                <p className="text-[11px] text-slate-400">
                  Receive email deliveries for campus updates, deadlines, and schedule changes.
                </p>
              </div>
              <button
                type="button"
                id="email-notifications-guest-switch"
                role="switch"
                aria-checked={emailOptIn}
                disabled={isUpdatingPreferences}
                onClick={handleToggleEmailOptIn}
                data-testid="email-opt-in-toggle"
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-50 ${
                  emailOptIn ? 'bg-emerald-500' : 'bg-slate-700'
                }`}
              >
                <span className="sr-only">Toggle announcement email notifications</span>
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                    emailOptIn ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
            <p className="text-[10px] text-slate-500 italic pt-1">
              Deliveries are sent to <span className="font-mono text-slate-400">{user?.email}</span>.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Top Banner & Header */}
      <div className="text-center max-w-xl mx-auto mb-10">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-3">
          <Sparkles className="w-3.5 h-3.5" />
          Verified Student Credential
        </div>
        <h1 className="text-3xl font-black text-white tracking-tight">
          Digital Member ID Card
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Present this official QR code at SSA events and workshops for instant verification.
        </p>

        {isExpiringSoon && (
          <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center justify-between text-xs text-amber-300">
            <span className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-400" />
              Membership renewal due in <strong>{card.days_remaining} days</strong>.
            </span>
            <Button size="sm" variant="outline" className="text-amber-300 border-amber-400/40 hover:bg-amber-400/10" onClick={() => navigate('/join')}>
              Renew Now
            </Button>
          </div>
        )}

        {isExpired && (
          <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl flex items-center justify-between text-xs text-rose-300">
            <span className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400" />
              Your membership expired on {formatDate(card.valid_until)}.
            </span>
            <Button size="sm" variant="danger" onClick={() => navigate('/join')}>
              Renew Now
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* The Digital Member ID Card (Left / Center) */}
        <div className="lg:col-span-7 flex flex-col items-center">
          <div
            ref={cardRef}
            className={`w-full max-w-md rounded-3xl p-6 sm:p-7 relative overflow-hidden transition-all duration-300 shadow-2xl border ${
              isActive
                ? 'bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border-emerald-500/40 shadow-emerald-950/30 ring-1 ring-emerald-500/20'
                : 'bg-slate-900 border-slate-800 opacity-90'
            }`}
          >
            {/* Background Aesthetic Watermark */}
            <div className="absolute -right-8 -top-8 w-44 h-44 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
            <div className="absolute -left-8 -bottom-8 w-44 h-44 bg-teal-500/5 rounded-full blur-2xl pointer-events-none" />

            {/* Card Header */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center font-black text-slate-950 text-sm shadow-md">
                  SSA
                </div>
                <div>
                  <h3 className="font-extrabold text-white text-sm tracking-tight leading-tight">
                    Student Software Association
                  </h3>
                  <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wider">
                    Official Member Pass
                  </p>
                </div>
              </div>

              <StatusChip status={card.status} />
            </div>

            {/* Member Details & Avatar */}
            <div className="py-5 flex items-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-slate-800 to-slate-700 border border-slate-600/50 flex items-center justify-center text-white text-xl font-bold shadow-inner">
                {card.full_name ? card.full_name.charAt(0).toUpperCase() : 'U'}
              </div>

              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-bold text-white truncate">
                  {card.full_name}
                </h2>
                <div className="flex items-center gap-2 mt-1">
                  <RoleBadge role={card.role || user?.role || 'member'} />
                  <span className="text-xs text-slate-400 font-mono">
                    {card.plan_name}
                  </span>
                </div>
              </div>
            </div>

            {/* QR Code Container */}
            <div className="my-2 p-5 bg-white rounded-2xl flex flex-col items-center justify-center shadow-lg">
              <QRCodeSVG
                value={card.qr_payload || card.member_code}
                size={168}
                level="H"
                includeMargin={false}
                className="w-full max-w-[168px] h-auto"
              />
              <div className="mt-3 text-center">
                <span className="font-mono text-xs font-bold text-slate-900 tracking-wider select-all bg-slate-100 px-2 py-0.5 rounded">
                  {card.member_code}
                </span>
                <p className="text-[10px] text-slate-500 mt-1">
                  Scan with SSA Hub Scanner to verify
                </p>
              </div>
            </div>

            {/* Card Footer Details */}
            <div className="pt-4 border-t border-slate-800/80 grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-[10px] uppercase tracking-wider text-slate-500 block">
                  Valid Until
                </span>
                <span className="font-semibold text-slate-200">
                  {formatDate(card.valid_until)}
                </span>
              </div>
              <div className="text-right">
                <span className="text-[10px] uppercase tracking-wider text-slate-500 block">
                  Remaining
                </span>
                <span className={`font-semibold ${isExpiringSoon ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {typeof card.days_remaining === 'number' ? `${card.days_remaining} Days` : 'Active'}
                </span>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3 mt-6">
            <Button variant="outline" size="sm" onClick={handlePrint}>
              <Printer className="w-4 h-4 mr-1.5" />
              Print / Save Pass
            </Button>
            {isExpiringSoon && (
              <Button variant="primary" size="sm" onClick={() => navigate('/join')}>
                Renew Pass
              </Button>
            )}
          </div>
        </div>

        {/* Member Privileges and Info (Right) */}
        <div className="lg:col-span-5 space-y-6">
          <Card className="border-slate-800 bg-slate-900/70">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold text-white flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Active Membership Privileges
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Included with your {card.plan_name}
              </CardDescription>
            </CardHeader>

            <CardContent>
              <ul className="space-y-3 text-xs sm:text-sm text-slate-300">
                <li className="flex items-start gap-2.5">
                  <div className="rounded-full p-0.5 bg-emerald-500/20 text-emerald-400 mt-0.5">
                    <UserCheck className="w-3.5 h-3.5" />
                  </div>
                  <span>Free or discounted access to all tech workshops and speaker sessions.</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <div className="rounded-full p-0.5 bg-emerald-500/20 text-emerald-400 mt-0.5">
                    <QrCode className="w-3.5 h-3.5" />
                  </div>
                  <span>Instant event entry without queueing via dynamic verification pass.</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <div className="rounded-full p-0.5 bg-emerald-500/20 text-emerald-400 mt-0.5">
                    <Sparkles className="w-3.5 h-3.5" />
                  </div>
                  <span>Voting eligibility in annual executive committee club elections.</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <div className="rounded-full p-0.5 bg-emerald-500/20 text-emerald-400 mt-0.5">
                    <Calendar className="w-3.5 h-3.5" />
                  </div>
                  <span>Priority registration slots for competitive hackathons.</span>
                </li>
              </ul>
            </CardContent>
          </Card>

          {/* Quick Tickets Preview Card */}
          <Card className="border-slate-800 bg-slate-900/70">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base font-bold text-white flex items-center gap-2">
                  <Ticket className="w-4 h-4 text-emerald-400" />
                  My Event Tickets
                </CardTitle>
                <CardDescription className="text-xs text-slate-400">
                  {myTickets && myTickets.filter(t => t.status === 'valid').length > 0
                    ? `${myTickets.filter(t => t.status === 'valid').length} valid entry pass(es) ready`
                    : 'Manage your event reservations & QR entry passes'}
                </CardDescription>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate('/me/tickets')}
                className="text-xs text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
              >
                View Tickets <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </CardHeader>

            <CardContent>
              {myTickets && myTickets.filter(t => t.status === 'valid').length > 0 ? (
                <div className="space-y-2">
                  {myTickets.filter(t => t.status === 'valid').slice(0, 2).map(t => (
                    <div
                      key={t.id}
                      onClick={() => navigate('/me/tickets')}
                      className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between text-xs hover:border-slate-700 cursor-pointer transition-colors"
                    >
                      <div className="min-w-0 pr-2">
                        <p className="font-semibold text-white truncate">{t.event_title}</p>
                        <p className="text-[11px] text-slate-400">{t.ticket_type_name} • {t.venue}</p>
                      </div>
                      <span className="font-mono text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded shrink-0">
                        {t.code}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">
                  No upcoming event tickets booked yet.
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-emerald-400 p-0 ml-1.5 h-auto text-xs"
                    onClick={() => navigate('/events')}
                  >
                    Explore events
                  </Button>
                </p>
              )}
            </CardContent>
          </Card>

          {/* Email Notification Preferences Card */}
          <Card className="border-slate-800/80 bg-slate-900/60 shadow-xl overflow-hidden">
            <CardHeader className="pb-3 border-b border-slate-800/60 flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                  <Mail className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle className="text-base text-white">Email Notification Preferences</CardTitle>
                  <CardDescription className="text-xs text-slate-400">
                    Manage club communications
                  </CardDescription>
                </div>
              </div>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                  emailOptIn
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}
              >
                {emailOptIn ? 'Subscribed' : 'Muted'}
              </span>
            </CardHeader>
            <CardContent className="pt-4 space-y-3">
              <div className="flex items-center justify-between gap-4">
                <div className="space-y-0.5">
                  <label
                    htmlFor="email-notifications-member-switch"
                    className="text-xs font-semibold text-slate-200 cursor-pointer"
                  >
                    Announcement Broadcasts
                  </label>
                  <p className="text-[11px] text-slate-400">
                    Receive email deliveries for campus updates, deadlines, and schedule changes.
                  </p>
                </div>
                <button
                  type="button"
                  id="email-notifications-member-switch"
                  role="switch"
                  aria-checked={emailOptIn}
                  disabled={isUpdatingPreferences}
                  onClick={handleToggleEmailOptIn}
                  data-testid="email-opt-in-toggle"
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-50 ${
                    emailOptIn ? 'bg-emerald-500' : 'bg-slate-700'
                  }`}
                >
                  <span className="sr-only">Toggle announcement email notifications</span>
                  <span
                    aria-hidden="true"
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                      emailOptIn ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
              <p className="text-[10px] text-slate-500 italic pt-1">
                Deliveries are sent to <span className="font-mono text-slate-400">{user?.email}</span>. Essential receipts cannot be muted.
              </p>
            </CardContent>
          </Card>

          {/* Quick Help Card */}
          <Card className="border-slate-800/80 bg-slate-900/40">
            <CardContent className="pt-6 text-xs text-slate-400 space-y-2">
              <h4 className="font-semibold text-slate-200">How to use your digital card:</h4>
              <p>
                Save this page to your mobile home screen or screenshot your QR code. Event volunteers will scan this code to check you in seamlessly.
              </p>
              <div className="pt-2">
                <Button variant="ghost" size="sm" className="text-emerald-400 p-0 h-auto" onClick={() => navigate('/join')}>
                  View all club plans <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
