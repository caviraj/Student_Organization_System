import { useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { paymentsApi } from '../../api/payments';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { useToast } from '../../components/ui/Toast';
import { formatINR } from '../../lib/formatINR';
import type { CheckoutResponse } from '../../types/api';
import { CreditCard, CheckCircle2, XCircle, ArrowLeft, ShieldCheck, AlertTriangle } from 'lucide-react';

export function Checkout() {
  const { orderId } = useParams<{ orderId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const { refreshUser } = useAuth();

  const checkoutData = (location.state as { checkoutData?: CheckoutResponse })?.checkoutData;

  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'success' | 'failed'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const confirmMutation = useMutation({
    mutationFn: (status: 'SUCCESS' | 'FAILED') => {
      const oid = orderId || checkoutData?.order_id || 'order_unknown';
      return paymentsApi.mockConfirm(oid, status === 'SUCCESS' ? 'success' : 'fail');
    },
    onSuccess: async (data, status) => {
      const isPaid =
        status === 'SUCCESS' &&
        (data.order_status === 'paid' ||
          data.payment_status === 'paid' ||
          data.order_status === 'PAID' ||
          data.payment_status === 'PAID' ||
          data.status === 'SUCCESS' ||
          data.status === 'success');

      if (isPaid) {
        setPaymentStatus('success');
        await refreshUser();
        toast.show('Payment confirmed! Membership activated successfully.', 'success');
        setTimeout(() => {
          navigate('/me');
        }, 1800);
      } else {
        setPaymentStatus('failed');
        setErrorMessage(data.message || 'Payment simulation failed.');
        toast.show('Payment failed or cancelled.', 'error');
      }
    },
    onError: (err: any) => {
      setPaymentStatus('failed');
      const msg = err.error?.message || err.message || 'Payment verification failed.';
      setErrorMessage(msg);
      toast.show(msg, 'error');
    },
  });

  const handleSimulate = (status: 'SUCCESS' | 'FAILED') => {
    confirmMutation.mutate(status);
  };

  const amountPaise = checkoutData?.amount || 50000;
  const currentOrderId = orderId || checkoutData?.order_id || 'ord_sample_987';

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate('/join')}
        className="mb-6 text-slate-400 hover:text-white"
      >
        <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to Plans
      </Button>

      <Card className="border-slate-800 bg-slate-900/90 shadow-2xl relative overflow-hidden">
        {/* Glow accent */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500" />

        <CardHeader className="text-center pb-6">
          <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CreditCard className="w-7 h-7" />
          </div>
          <CardTitle className="text-2xl font-bold text-white">Payment Checkout</CardTitle>
          <CardDescription className="text-slate-400">
            Complete your student club membership purchase
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Order Details Box */}
          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-400">Order Reference</span>
              <span className="font-mono text-xs text-slate-300 bg-slate-800 px-2 py-0.5 rounded">
                {currentOrderId}
              </span>
            </div>
            {checkoutData?.plan_name && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-400">Membership Tier</span>
                <span className="font-medium text-white">{checkoutData.plan_name}</span>
              </div>
            )}
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-400">Payment Gateway</span>
              <span className="text-slate-300 font-medium flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Cashfree / Razorpay Mock Simulator
              </span>
            </div>
            <div className="pt-3 border-t border-slate-800 flex justify-between items-baseline">
              <span className="text-base font-semibold text-white">Total Amount</span>
              <span className="text-3xl font-black text-emerald-400">
                {formatINR(amountPaise)}
              </span>
            </div>
          </div>

          {/* Status Display if completed or failed */}
          {paymentStatus === 'success' && (
            <div className="p-4 rounded-xl bg-emerald-950/50 border border-emerald-500/40 text-center animate-fade-in">
              <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
              <h4 className="font-bold text-white text-lg">Payment Successful!</h4>
              <p className="text-xs text-emerald-300 mt-1">
                Your role has been upgraded to Member and your membership card has been issued.
              </p>
              <p className="text-xs text-slate-400 mt-3">Redirecting to your Digital ID Card...</p>
            </div>
          )}

          {paymentStatus === 'failed' && (
            <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-500/40 text-center animate-fade-in">
              <XCircle className="w-10 h-10 text-rose-400 mx-auto mb-2" />
              <h4 className="font-bold text-white text-lg">Payment Simulation Failed</h4>
              <p className="text-xs text-rose-300 mt-1">
                {errorMessage || 'The simulated transaction was rejected or cancelled.'}
              </p>
            </div>
          )}

          {/* Simulation Notice */}
          <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200/90 flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <strong>Phase 1 Mock Gateway:</strong> Real bank charges are bypassed in development/testing mode. Use the buttons below to test both successful confirmation and failure handling.
            </div>
          </div>
        </CardContent>

        <CardFooter className="flex flex-col sm:flex-row gap-3 pt-2">
          <Button
            variant="success"
            size="lg"
            className="w-full sm:flex-1"
            disabled={confirmMutation.isPending || paymentStatus === 'success'}
            isLoading={confirmMutation.isPending && confirmMutation.variables === 'SUCCESS'}
            onClick={() => handleSimulate('SUCCESS')}
          >
            <ShieldCheck className="w-4 h-4 mr-2" />
            Simulate Payment Success
          </Button>

          <Button
            variant="outline"
            size="lg"
            className="w-full sm:w-auto text-rose-400 border-rose-500/30 hover:bg-rose-500/10 hover:border-rose-500/50"
            disabled={confirmMutation.isPending || paymentStatus === 'success'}
            isLoading={confirmMutation.isPending && confirmMutation.variables === 'FAILED'}
            onClick={() => handleSimulate('FAILED')}
          >
            <XCircle className="w-4 h-4 mr-2" />
            Simulate Failure
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
