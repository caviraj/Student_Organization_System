import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, AlertTriangle, ArrowRight } from 'lucide-react';
import { fundraisersApi } from '../../../api/fundraisers';
import { rupeesToPaise, formatINR } from '../../../lib/formatINR';
import { useToast } from '../../../components/ui/Toast';
import { Button } from '../../../components/ui/Button';
import { LogIncomeSchema } from '../schemas';

interface LogIncomeModalProps {
  fundraiserId: string;
  fundraiserTitle: string;
  isOpen: boolean;
  onClose: () => void;
}

export function LogIncomeModal({
  fundraiserId,
  fundraiserTitle,
  isOpen,
  onClose,
}: LogIncomeModalProps) {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const [rupeesInput, setRupeesInput] = useState('');
  const [source, setSource] = useState<'cash' | 'online' | 'cheque' | 'other'>('cash');
  const [note, setNote] = useState('');
  const [isConfirmStep, setIsConfirmStep] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const calculatedPaise = rupeesInput ? rupeesToPaise(rupeesInput) : 0;

  const logIncomeMutation = useMutation({
    mutationFn: (data: { amount: number; source: 'cash' | 'online' | 'cheque' | 'other'; note?: string }) =>
      fundraisersApi.logIncome(fundraiserId, data),

    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['fundraiser', fundraiserId] });
      queryClient.invalidateQueries({ queryKey: ['fundraisers'] });
      addToast({
        type: 'success',
        title: 'Income Logged to Ledger',
        message: `Successfully recorded ${formatINR(calculatedPaise)}. Campaign total is now ${formatINR(res.raised)}.`,
      });
      handleClose();
    },

    onError: (err: any) => {
      const msg = err?.message || 'Failed to log income to ledger';
      addToast({
        type: 'error',
        title: 'Transaction Error',
        message: msg,
      });
      setIsConfirmStep(false);
    },
  });

  const handleClose = () => {
    setRupeesInput('');
    setSource('cash');
    setNote('');
    setIsConfirmStep(false);
    setFieldErrors({});
    onClose();
  };

  const handleProceedToConfirm = (e: React.FormEvent) => {
    e.preventDefault();
    setFieldErrors({});

    const payload = {
      amount: calculatedPaise,
      source,
      note: note.trim() || undefined,
    };

    const validation = LogIncomeSchema.safeParse(payload);
    if (!validation.success) {
      const errors: Record<string, string> = {};
      validation.error.issues.forEach((issue) => {
        const field = issue.path[0]?.toString() || 'amount';
        errors[field] = issue.message;
      });
      setFieldErrors(errors);
      return;
    }

    setIsConfirmStep(true);
  };

  const handleFinalSubmit = () => {
    logIncomeMutation.mutate({
      amount: calculatedPaise,
      source,
      note: note.trim() || undefined,
    });
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="log-income-title"
    >
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
              ₹
            </div>
            <div>
              <h2 id="log-income-title" className="text-base font-bold text-slate-900">
                Log Campaign Income
              </h2>
              <p className="text-xs text-slate-500 truncate max-w-[240px]">{fundraiserTitle}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step 1: Input Form */}
        {!isConfirmStep ? (
          <form onSubmit={handleProceedToConfirm} className="p-6 space-y-4">
            {/* Amount (Rupees) */}
            <div>
              <label htmlFor="income-amount" className="block text-xs font-semibold text-slate-700 mb-1">
                Amount Raised (₹) <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 font-medium">₹</span>
                <input
                  id="income-amount"
                  type="number"
                  step="any"
                  min="1"
                  required
                  value={rupeesInput}
                  onChange={(e) => setRupeesInput(e.target.value)}
                  placeholder="500"
                  className={`w-full pl-8 pr-4 py-2 text-sm bg-white border rounded-xl focus:outline-none focus:ring-2 transition-all placeholder:text-slate-400 font-semibold ${
                    fieldErrors.amount
                      ? 'border-rose-300 focus:ring-rose-500/20 focus:border-rose-500'
                      : 'border-slate-200 focus:ring-indigo-500/20 focus:border-indigo-500'
                  }`}
                />
              </div>
              {rupeesInput && calculatedPaise > 0 && (
                <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
                  <span>Formatted: <strong className="text-slate-800">{formatINR(calculatedPaise)}</strong></span>
                  <span className="font-mono text-slate-400">({calculatedPaise} paise)</span>
                </div>
              )}
              {fieldErrors.amount && <p className="text-xs text-rose-600 mt-1">{fieldErrors.amount}</p>}
            </div>

            {/* Source */}
            <div>
              <label htmlFor="income-source" className="block text-xs font-semibold text-slate-700 mb-1">
                Payment Channel / Source <span className="text-rose-500">*</span>
              </label>
              <select
                id="income-source"
                value={source}
                onChange={(e) => setSource(e.target.value as any)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all font-medium"
              >
                <option value="cash">Cash (Stall / Bucket collection)</option>
                <option value="online">Online (UPI / QR Code / Netbanking)</option>
                <option value="cheque">Cheque (Donor / Corporate)</option>
                <option value="other">Other</option>
              </select>
            </div>

            {/* Note / Memo */}
            <div>
              <label htmlFor="income-note" className="block text-xs font-semibold text-slate-700 mb-1">
                Note / Donor Reference <span className="text-slate-400 font-normal">(optional)</span>
              </label>
              <textarea
                id="income-note"
                rows={2}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Afternoon stall cash count batch #2"
                className="w-full px-3 py-2 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:text-slate-400"
              />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
              <Button type="button" variant="outline" size="sm" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                rightIcon={<ArrowRight className="w-4 h-4" />}
                disabled={!rupeesInput || calculatedPaise <= 0}
              >
                Review & Confirm
              </Button>
            </div>
          </form>
        ) : (
          /* Step 2: Ledger Warning Confirmation Dialog */
          <div className="p-6 space-y-5 animate-in fade-in duration-150">
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed">
                <span className="font-bold block mb-1">Permanent Ledger Record Warning</span>
                Logging <strong className="font-semibold text-amber-950">{formatINR(calculatedPaise)}</strong> will permanently write an income record into the club financial ledger. This transaction is immutable and will reflect on club audit accounts.
              </div>
            </div>

            <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">Fundraiser:</span>
                <span className="font-semibold text-slate-900 truncate max-w-[200px]">{fundraiserTitle}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Amount:</span>
                <span className="font-bold text-emerald-600">{formatINR(calculatedPaise)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Payment Source:</span>
                <span className="font-semibold text-slate-900 capitalize">{source}</span>
              </div>
              {note && (
                <div className="flex justify-between pt-1 border-t border-slate-200/60">
                  <span className="text-slate-500">Note:</span>
                  <span className="text-slate-700 italic truncate max-w-[200px]">{note}</span>
                </div>
              )}
            </div>

            {/* Confirmation CTAs */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsConfirmStep(false)}
                disabled={logIncomeMutation.isPending}
              >
                Back to Edit
              </Button>
              <Button
                type="button"
                variant="primary"
                size="sm"
                isLoading={logIncomeMutation.isPending}
                onClick={handleFinalSubmit}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                Confirm & Write to Ledger
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
