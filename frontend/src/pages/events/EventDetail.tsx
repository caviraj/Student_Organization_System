import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { eventsApi } from '../../api/events';
import { ticketsApi } from '../../api/tickets';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/ui/Toast';
import { formatDateTime } from '../../lib/formatDate';
import { formatINR } from '../../lib/formatINR';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { ApiError } from '../../types/api';
import type { TicketType } from '../../types/events';
import {
  Calendar,
  MapPin,
  Clock,
  Ticket,
  Sparkles,
  ArrowLeft,
  CheckCircle2,
  Plus,
  Minus,
  Crown,
} from 'lucide-react';

export function EventDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const { showToast } = useToast();

  const [selectedTierId, setSelectedTierId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState<number>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    data: event,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['event', id],
    queryFn: () => eventsApi.getEvent(id!),
    enabled: !!id,
  });

  const isActiveMember = user?.membership?.status === 'active';
  const ticketTypes = event?.ticket_types ?? [];

  // Default selection to first available tier if none selected
  const activeTier = ticketTypes.find((t) => t.id === selectedTierId) ||
    ticketTypes.find((t) => (t.seats_left ?? 1) > 0) ||
    ticketTypes[0];

  const maxAvailable = activeTier?.seats_left !== undefined ? activeTier.seats_left : activeTier?.capacity ?? 10;
  const maxAllowedQuantity = Math.min(10, Math.max(0, maxAvailable));
  const isTierSoldOut = maxAllowedQuantity === 0;

  const unitPrice = activeTier
    ? (isActiveMember ? activeTier.member_price : activeTier.non_member_price)
    : 0;
  const totalPrice = unitPrice * quantity;
  const savingsPerTicket = activeTier ? Math.max(0, activeTier.non_member_price - activeTier.member_price) : 0;
  const totalSavings = savingsPerTicket * quantity;

  const handleSelectTier = (tier: TicketType) => {
    setSelectedTierId(tier.id);
    const available = tier.seats_left !== undefined ? tier.seats_left : tier.capacity;
    if (quantity > available) {
      setQuantity(Math.max(1, Math.min(available, 10)));
    }
  };

  const handleQuantityChange = (delta: number) => {
    setQuantity((prev) => {
      const next = prev + delta;
      if (next < 1) return 1;
      if (next > maxAllowedQuantity) return maxAllowedQuantity;
      return next;
    });
  };

  const handleCheckout = async () => {
    if (!activeTier) return;

    if (!isAuthenticated) {
      showToast('Please sign in or create an account to reserve your ticket.', 'info');
      navigate(`/login?redirect=/events/${id}`);
      return;
    }

    if (isTierSoldOut) {
      showToast('This ticket type is no longer available.', 'error');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await ticketsApi.checkout({
        ticket_type_id: activeTier.id,
        quantity,
      });

      // Free ticket flow
      if (totalPrice === 0 || res.amount === 0) {
        showToast(`Successfully booked ${quantity} ticket(s) for ${event?.title}!`, 'success');
        navigate('/me/tickets');
        return;
      }

      // Paid ticket flow: routes to mock payment / checkout
      showToast('Order created. Proceeding to checkout...', 'info');
      navigate(`/checkout/${res.order_id}`);
    } catch (err: unknown) {
      if (err instanceof ApiError && (err.status === 409 || err.code === 'SOLD_OUT')) {
        const availableCount = err.details?.available ?? 0;
        showToast(`Sorry, this tier just sold out or has only ${availableCount} seats left. Updating capacity...`, 'error');
        refetch();
      } else {
        showToast(err instanceof Error ? err.message : 'Unable to initiate checkout. Please try again.', 'error');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-72 w-full rounded-3xl" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-4">
            <Skeleton className="h-10 w-3/4" />
            <Skeleton className="h-24 w-full" />
          </div>
          <Skeleton className="h-80 w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  if (isError || !event) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16">
        <ErrorState
          title="Event Not Found"
          message={error instanceof Error ? error.message : 'The event could not be found or has been unpublished.'}
          onRetry={() => refetch()}
        />
        <div className="text-center mt-6">
          <Link to="/events">
            <Button variant="outline" leftIcon={<ArrowLeft className="w-4 h-4" />}>
              Back to Events
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      {/* Back button */}
      <div className="mb-6">
        <Link
          to="/events"
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-indigo-600 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to All Events</span>
        </Link>
      </div>

      {/* Hero Banner */}
      <div className="relative mb-8 overflow-hidden rounded-3xl bg-slate-900 text-white shadow-xl">
        <div className="h-64 sm:h-80 w-full relative">
          {event.banner_url ? (
            <img
              src={event.banner_url}
              alt={event.title}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex items-center justify-center p-8">
              <Calendar className="w-16 h-16 text-indigo-400 opacity-60" />
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent" />
        </div>

        {/* Hero Title & Info Overlay */}
        <div className="absolute bottom-0 left-0 right-0 p-6 sm:p-8">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-500/30 backdrop-blur-md text-indigo-200 text-xs font-semibold mb-3 border border-indigo-400/30">
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            <span>SSA Hub Official Event</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold text-white tracking-tight mb-3">
            {event.title}
          </h1>
          <div className="flex flex-wrap items-center gap-4 text-xs sm:text-sm text-slate-300">
            <div className="flex items-center gap-1.5">
              <Clock className="w-4 h-4 text-indigo-400" />
              <span>{formatDateTime(event.starts_at)} – {formatDateTime(event.ends_at)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <MapPin className="w-4 h-4 text-indigo-400" />
              <span>{event.venue}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Event Details & Ticket Tiers */}
        <div className="lg:col-span-2 space-y-8">
          {/* Member Savings Banner for Guests / Non-members */}
          {!isActiveMember && savingsPerTicket > 0 && (
            <div className="p-4 rounded-2xl bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/30 flex items-start gap-3">
              <div className="p-2 rounded-xl bg-amber-500/20 text-amber-700 shrink-0">
                <Crown className="w-5 h-5 text-amber-600" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-bold text-amber-900">
                  SSA Club Members save {formatINR(savingsPerTicket)} per ticket!
                </p>
                <p className="text-xs text-amber-800/80 mt-0.5 leading-relaxed">
                  Join SSA Hub today to unlock member discounts on all campus events and workshops.
                </p>
                <Link to="/join" className="inline-block mt-2">
                  <Button variant="outline" size="sm" className="text-xs border-amber-600 text-amber-900 hover:bg-amber-100">
                    View Membership Plans
                  </Button>
                </Link>
              </div>
            </div>
          )}

          {/* Description */}
          <Card className="p-6">
            <h2 className="text-lg font-bold text-slate-900 mb-3">About this Event</h2>
            <div className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">
              {event.description || 'No detailed description provided for this event.'}
            </div>
          </Card>

          {/* Ticket Tiers Selection */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Ticket className="w-5 h-5 text-indigo-600" />
                Select Ticket Tier
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                {ticketTypes.length} {ticketTypes.length === 1 ? 'tier' : 'tiers'} available
              </span>
            </div>

            {ticketTypes.length === 0 ? (
              <Card className="p-6 text-center text-slate-500">
                <Ticket className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
                <p className="text-sm font-medium">No tickets currently on sale for this event.</p>
              </Card>
            ) : (
              <div className="space-y-3">
                {ticketTypes.map((tier) => {
                  const isSelected = activeTier?.id === tier.id;
                  const seatsLeft = tier.seats_left !== undefined ? tier.seats_left : tier.capacity;
                  const isSoldOut = seatsLeft <= 0;
                  const ratio = tier.capacity > 0 ? (seatsLeft / tier.capacity) * 100 : 0;

                  return (
                    <div
                      key={tier.id}
                      onClick={() => !isSoldOut && handleSelectTier(tier)}
                      className={`relative p-5 rounded-2xl border transition-all ${
                        isSoldOut
                          ? 'opacity-60 bg-slate-50 border-slate-200 cursor-not-allowed'
                          : isSelected
                          ? 'bg-indigo-50/70 border-indigo-600 ring-2 ring-indigo-600/20 shadow-sm cursor-pointer'
                          : 'bg-white border-slate-200 hover:border-indigo-300 hover:bg-slate-50/50 cursor-pointer'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-bold text-base text-slate-900">{tier.name}</h3>
                            {isSoldOut ? (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700">
                                Sold Out
                              </span>
                            ) : seatsLeft <= 5 ? (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700">
                                {seatsLeft} seats left
                              </span>
                            ) : null}
                          </div>

                          {/* Member vs Non-member price breakdown */}
                          <div className="flex items-center gap-3 pt-1 text-xs">
                            <div>
                              <span className="text-slate-500">Member: </span>
                              <span className="font-bold text-slate-900">
                                {tier.member_price === 0 ? 'Free' : formatINR(tier.member_price)}
                              </span>
                            </div>
                            <span className="text-slate-300">•</span>
                            <div>
                              <span className="text-slate-500">Regular: </span>
                              <span className="font-bold text-slate-900">
                                {tier.non_member_price === 0 ? 'Free' : formatINR(tier.non_member_price)}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Price Badge */}
                        <div className="text-right">
                          <div className="text-lg font-black text-indigo-600">
                            {isActiveMember
                              ? tier.member_price === 0
                                ? 'Free'
                                : formatINR(tier.member_price)
                              : tier.non_member_price === 0
                              ? 'Free'
                              : formatINR(tier.non_member_price)}
                          </div>
                          {isActiveMember ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                              Member Rate
                            </span>
                          ) : (
                            <span className="text-[10px] text-slate-400 font-medium">Standard Rate</span>
                          )}
                        </div>
                      </div>

                      {/* Capacity progress bar */}
                      {!isSoldOut && (
                        <div className="mt-3 pt-3 border-t border-slate-100">
                          <div className="flex justify-between items-center text-[11px] text-slate-500 mb-1">
                            <span>Remaining Seats</span>
                            <span className="font-semibold text-slate-700">
                              {seatsLeft} of {tier.capacity} left
                            </span>
                          </div>
                          <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                ratio <= 10
                                  ? 'bg-rose-500'
                                  : ratio <= 25
                                  ? 'bg-amber-500'
                                  : 'bg-emerald-500'
                              }`}
                              style={{ width: `${Math.min(100, ratio)}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Checkout Summary Box */}
        <div className="space-y-6">
          <Card className="p-6 sticky top-24 border-slate-200 shadow-md">
            <h3 className="font-bold text-lg text-slate-900 mb-4 pb-3 border-b border-slate-100 flex items-center gap-2">
              <Ticket className="w-5 h-5 text-indigo-600" />
              Ticket Summary
            </h3>

            {activeTier ? (
              <div className="space-y-5">
                <div>
                  <p className="text-xs text-slate-500 font-medium">Selected Tier</p>
                  <p className="text-sm font-bold text-slate-900">{activeTier.name}</p>
                </div>

                {/* Quantity Stepper */}
                <div>
                  <div className="flex justify-between items-center mb-1.5">
                    <span className="text-xs text-slate-500 font-medium">Quantity</span>
                    <span className="text-xs text-slate-400">Max {maxAllowedQuantity}</span>
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-xl border border-slate-200 bg-slate-50/50">
                    <button
                      type="button"
                      onClick={() => handleQuantityChange(-1)}
                      disabled={quantity <= 1 || isTierSoldOut}
                      className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                      aria-label="Decrease quantity"
                    >
                      <Minus className="w-3.5 h-3.5" />
                    </button>
                    <span className="font-bold text-base text-slate-900 px-4">{quantity}</span>
                    <button
                      type="button"
                      onClick={() => handleQuantityChange(1)}
                      disabled={quantity >= maxAllowedQuantity || isTierSoldOut}
                      className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                      aria-label="Increase quantity"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Price Breakdown */}
                <div className="space-y-2 pt-3 border-t border-slate-100 text-xs">
                  <div className="flex justify-between text-slate-600">
                    <span>
                      Unit Price ({isActiveMember ? 'Member' : 'Standard'})
                    </span>
                    <span>{unitPrice === 0 ? 'Free' : formatINR(unitPrice)}</span>
                  </div>
                  <div className="flex justify-between text-slate-600">
                    <span>Quantity</span>
                    <span>× {quantity}</span>
                  </div>

                  {isActiveMember && totalSavings > 0 && (
                    <div className="flex justify-between text-emerald-600 font-semibold bg-emerald-50/80 p-2 rounded-lg">
                      <span className="flex items-center gap-1">
                        <Crown className="w-3.5 h-3.5" />
                        Member Savings
                      </span>
                      <span>-{formatINR(totalSavings)}</span>
                    </div>
                  )}

                  <div className="flex justify-between items-baseline pt-2 border-t border-slate-200 text-sm">
                    <span className="font-bold text-slate-900">Total Amount</span>
                    <span className="text-xl font-extrabold text-indigo-600">
                      {totalPrice === 0 ? 'Free' : formatINR(totalPrice)}
                    </span>
                  </div>
                </div>

                {/* Checkout CTA */}
                <Button
                  variant="primary"
                  size="lg"
                  onClick={handleCheckout}
                  isLoading={isSubmitting}
                  disabled={isTierSoldOut || ticketTypes.length === 0}
                  className="w-full justify-center shadow-lg shadow-indigo-600/20 font-bold"
                >
                  {isTierSoldOut
                    ? 'Sold Out'
                    : totalPrice === 0
                    ? 'Confirm Free Ticket'
                    : `Buy Ticket (${formatINR(totalPrice)})`}
                </Button>

                {!isAuthenticated && (
                  <p className="text-[11px] text-center text-slate-500">
                    You'll be prompted to sign in or create an account to receive your tickets.
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-4">
                No tickets currently available.
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
