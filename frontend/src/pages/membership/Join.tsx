import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { plansApi } from '../../api/plans';
import { membershipsApi } from '../../api/memberships';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { SkeletonCard } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { StatusChip } from '../../components/ui/StatusChip';
import { useToast } from '../../components/ui/Toast';
import { formatINR } from '../../lib/formatINR';
import type { MembershipPlan } from '../../types/api';
import { Check, Sparkles, ShieldCheck, Zap, ArrowRight, Clock } from 'lucide-react';

export function Join() {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);

  const { data: plans, isLoading, error, refetch } = useQuery({
    queryKey: ['membershipPlans'],
    queryFn: () => plansApi.getPlans(),
  });

  const checkoutMutation = useMutation({
    mutationFn: (planId: string) => membershipsApi.checkout(planId),
    onSuccess: (data) => {
      toast.show('Checkout initiated. Redirecting to payment simulation...', 'success');
      navigate(`/checkout/${data.order_id}`, {
        state: { checkoutData: data },
      });
    },
    onError: (err: any) => {
      const msg = err.error?.message || err.message || 'Failed to initiate checkout. Please try again.';
      toast.show(msg, 'error');
    },
  });

  const handleSelectPlan = (plan: MembershipPlan) => {
    if (!isAuthenticated) {
      toast.show('Please sign in or create an account first.', 'info');
      navigate(`/login?redirect=/join`);
      return;
    }
    setSelectedPlanId(plan.id);
    checkoutMutation.mutate(plan.id);
  };

  // Only show active plans
  const activePlans = plans?.filter((p) => p.is_active) || [];

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Header */}
      <div className="text-center max-w-3xl mx-auto mb-12">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-4">
          <Sparkles className="w-3.5 h-3.5" />
          Club Membership
        </div>
        <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
          Choose Your Membership Tier
        </h1>
        <p className="mt-3 text-slate-400 text-base sm:text-lg">
          Unlock exclusive events, voting rights, merch store discounts, and verified digital student member credentials.
        </p>

        {user?.membership && user.membership.status === 'active' && (
          <div className="mt-6 inline-flex items-center gap-3 px-4 py-2 bg-emerald-950/40 border border-emerald-500/30 rounded-xl text-sm text-emerald-300">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>You currently hold an <strong>Active Membership</strong> ({user.membership.plan_name}).</span>
            <Button size="sm" variant="ghost" className="text-emerald-400 hover:text-emerald-300 p-0 h-auto" onClick={() => navigate('/me')}>
              View Card <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        )}
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <ErrorState
          title="Could not load membership plans"
          message="We encountered an issue fetching the latest plans. Please verify your connection."
          onRetry={() => refetch()}
        />
      )}

      {/* Empty State */}
      {!isLoading && !error && activePlans.length === 0 && (
        <EmptyState
          icon={<ShieldCheck className="w-12 h-12 text-slate-500" />}
          title="No Active Membership Plans"
          description="Membership registrations are currently closed or plans are being updated. Check back shortly!"
        />
      )}

      {/* Plans Grid */}
      {!isLoading && !error && activePlans.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 items-stretch">
          {activePlans.map((plan, idx) => {
            const isPopular = idx === 0 || plan.duration_days >= 365;
            const isCurrentPlan = user?.membership?.plan_id === plan.id && user?.membership?.status === 'active';

            return (
              <Card
                key={plan.id}
                className={`relative flex flex-col transition-all duration-300 hover:border-slate-600 ${
                  isPopular
                    ? 'border-emerald-500/50 bg-slate-900/90 shadow-xl shadow-emerald-950/20 ring-1 ring-emerald-500/30'
                    : 'border-slate-800 bg-slate-900/60'
                }`}
              >
                {isPopular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 font-bold text-xs uppercase tracking-wider py-1 px-3.5 rounded-full shadow-md flex items-center gap-1">
                    <Zap className="w-3 h-3 fill-current" />
                    Recommended
                  </div>
                )}

                <CardHeader className="pb-4">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-xl font-bold text-white">{plan.name}</CardTitle>
                    {isCurrentPlan && (
                      <StatusChip status="active" label="Your Plan" />
                    )}
                  </div>
                  {plan.description && (
                    <CardDescription className="text-slate-400 mt-1 line-clamp-2">
                      {plan.description}
                    </CardDescription>
                  )}
                </CardHeader>

                <CardContent className="flex-1 space-y-6">
                  {/* Price Block */}
                  <div className="pt-2 pb-4 border-b border-slate-800">
                    <div className="flex items-baseline gap-1">
                      <span className="text-4xl font-extrabold text-white tracking-tight">
                        {formatINR(plan.price)}
                      </span>
                      <span className="text-slate-400 text-sm font-medium">
                        / {plan.duration_days} days
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-2 text-xs text-slate-500">
                      <Clock className="w-3.5 h-3.5" />
                      Valid for {Math.round(plan.duration_days / 30)} months from payment date
                    </div>
                  </div>

                  {/* Perks List */}
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                      Included Benefits:
                    </h4>
                    <ul className="space-y-2.5">
                      {plan.perks && plan.perks.length > 0 ? (
                        plan.perks.map((perk, perkIdx) => (
                          <li key={perkIdx} className="flex items-start gap-2.5 text-sm text-slate-300">
                            <span className="mt-0.5 rounded-full p-0.5 bg-emerald-500/20 text-emerald-400 shrink-0">
                              <Check className="w-3.5 h-3.5" />
                            </span>
                            <span>{perk}</span>
                          </li>
                        ))
                      ) : (
                        <li className="flex items-center gap-2 text-sm text-slate-400">
                          <Check className="w-4 h-4 text-emerald-400" />
                          <span>Standard SSA Hub member privileges</span>
                        </li>
                      )}
                    </ul>
                  </div>
                </CardContent>

                <CardFooter className="pt-4 border-t border-slate-800/60">
                  <Button
                    variant={isPopular ? 'primary' : 'outline'}
                    size="lg"
                    className="w-full"
                    disabled={checkoutMutation.isPending}
                    isLoading={checkoutMutation.isPending && selectedPlanId === plan.id}
                    onClick={() => handleSelectPlan(plan)}
                  >
                    {isCurrentPlan
                      ? 'Renew Membership'
                      : !isAuthenticated
                      ? 'Sign In to Join'
                      : 'Select Plan & Pay'}
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}

      {/* FAQ or Assurance footnote */}
      <div className="mt-16 border-t border-slate-800/80 pt-10 grid grid-cols-1 md:grid-cols-3 gap-6 text-center sm:text-left">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/60">
          <ShieldCheck className="w-6 h-6 text-emerald-400 mb-2 mx-auto sm:mx-0" />
          <h4 className="font-semibold text-white text-sm">Instant Digital Card</h4>
          <p className="text-xs text-slate-400 mt-1">Get your verified QR code member card immediately after payment simulation.</p>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/60">
          <Zap className="w-6 h-6 text-teal-400 mb-2 mx-auto sm:mx-0" />
          <h4 className="font-semibold text-white text-sm">Automated Role Upgrades</h4>
          <p className="text-xs text-slate-400 mt-1">Accounts upgrade from Guest to Member automatically upon payment confirmation.</p>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/60">
          <Sparkles className="w-6 h-6 text-cyan-400 mb-2 mx-auto sm:mx-0" />
          <h4 className="font-semibold text-white text-sm">Transparent Finances</h4>
          <p className="text-xs text-slate-400 mt-1">All membership fees directly support student workshops, hackathons, and activities.</p>
        </div>
      </div>
    </div>
  );
}
