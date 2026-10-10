import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { QRCodeSVG } from 'qrcode.react';
import { ticketsApi } from '../../api/tickets';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { formatDate } from '../../lib/formatDate';
import { formatINR } from '../../lib/formatINR';
import type { TicketItem } from '../../types/events';
import {
  Ticket,
  Calendar,
  MapPin,
  QrCode,
  X,
  Sparkles,
  CheckCircle2,
  Clock,
  AlertCircle,
  Sun,
} from 'lucide-react';

export function MyTickets() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'upcoming' | 'past'>('upcoming');
  const [selectedTicket, setSelectedTicket] = useState<TicketItem | null>(null);

  const { data: tickets, isLoading, error, refetch } = useQuery({
    queryKey: ['myTickets'],
    queryFn: ticketsApi.getMyTickets,
  });

  const allTickets = tickets ?? [];
  const [nowMs] = useState(() => Date.now());
  const getEndTime = (t: TicketItem) => (t.ends_at ? new Date(t.ends_at).getTime() : new Date(t.starts_at).getTime());

  const upcomingTickets = allTickets.filter(
    (t) => getEndTime(t) >= nowMs && t.status !== 'void'
  );
  const pastTickets = allTickets.filter(
    (t) => getEndTime(t) < nowMs || t.status === 'void'
  );

  const displayedTickets = activeTab === 'upcoming' ? upcomingTickets : pastTickets;

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-12 w-64 rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Skeleton className="h-80 rounded-2xl" />
          <Skeleton className="h-80 rounded-2xl" />
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-md mx-auto px-4 py-16">
        <ErrorState
          title="Could not load tickets"
          message="Failed to retrieve your purchased or registered event passes."
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-2">
            <Ticket className="w-3.5 h-3.5" />
            Verified Event Access
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">My Event Tickets</h1>
          <p className="text-sm text-slate-400 mt-1">
            Display your admission pass QR code at the event entrance for fast check-in.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/events')}
          className="self-start sm:self-auto text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
        >
          <Sparkles className="w-4 h-4 mr-1.5" />
          Browse All Events
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 mb-8 gap-6">
        <button
          onClick={() => setActiveTab('upcoming')}
          className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors border-b-2 -mb-px ${
            activeTab === 'upcoming'
              ? 'border-emerald-400 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Upcoming Events
          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-800 text-slate-300">
            {upcomingTickets.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('past')}
          className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors border-b-2 -mb-px ${
            activeTab === 'past'
              ? 'border-emerald-400 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Past / Expired
          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-800 text-slate-300">
            {pastTickets.length}
          </span>
        </button>
      </div>

      {/* Empty State */}
      {displayedTickets.length === 0 ? (
        <EmptyState
          icon={<Ticket className="w-14 h-14 text-slate-500" />}
          title={activeTab === 'upcoming' ? 'No Upcoming Tickets' : 'No Past Tickets'}
          description={
            activeTab === 'upcoming'
              ? "You haven't reserved tickets for any upcoming events yet. Check out what's happening on campus!"
              : 'You have no past event ticket history.'
          }
          actionLabel="Explore Campus Events"
          onAction={() => navigate('/events')}
        />
      ) : (
        /* Ticket Cards Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {displayedTickets.map((t) => {
            const isValid = t.status === 'valid';
            const isUsed = t.status === 'used';
            const isVoid = t.status === 'void';

            return (
              <Card
                key={t.id}
                className={`border-slate-800 bg-slate-900/80 hover:border-slate-700 transition-all flex flex-col justify-between overflow-hidden group ${
                  isValid ? 'hover:shadow-lg hover:shadow-emerald-950/20' : 'opacity-85'
                }`}
              >
                <div>
                  {/* Status Banner */}
                  <div className="px-4 py-2 border-b border-slate-800/80 bg-slate-950/50 flex items-center justify-between text-xs">
                    <span className="font-mono text-slate-400 font-semibold tracking-wider">
                      {t.code}
                    </span>
                    {isValid && (
                      <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Valid Pass
                      </span>
                    )}
                    {isUsed && (
                      <span className="inline-flex items-center gap-1 text-amber-400 font-medium">
                        <Clock className="w-3.5 h-3.5" /> Checked In
                      </span>
                    )}
                    {isVoid && (
                      <span className="inline-flex items-center gap-1 text-rose-400 font-medium">
                        <AlertCircle className="w-3.5 h-3.5" /> Cancelled
                      </span>
                    )}
                  </div>

                  <CardHeader className="pb-3">
                    <div className="text-xs text-emerald-400 font-semibold mb-1">
                      {t.ticket_type_name}
                    </div>
                    <CardTitle className="text-lg font-bold text-white leading-snug group-hover:text-emerald-300 transition-colors">
                      {t.event_title}
                    </CardTitle>
                  </CardHeader>

                  <CardContent className="space-y-2.5 text-xs text-slate-300">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-slate-500 shrink-0" />
                      <span>{formatDate(t.starts_at)}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-slate-500 shrink-0" />
                      <span className="truncate">{t.venue}</span>
                    </div>

                    {isUsed && t.checked_in_at && (
                      <div className="pt-2 text-[11px] text-amber-400/90 font-medium">
                        Scanned at door: {formatDate(t.checked_in_at)}
                      </div>
                    )}
                  </CardContent>
                </div>

                <CardFooter className="pt-3 border-t border-slate-800/60 bg-slate-950/30 flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300">
                    {t.price_paid === 0 ? 'Free Pass' : formatINR(t.price_paid)}
                  </span>

                  <Button
                    size="sm"
                    variant={isValid ? 'primary' : 'outline'}
                    onClick={() => setSelectedTicket(t)}
                    className="flex items-center gap-1.5"
                  >
                    <QrCode className="w-4 h-4" />
                    {isValid ? 'View QR Pass' : 'View Pass'}
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}

      {/* High-Contrast QR Fullscreen Modal */}
      {selectedTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-fade-in">
          <div className="relative w-full max-w-sm rounded-3xl bg-slate-900 border border-slate-800 p-6 shadow-2xl text-center overflow-hidden">
            {/* Top gradient glow */}
            <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-500" />

            {/* Close Button */}
            <button
              onClick={() => setSelectedTicket(null)}
              className="absolute top-4 right-4 p-2 rounded-full text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label="Close pass"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Header info */}
            <div className="pt-2 mb-4">
              <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-2">
                {selectedTicket.ticket_type_name}
              </span>
              <h3 className="text-lg font-black text-white leading-snug px-4">
                {selectedTicket.event_title}
              </h3>
            </div>

            {/* High-Contrast QR Code container */}
            <div className="mx-auto my-3 p-5 bg-white rounded-2xl shadow-xl flex flex-col items-center justify-center max-w-[240px]">
              <QRCodeSVG
                value={selectedTicket.code}
                size={196}
                level="H"
                includeMargin={false}
                className="w-full max-w-[196px] h-auto"
              />
              <div className="mt-3 font-mono text-base font-extrabold text-slate-950 tracking-widest select-all bg-slate-100 px-3 py-1 rounded">
                {selectedTicket.code}
              </div>
            </div>

            {/* Attendee & Schedule Meta */}
            <div className="mt-4 pt-3 border-t border-slate-800 text-xs space-y-1.5 text-slate-300">
              <p className="font-semibold text-white">
                Attendee: {user?.full_name || 'SSA Member / Guest'}
              </p>
              <p className="text-slate-400">
                {formatDate(selectedTicket.starts_at)} • {selectedTicket.venue}
              </p>
            </div>

            {/* Door Scanning Brightness Hint */}
            <div className="mt-4 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center gap-2 text-xs text-amber-300">
              <Sun className="w-4 h-4 text-amber-400 shrink-0" />
              <span>Turn phone brightness to max for instant scanning</span>
            </div>

            <div className="mt-5">
              <Button
                variant="outline"
                size="sm"
                className="w-full text-slate-300"
                onClick={() => setSelectedTicket(null)}
              >
                Close Pass
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
