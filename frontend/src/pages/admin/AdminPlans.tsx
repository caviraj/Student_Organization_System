import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { plansApi } from '../../api/plans';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { StatusChip } from '../../components/ui/StatusChip';
import { SkeletonCard } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { useToast } from '../../components/ui/Toast';
import { formatINR } from '../../lib/formatINR';
import type { MembershipPlan } from '../../types/api';
import { ShieldCheck, Plus, Edit2, Layers, Check, Clock } from 'lucide-react';

export function AdminPlans() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editPlan, setEditPlan] = useState<MembershipPlan | null>(null);

  // Form states for Create
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [priceRupees, setPriceRupees] = useState('500');
  const [durationDays, setDurationDays] = useState('365');
  const [perksText, setPerksText] = useState('Event access\nVoting rights\nMember badge');
  const [formError, setFormError] = useState<string | null>(null);

  const { data: plans, isLoading, error, refetch } = useQuery({
    queryKey: ['adminPlans'],
    queryFn: () => plansApi.getPlans(true),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const parsedRupees = parseFloat(priceRupees);
      if (isNaN(parsedRupees) || parsedRupees <= 0) {
        throw new Error('Price must be greater than zero');
      }
      const pricePaise = Math.round(parsedRupees * 100);
      const days = parseInt(durationDays, 10);
      if (isNaN(days) || days <= 0) {
        throw new Error('Duration days must be a positive integer');
      }

      const perks = perksText
        .split('\n')
        .map((p) => p.trim())
        .filter(Boolean);

      return plansApi.createPlan({
        name: name.trim(),
        description: description.trim(),
        price: pricePaise,
        duration_days: days,
        perks,
      });
    },
    onSuccess: () => {
      toast.show('Plan created successfully!', 'success');
      setCreateModalOpen(false);
      resetCreateForm();
      queryClient.invalidateQueries({ queryKey: ['adminPlans'] });
      queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
    },
    onError: (err: any) => {
      if (err.error?.code === 'PLAN_NAME_TAKEN') {
        setFormError('A membership plan with this name already exists.');
      } else {
        setFormError(err.error?.message || err.message || 'Failed to create plan.');
      }
    },
  });

  const updateMutation = useMutation({
    mutationFn: (updated: { id: string; data: Partial<MembershipPlan> }) =>
      plansApi.updatePlan(updated.id, {
        name: updated.data.name,
        description: updated.data.description,
        price: updated.data.price,
        duration_days: updated.data.duration_days,
        perks: updated.data.perks,
        is_active: updated.data.is_active,
      }),
    onSuccess: () => {
      toast.show('Plan updated successfully!', 'success');
      setEditPlan(null);
      queryClient.invalidateQueries({ queryKey: ['adminPlans'] });
      queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
    },
    onError: (err: any) => {
      toast.show(err.error?.message || err.message || 'Failed to update plan.', 'error');
    },
  });

  const resetCreateForm = () => {
    setName('');
    setDescription('');
    setPriceRupees('500');
    setDurationDays('365');
    setPerksText('Event access\nVoting rights\nMember badge');
    setFormError(null);
  };

  const handleOpenEdit = (plan: MembershipPlan) => {
    setEditPlan(plan);
  };

  const handleTogglePlanActive = (plan: MembershipPlan) => {
    updateMutation.mutate({
      id: plan.id,
      data: { is_active: !plan.is_active },
    });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-2">
            <Layers className="w-3.5 h-3.5" />
            Membership Configuration
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Membership Plans
          </h1>
          <p className="text-sm text-slate-400">
            Configure pricing tiers, duration, perks, and active enrollment status.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            onClick={() => {
              resetCreateForm();
              setCreateModalOpen(true);
            }}
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Create New Plan
          </Button>
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <ErrorState
          title="Could not load membership plans"
          message="Failed to fetch plans from server."
          onRetry={() => refetch()}
        />
      )}

      {/* Empty State */}
      {!isLoading && !error && (!plans || plans.length === 0) && (
        <EmptyState
          icon={<ShieldCheck className="w-12 h-12 text-slate-500" />}
          title="No Membership Plans Configured"
          description="Create your first membership plan to allow students to join."
          actionLabel="Create Plan"
          onAction={() => setCreateModalOpen(true)}
        />
      )}

      {/* Plans List Cards */}
      {!isLoading && !error && plans && plans.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {plans.map((plan) => (
            <Card
              key={plan.id}
              className={`flex flex-col border-slate-800 bg-slate-900/80 transition-all ${
                plan.is_active ? 'border-slate-700' : 'opacity-60 border-dashed'
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-xl font-bold text-white">{plan.name}</CardTitle>
                    <CardDescription className="text-xs text-slate-400 mt-1 line-clamp-2">
                      {plan.description || 'No description provided.'}
                    </CardDescription>
                  </div>
                  <StatusChip status={plan.is_active ? 'active' : 'none'} label={plan.is_active ? 'Active' : 'Archived'} />
                </div>
              </CardHeader>

              <CardContent className="flex-1 space-y-4">
                <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80 flex items-baseline justify-between">
                  <span className="text-2xl font-black text-white">
                    {formatINR(plan.price)}
                  </span>
                  <span className="text-xs text-slate-400 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    {plan.duration_days} days
                  </span>
                </div>

                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    Included Perks:
                  </h4>
                  <ul className="space-y-1.5 text-xs text-slate-300">
                    {plan.perks?.map((perk, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span className="truncate">{perk}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </CardContent>

              <div className="p-4 pt-2 border-t border-slate-800/80 flex items-center justify-between gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleTogglePlanActive(plan)}
                  isLoading={updateMutation.isPending && updateMutation.variables?.id === plan.id}
                >
                  {plan.is_active ? 'Archive' : 'Activate'}
                </Button>

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleOpenEdit(plan)}
                >
                  <Edit2 className="w-3.5 h-3.5 mr-1" />
                  Edit Plan
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Plan Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Create Membership Plan"
        description="Add a new subscription tier with custom duration and pricing."
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          className="space-y-4"
        >
          {formError && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300">
              {formError}
            </div>
          )}

          <Input
            label="Plan Name"
            placeholder="e.g. Annual Student Pass"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setFormError(null);
            }}
            required
          />

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Description
            </label>
            <textarea
              className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 min-h-[70px]"
              placeholder="Brief description of the tier..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Price (in Rupees ₹)"
              type="number"
              placeholder="500"
              value={priceRupees}
              onChange={(e) => setPriceRupees(e.target.value)}
              hint={`Total: ${formatINR(Math.round((parseFloat(priceRupees) || 0) * 100))}`}
              required
            />

            <Input
              label="Duration (in Days)"
              type="number"
              placeholder="365"
              value={durationDays}
              onChange={(e) => setDurationDays(e.target.value)}
              hint="e.g. 365 = 1 year"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Perks (one per line)
            </label>
            <textarea
              className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 min-h-[90px] font-mono text-xs"
              value={perksText}
              onChange={(e) => setPerksText(e.target.value)}
              placeholder="Event passes&#10;Discounts&#10;Voting access"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreateModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={createMutation.isPending}
            >
              Save & Publish Plan
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Plan Modal */}
      {editPlan && (
        <Modal
          isOpen={!!editPlan}
          onClose={() => setEditPlan(null)}
          title={`Edit Plan: ${editPlan.name}`}
          description="Update plan perks or description."
        >
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Description
              </label>
              <textarea
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 min-h-[70px]"
                value={editPlan.description || ''}
                onChange={(e) =>
                  setEditPlan({ ...editPlan, description: e.target.value })
                }
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Perks (comma-separated)
              </label>
              <textarea
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 min-h-[80px]"
                value={editPlan.perks.join(', ')}
                onChange={(e) =>
                  setEditPlan({
                    ...editPlan,
                    perks: e.target.value.split(',').map((p) => p.trim()),
                  })
                }
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
              <Button variant="ghost" onClick={() => setEditPlan(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                isLoading={updateMutation.isPending}
                onClick={() =>
                  updateMutation.mutate({
                    id: editPlan.id,
                    data: {
                      description: editPlan.description,
                      perks: editPlan.perks,
                    },
                  })
                }
              >
                Save Changes
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
