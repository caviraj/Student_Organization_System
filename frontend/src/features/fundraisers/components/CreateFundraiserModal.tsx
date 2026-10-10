import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { fundraisersApi } from '../../../api/fundraisers';
import { formatINR, rupeesToPaise } from '../../../lib/formatINR';
import { getLocalDateString } from '../utils/taskUtils';

interface CreateFundraiserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (id: string) => void;
}

export const CreateFundraiserModal: React.FC<CreateFundraiserModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const queryClient = useQueryClient();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [goalRupees, setGoalRupees] = useState('');
  const [eventDate, setEventDate] = useState(getLocalDateString());
  const [status, setStatus] = useState<'planning' | 'active'>('planning');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const goalPaise = React.useMemo(() => {
    const val = parseFloat(goalRupees);
    return isNaN(val) || val <= 0 ? 0 : rupeesToPaise(val);
  }, [goalRupees]);

  const createMutation = useMutation({
    mutationFn: fundraisersApi.createFundraiser,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['fundraisers'] });
      resetForm();
      onClose();
      if (onSuccess) onSuccess(data.id);
    },
    onError: (err: any) => {
      setErrorMsg(err.message || 'Failed to create fundraiser. Please try again.');
    },
  });

  const resetForm = () => {
    setTitle('');
    setDescription('');
    setGoalRupees('');
    setEventDate(getLocalDateString());
    setStatus('planning');
    setErrorMsg(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!title.trim() || title.trim().length < 3) {
      setErrorMsg('Fundraiser title must be at least 3 characters.');
      return;
    }

    if (goalPaise <= 0) {
      setErrorMsg('Goal amount must be greater than ₹0.');
      return;
    }

    createMutation.mutate({
      title: title.trim(),
      description: description.trim(),
      goal_amount: goalPaise,
      event_date: eventDate,
      status,
    });
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-fundraiser-title"
    >
      <div className="bg-white rounded-2xl max-w-lg w-full p-6 sm:p-8 shadow-2xl border border-slate-100 transition-all">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div>
              <h2 id="create-fundraiser-title" className="text-xl font-bold text-slate-900">
                New Fundraiser Campaign
              </h2>
              <p className="text-xs text-slate-500">Plan and track fundraising initiatives</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              resetForm();
              onClose();
            }}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
            aria-label="Close modal"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {errorMsg && (
          <div className="mb-5 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm flex items-center gap-2">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="fundraiser-title" className="block text-sm font-semibold text-slate-700 mb-1">
              Campaign Title *
            </label>
            <input
              id="fundraiser-title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Annual Charity Bake Sale"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-slate-900 text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
            />
          </div>

          <div>
            <label htmlFor="fundraiser-desc" className="block text-sm font-semibold text-slate-700 mb-1">
              Description
            </label>
            <textarea
              id="fundraiser-desc"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explain the purpose, team goals, or beneficiary details..."
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-slate-900 text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors resize-none"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="fundraiser-goal" className="block text-sm font-semibold text-slate-700 mb-1">
                Goal Amount (₹) *
              </label>
              <div className="relative">
                <span className="absolute left-3.5 top-2.5 text-slate-400 font-medium text-sm">₹</span>
                <input
                  id="fundraiser-goal"
                  type="number"
                  min="1"
                  step="any"
                  required
                  value={goalRupees}
                  onChange={(e) => setGoalRupees(e.target.value)}
                  placeholder="15,000"
                  className="w-full pl-8 pr-3.5 py-2.5 rounded-xl border border-slate-300 text-slate-900 text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                {goalPaise > 0 ? `Target: ${formatINR(goalPaise)}` : 'Enter amount in Indian Rupees'}
              </p>
            </div>

            <div>
              <label htmlFor="fundraiser-date" className="block text-sm font-semibold text-slate-700 mb-1">
                Target Date *
              </label>
              <input
                id="fundraiser-date"
                type="date"
                required
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-slate-900 text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
              />
            </div>
          </div>

          <div>
            <label htmlFor="fundraiser-status" className="block text-sm font-semibold text-slate-700 mb-1">
              Initial Status
            </label>
            <select
              id="fundraiser-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as 'planning' | 'active')}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-slate-900 text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
            >
              <option value="planning">Planning (Draft tasks & logistics)</option>
              <option value="active">Active (Currently collecting funds)</option>
            </select>
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={() => {
                resetForm();
                onClose();
              }}
              className="px-4 py-2.5 rounded-xl border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold shadow-xs disabled:opacity-50 flex items-center gap-2 transition-colors"
            >
              {createMutation.isPending ? (
                <>
                  <svg className="w-4 h-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Creating...</span>
                </>
              ) : (
                <span>Create Campaign</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
