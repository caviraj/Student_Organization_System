import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { plansApi, planPerks } from '../../api/plans';
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
  const [durationMonths, setDurationMonths] = useState('12');
  const [ticketDiscount, setTicketDiscount] = useState('0');
  const [merchDiscount, setMerchDiscount] = useState('0');
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
      const months = parseInt(durationMonths, 10);
      if (isNaN(months) || months <= 0) {
        throw new Error('Duration must be a positive number of months');
      }

      return plansApi.createPlan({
        name: name.trim(),
        description: description.trim(),
        price: pricePaise,
        duration_months: months,
        ticket_discount_pct: parseInt(ticketDiscount, 10) || 0,
        merch_discount_pct: parseInt(merchDiscount, 10) || 0,
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
        duration_months: updated.data.duration_months,
        ticket_discount_pct: updated.data.ticket_discount_pct,
        merch_discount_pct: updated.data.merch_discount_pct,
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
    setDurationMonths('12');
    setTicketDiscount('0');
    setMerchDiscount('0');
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
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 mb-2">
            <Layers className="w-3.5 h-3.5" />
            Membership Configuration
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
            Membership Plans
          </h1>
          <p className="text-sm text-slate-600">
            Configure pricing tiers, duration, member discounts, and active enrollment status.
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
          icon={<ShieldCheck className="w-12 h-12 text-slate-400" />}
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
              className={`flex flex-col transition-all ${
                plan.is_active ? '' : 'opacity-60 border-dashed'
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-xl font-bold">{plan.name}</CardTitle>
                    <CardDescription className="text-xs mt-1 line-clamp-2">
                      {plan.description || 'No description provided.'}
                    </CardDescription>
                  </div>
                  <StatusChip status={plan.is_active ? 'active' : 'none'} label={plan.is_active ? 'Active' : 'Archived'} />
                </div>
              </CardHeader>

              <CardContent className="flex-1 space-y-4">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-baseline justify-between">
                  <span className="text-2xl font-black text-slate-900">
                    {formatINR(plan.price)}
                  </span>
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    {plan.duration_months} month{plan.duration_months > 1 ? 's' : ''}
                  </span>
                </div>

                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                    Included Perks:
                  </h4>
                  <ul className="space-y-1.5 text-xs text-slate-600">
                    {planPerks(plan).map((perk) => (
                      <li key={perk} className="flex items-center gap-2">
                        <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span className="truncate">{perk}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </CardContent>

              <div className="p-4 pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
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
        description="Add a new subscription tier with custom duration, pricing and member discounts."
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          className="space-y-4"
        >
          {formError && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
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
            <label htmlFor="plan-description" className="block text-sm font-medium text-slate-700 mb-1.5">
              Description
            </label>
            <textarea
              id="plan-description"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-300 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-600 min-h-[70px]"
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
              label="Duration (in Months)"
              type="number"
              min={1}
              max={60}
              placeholder="12"
              value={durationMonths}
              onChange={(e) => setDurationMonths(e.target.value)}
              hint="1-60 months; e.g. 12 = 1 year"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Ticket Discount (%)"
              type="number"
              min={0}
              max={100}
              placeholder="0"
              value={ticketDiscount}
              onChange={(e) => setTicketDiscount(e.target.value)}
              hint="Applied at event checkout"
            />

            <Input
              label="Merch Discount (%)"
              type="number"
              min={0}
              max={100}
              placeholder="0"
              value={merchDiscount}
              onChange={(e) => setMerchDiscount(e.target.value)}
              hint="Applied at shop checkout"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
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
          description="Update the plan's description, duration and member discounts."
        >
          <div className="space-y-4">
            <div>
              <label htmlFor="edit-plan-description" className="block text-sm font-medium text-slate-700 mb-1.5">
                Description
              </label>
              <textarea
                id="edit-plan-description"
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-600 min-h-[70px]"
                value={editPlan.description || ''}
                onChange={(e) =>
                  setEditPlan({ ...editPlan, description: e.target.value })
                }
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Input
                label="Months"
                type="number"
                min={1}
                value={String(editPlan.duration_months)}
                onChange={(e) =>
                  setEditPlan({ ...editPlan, duration_months: parseInt(e.target.value, 10) || 0 })
                }
                required
              />
              <Input
                label="Ticket %"
                type="number"
                min={0}
                max={100}
                value={String(editPlan.ticket_discount_pct)}
                onChange={(e) =>
                  setEditPlan({ ...editPlan, ticket_discount_pct: parseInt(e.target.value, 10) || 0 })
                }
              />
              <Input
                label="Merch %"
                type="number"
                min={0}
                max={100}
                value={String(editPlan.merch_discount_pct)}
                onChange={(e) =>
                  setEditPlan({ ...editPlan, merch_discount_pct: parseInt(e.target.value, 10) || 0 })
                }
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
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
                      duration_months: editPlan.duration_months,
                      ticket_discount_pct: editPlan.ticket_discount_pct,
                      merch_discount_pct: editPlan.merch_discount_pct,
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
