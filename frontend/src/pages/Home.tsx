import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import { eventsApi } from '../api/events';
import { announcementsApi } from '../api/announcements';
import { formatDateTime } from '../lib/formatDate';
import { formatRelativeTime } from '../lib/formatRelativeTime';
import {
  Sparkles,
  ShieldCheck,
  QrCode,
  Award,
  ArrowRight,
  Calendar,
  MapPin,
  Megaphone,
  Pin,
  RefreshCw,
  AlertCircle,
  Tag,
} from 'lucide-react';

export function Home() {
  const { isAuthenticated } = useAuth();

  // Next Upcoming Event Query
  const {
    data: eventsData,
    isLoading: isEventsLoading,
    isError: isEventsError,
    refetch: refetchEvents,
  } = useQuery({
    queryKey: ['events', 'home-next'],
    queryFn: () => eventsApi.getEvents({ status: 'published', page_size: 10 }),
  });

  // Latest Announcement Query
  const {
    data: announcementsData,
    isLoading: isAnnouncementsLoading,
    isError: isAnnouncementsError,
    refetch: refetchAnnouncements,
  } = useQuery({
    queryKey: ['announcements', 'home-latest'],
    queryFn: () => announcementsApi.getAnnouncements({ page_size: 1 }),
  });

  // Calculate the next upcoming event
  const nextEvent = eventsData?.items && eventsData.items.length > 0
    ? [...eventsData.items].sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())[0]
    : null;

  const latestAnnouncement = announcementsData?.items && announcementsData.items.length > 0
    ? announcementsData.items[0]
    : null;

  return (
    <div className="space-y-12 sm:space-y-16">
      {/* Hero Section */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-900 via-indigo-800 to-slate-900 text-white p-8 sm:p-14 shadow-2xl border border-indigo-700/40">
        <div className="absolute top-0 right-0 -mr-16 -mt-16 w-80 h-80 rounded-full bg-indigo-500/20 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 -ml-16 -mb-16 w-80 h-80 rounded-full bg-amber-500/15 blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/25 border border-indigo-400/30 text-indigo-200 text-xs font-semibold tracking-wide uppercase">
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            Official Student Association Platform
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white leading-tight">
            One Hub for Every Student Leader, Member &amp; Event
          </h1>

          <p className="text-base sm:text-lg text-indigo-100/90 leading-relaxed max-w-2xl">
            Join the campus's premier student community. Get your digital verified ID card, instant access to club privileges, workshops, and exclusive member discounts.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-4">
            {isAuthenticated ? (
              <Link to="/me">
                <Button variant="secondary" size="lg" leftIcon={<QrCode className="w-5 h-5" />}>
                  Open My Membership Card
                </Button>
              </Link>
            ) : (
              <>
                <Link to="/register">
                  <Button variant="secondary" size="lg" rightIcon={<ArrowRight className="w-5 h-5" />}>
                    Join as a Member
                  </Button>
                </Link>
                <Link to="/login">
                  <Button
                    variant="outline"
                    size="lg"
                    className="border-white/30 text-white hover:bg-white/10 hover:border-white/50 bg-white/5"
                  >
                    Sign In
                  </Button>
                </Link>
              </>
            )}
            <Link to="/events">
              <Button
                variant="secondary"
                size="lg"
                className="bg-amber-400 hover:bg-amber-300 text-slate-900 border-none font-bold"
              >
                Browse Events
              </Button>
            </Link>
            <Link to="/announcements">
              <Button
                variant="ghost"
                size="lg"
                className="text-indigo-200 hover:text-white hover:bg-white/10"
                leftIcon={<Megaphone className="w-4 h-4" />}
              >
                Announcements
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Live Highlights: Next Event & Latest Announcement */}
      <section className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              Live Campus Updates
            </h2>
            <p className="text-sm text-slate-500">
              Check out what's coming next and recent official club dispatches.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Card 1: Next Upcoming Event */}
          <Card className="flex flex-col justify-between border-slate-200/80 hover:border-indigo-300 hover:shadow-md transition-all">
            <CardContent className="p-6 flex-1 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200/60">
                    <Calendar className="w-3.5 h-3.5 text-amber-600" />
                    Next Upcoming Event
                  </span>
                  <Link
                    to="/events"
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                  >
                    All events
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>

                {isEventsLoading && (
                  <div className="space-y-3 py-2">
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-4 w-2/3" />
                  </div>
                )}

                {isEventsError && (
                  <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs">
                      <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                      <span>Could not load upcoming events.</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => refetchEvents()}
                      leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
                    >
                      Retry
                    </Button>
                  </div>
                )}

                {!isEventsLoading && !isEventsError && !nextEvent && (
                  <EmptyState
                    icon={<Calendar className="w-6 h-6 text-slate-400" />}
                    title="No upcoming events"
                    description="Stay tuned! New club events will be published soon."
                    actionLabel="View past events"
                    onAction={() => {}}
                    className="p-6"
                  />
                )}

                {!isEventsLoading && !isEventsError && nextEvent && (
                  <div className="space-y-3">
                    <h3 className="text-xl font-bold text-slate-900 line-clamp-1">
                      {nextEvent.title}
                    </h3>

                    <div className="space-y-1.5 text-sm text-slate-600">
                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
                        <span className="font-medium text-slate-800">
                          {formatDateTime(nextEvent.starts_at)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-slate-400 shrink-0" />
                        <span className="line-clamp-1">{nextEvent.venue || 'Campus Venue TBA'}</span>
                      </div>
                    </div>

                    {nextEvent.description && (
                      <p className="text-sm text-slate-500 line-clamp-2 pt-1">
                        {nextEvent.description}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {!isEventsLoading && !isEventsError && nextEvent && (
                <div className="pt-6 border-t border-slate-100 mt-6 flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700 font-semibold bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200/60">
                    Registration Open
                  </span>
                  <Link to={`/events/${nextEvent.id}`}>
                    <Button variant="primary" size="sm" rightIcon={<ArrowRight className="w-4 h-4" />}>
                      View &amp; Get Tickets
                    </Button>
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Card 2: Latest Announcement */}
          <Card className="flex flex-col justify-between border-slate-200/80 hover:border-indigo-300 hover:shadow-md transition-all">
            <CardContent className="p-6 flex-1 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-800 border border-indigo-200/60">
                    <Megaphone className="w-3.5 h-3.5 text-indigo-600" />
                    Latest Announcement
                  </span>
                  <Link
                    to="/announcements"
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                  >
                    All notices
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>

                {isAnnouncementsLoading && (
                  <div className="space-y-3 py-2">
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                )}

                {isAnnouncementsError && (
                  <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs">
                      <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                      <span>Could not load announcements.</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => refetchAnnouncements()}
                      leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
                    >
                      Retry
                    </Button>
                  </div>
                )}

                {!isAnnouncementsLoading && !isAnnouncementsError && !latestAnnouncement && (
                  <EmptyState
                    icon={<Megaphone className="w-6 h-6 text-slate-400" />}
                    title="No announcements posted"
                    description="Club organizers have not published any announcements yet."
                    className="p-6"
                  />
                )}

                {!isAnnouncementsLoading && !isAnnouncementsError && latestAnnouncement && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-semibold bg-slate-100 text-slate-700 capitalize">
                        <Tag className="w-3 h-3 text-slate-400" />
                        {latestAnnouncement.category}
                      </span>
                      {latestAnnouncement.is_pinned && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                          <Pin className="w-3 h-3 text-amber-600" />
                          Pinned
                        </span>
                      )}
                      <span className="text-xs text-slate-400">
                        {formatRelativeTime(latestAnnouncement.published_at)}
                      </span>
                    </div>

                    <h3 className="text-xl font-bold text-slate-900 line-clamp-1">
                      {latestAnnouncement.title}
                    </h3>

                    {/* Plain text body preview - React escaping ensures XSS safety */}
                    <p className="text-sm text-slate-600 line-clamp-3 leading-relaxed whitespace-pre-line">
                      {latestAnnouncement.body_preview}
                    </p>
                  </div>
                )}
              </div>

              {!isAnnouncementsLoading && !isAnnouncementsError && latestAnnouncement && (
                <div className="pt-6 border-t border-slate-100 mt-6 flex items-center justify-between">
                  <span className="text-xs text-slate-500 font-medium">
                    Posted by: <strong className="text-slate-800">{latestAnnouncement.author_name}</strong>
                  </span>
                  <Link to="/announcements">
                    <Button variant="outline" size="sm" rightIcon={<ArrowRight className="w-4 h-4" />}>
                      Read Full Notice
                    </Button>
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Feature Highlights */}
      <section className="space-y-6">
        <div className="text-center max-w-xl mx-auto space-y-2">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Why Join SSA Hub?
          </h2>
          <p className="text-sm text-slate-600">
            Engineered from the ground up for seamless student governance and club perks.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="hover:border-indigo-200 transition-all">
            <CardContent className="p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                <QrCode className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Digital QR Verification</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Scan-ready digital membership card directly on your phone. Verified in milliseconds at club venue entries.
              </p>
            </CardContent>
          </Card>

          <Card className="hover:border-amber-200 transition-all">
            <CardContent className="p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
                <Award className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Transparent Annual Plans</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Clear pricing, instant activations, and renewal tracking with no hidden charges or surprises.
              </p>
            </CardContent>
          </Card>

          <Card className="hover:border-emerald-200 transition-all">
            <CardContent className="p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Role-Based Governance</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Dedicated tools for organizers, treasurers, and volunteers to verify identities and maintain rosters.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* CTA section */}
      <section className="rounded-3xl bg-slate-900 text-white p-8 sm:p-12 text-center max-w-4xl mx-auto space-y-6">
        <h2 className="text-2xl sm:text-3xl font-bold text-white">
          Ready to become an official member?
        </h2>
        <p className="text-sm sm:text-base text-slate-300 max-w-xl mx-auto">
          Sign up today to activate your annual membership and unlock all student privileges.
        </p>
        <div className="flex justify-center gap-4">
          <Link to="/join">
            <Button variant="secondary" size="lg">
              View Membership Plans
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
