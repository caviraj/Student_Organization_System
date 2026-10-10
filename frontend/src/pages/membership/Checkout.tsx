import { useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { paymentsApi } from '../../api/payments';
import { openRazorpayCheckout } from '../../lib/razorpay';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { useToast } from '../../components/ui/Toast';
import { formatINR } from '../../lib/formatINR';
import { ApiError, type CheckoutResponse, type PaymentResultResponse } from '../../types/api';
import type { TicketCheckoutResponse } from '../../types/events';
import { CreditCard, CheckCircle2, XCircle, ArrowLeft, ShieldCheck, AlertTriangle, Lock } from 'lucide-react';

interface CheckoutSummaryExtras {
  items_count?: number;
  delivery_note?: string;
}

export function Checkout() {
  const { orderId } = useParams<{ orderId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const { user, refreshUser } = useAuth();

  // Descriptive extras only - the event title, the ticket tier, how many items are in the cart.
  // Never the amount and never which order this is: the router state is gone after a reload or a
  // return from a bank page, and those two have to survive that.
  const summary = (
    location.state as {
      checkoutData?: (CheckoutResponse & Partial<TicketCheckoutResponse>) & CheckoutSummaryExtras;
    } | null
  )?.checkoutData;

  const intentQuery = useQuery({
    queryKey: ['payment-intent', orderId],
    queryFn: () => paymentsApi.getIntent(orderId as string),
    enabled: Boolean(orderId),
    retry: false,
  });
  const intent = intentQuery.data;

  const isMerch = intent?.kind === 'merch';
  const isTicket = intent?.kind === 'ticket';
  // The mock provider is the only one that renders buttons which settle an order by assertion.
  const isMock = intent?.provider === 'mock';
  const alreadyPaid = intent?.order_status === 'paid';

  const [paying, setPaying] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'success' | 'failed'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const succeeded = paymentStatus === 'success' || alreadyPaid;

  const finish = async (data: PaymentResultResponse) => {
    if (data.order_status === 'paid') {
      setPaymentStatus('success');
      await refreshUser();
      const [message, destination] = isMerch
        ? ['Payment confirmed! Merchandise order placed.', '/me/orders']
        : isTicket
          ? ['Payment confirmed! Tickets issued successfully.', '/me/tickets']
          : ['Payment confirmed! Membership activated successfully.', '/me'];
      toast.show(message, 'success');
      setTimeout(() => navigate(destination), 1800);
    } else {
      setPaymentStatus('failed');
      setErrorMessage(data.message || 'The payment was not completed.');
      toast.show('Payment failed or cancelled.', 'error');
    }
  };

  const fail = (err: unknown, fallback: string) => {
    const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : fallback;
    setPaymentStatus('failed');
    setErrorMessage(message);
    toast.show(message, 'error');
  };

  const pay = async () => {
    if (!intent?.key_id || !intent.gateway_order_id) return;
    setPaying(true);
    setErrorMessage(null);
    try {
      const result = await openRazorpayCheckout(
        {
          key_id: intent.key_id,
          gateway_order_id: intent.gateway_order_id,
          amount: intent.amount,
          currency: intent.currency,
        },
        { name: user?.full_name, email: user?.email },
      );
      if (result.status === 'dismissed') {
        // The user closed the widget. Nothing was charged and the order is still payable, so this
        // is a note, not a failure.
        toast.show('Payment cancelled - nothing was charged.', 'info');
        return;
      }
      // The widget's word is not enough: the backend checks the signature before settling.
      await finish(await paymentsApi.verify(intent.order_id, result.payment));
    } catch (err) {
      fail(err, 'Payment verification failed.');
    } finally {
      setPaying(false);
    }
  };

  const simulate = async (outcome: 'success' | 'fail') => {
    if (!intent) return;
    setPaying(true);
    setErrorMessage(null);
    try {
      await finish(await paymentsApi.mockConfirm(intent.order_id, outcome));
    } catch (err) {
      fail(err, 'Payment simulation failed.');
    } finally {
      setPaying(false);
    }
  };

  const backTo = isMerch ? '/shop' : isTicket ? '/events' : '/join';
  const backLabel = isMerch ? 'Back to Shop' : isTicket ? 'Back to Events' : 'Back to Plans';

  if (intentQuery.isError) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-12">
        <Button variant="ghost" size="sm" onClick={() => navigate(backTo)} className="mb-6 text-slate-500 hover:text-slate-900">
          <ArrowLeft className="w-4 h-4 mr-1.5" /> {backLabel}
        </Button>
        <ErrorState
          title="We could not open this order"
          message={
            intentQuery.error instanceof ApiError
              ? intentQuery.error.message
              : 'The order could not be loaded. Please try again.'
          }
          onRetry={() => intentQuery.refetch()}
        />
      </div>
    );
  }

  if (!intent) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-12 space-y-4">
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-96 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <Button variant="ghost" size="sm" onClick={() => navigate(backTo)} className="mb-6 text-slate-500 hover:text-slate-900">
        <ArrowLeft className="w-4 h-4 mr-1.5" /> {backLabel}
      </Button>

      <Card className="border-slate-200 bg-white shadow-2xl relative overflow-hidden">
        {/* Glow accent */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500" />

        <CardHeader className="text-center pb-6">
          <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
            <CreditCard className="w-7 h-7" />
          </div>
          <CardTitle className="text-2xl font-bold text-slate-900">
            {isMerch ? 'Merchandise Checkout' : isTicket ? 'Ticket Checkout' : 'Payment Checkout'}
          </CardTitle>
          <CardDescription className="text-slate-500">
            {isMerch
              ? 'Complete your official club merchandise payment'
              : isTicket
              ? 'Complete your event admission ticket order'
              : 'Complete your student club membership purchase'}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Order Details Box */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-500">Order Reference</span>
              <span className="font-mono text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                {intent.order_id}
              </span>
            </div>

            {isMerch && (
              <>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-slate-500">Category</span>
                  <span className="font-medium text-slate-900">Official Club Merch</span>
                </div>
                {summary?.items_count ? (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-500">Items Ordered</span>
                    <span className="font-medium text-slate-900">
                      {summary.items_count} item{summary.items_count > 1 ? 's' : ''}
                    </span>
                  </div>
                ) : null}
                {summary?.delivery_note ? (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-500">Fulfillment Note</span>
                    <span className="font-medium text-slate-600 truncate max-w-[240px] text-right">
                      {summary.delivery_note}
                    </span>
                  </div>
                ) : null}
              </>
            )}

            {isTicket && summary?.event_title && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Event</span>
                <span className="font-medium text-slate-900 truncate max-w-[260px] text-right">{summary.event_title}</span>
              </div>
            )}

            {isTicket && summary?.ticket_type_name && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Ticket Tier</span>
                <span className="font-medium text-slate-900">{summary.ticket_type_name}</span>
              </div>
            )}

            {isTicket && typeof summary?.quantity === 'number' && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Quantity</span>
                <span className="font-medium text-slate-900">
                  {summary.quantity} ticket{summary.quantity > 1 ? 's' : ''}
                </span>
              </div>
            )}

            {isTicket && typeof summary?.unit_price === 'number' && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Price per ticket</span>
                <span className="font-medium text-slate-600">{formatINR(summary.unit_price)}</span>
              </div>
            )}

            {!isTicket && !isMerch && (summary as CheckoutResponse | undefined)?.plan_name && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-500">Membership Tier</span>
                <span className="font-medium text-slate-900">{(summary as CheckoutResponse).plan_name}</span>
              </div>
            )}

            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-500">Payment Gateway</span>
              <span className="text-slate-600 font-medium flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                {isMock ? 'Mock gateway (development)' : 'Razorpay'}
              </span>
            </div>
            <div className="pt-3 border-t border-slate-200 flex justify-between items-baseline">
              <span className="text-base font-semibold text-slate-900">Total Amount</span>
              <span className="text-3xl font-black text-emerald-600">{formatINR(intent.amount)}</span>
            </div>
          </div>

          {/* Status Display if completed or failed */}
          {succeeded && (
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-center animate-fade-in">
              <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto mb-2" />
              <h4 className="font-bold text-slate-900 text-lg">Payment Successful!</h4>
              <p className="text-xs text-emerald-700 mt-1">
                {isTicket
                  ? 'Your event tickets have been issued and QR access passes generated.'
                  : isMerch
                  ? 'Your merchandise order has been placed and the reserved stock is yours.'
                  : 'Your role has been upgraded to Member and your membership card has been issued.'}
              </p>
              <p className="text-xs text-slate-500 mt-3">
                {isMerch
                  ? 'Redirecting to My Orders...'
                  : isTicket
                  ? 'Redirecting to My Tickets...'
                  : 'Redirecting to your Digital ID Card...'}
              </p>
            </div>
          )}

          {!succeeded && paymentStatus === 'failed' && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-center animate-fade-in">
              <XCircle className="w-10 h-10 text-rose-600 mx-auto mb-2" />
              <h4 className="font-bold text-slate-900 text-lg">Payment Failed</h4>
              <p className="text-xs text-rose-700 mt-1">
                {errorMessage || 'The transaction was rejected or cancelled.'}
              </p>
            </div>
          )}

          {isMock ? (
            <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-700 flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <strong>Mock gateway:</strong> this deployment has no payment provider configured, so no money
                moves. The buttons below settle the order directly.
              </div>
            </div>
          ) : (
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 flex items-start gap-2.5">
              <Lock className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                Payment is processed by Razorpay. Your card and UPI details go to them and never touch this
                site.
              </div>
            </div>
          )}
        </CardContent>

        {!succeeded && (
          <CardFooter className="flex flex-col sm:flex-row gap-3 pt-2">
            {isMock ? (
              <>
                <Button
                  variant="success"
                  size="lg"
                  className="w-full sm:flex-1"
                  disabled={paying}
                  isLoading={paying}
                  onClick={() => simulate('success')}
                >
                  <ShieldCheck className="w-4 h-4 mr-2" />
                  Simulate Payment Success
                </Button>

                <Button
                  variant="outline"
                  size="lg"
                  className="w-full sm:w-auto text-rose-600 border-rose-300 hover:bg-rose-50 hover:border-rose-400"
                  disabled={paying}
                  onClick={() => simulate('fail')}
                >
                  <XCircle className="w-4 h-4 mr-2" />
                  Simulate Failure
                </Button>
              </>
            ) : (
              <Button
                variant="success"
                size="lg"
                className="w-full"
                disabled={paying}
                isLoading={paying}
                onClick={pay}
              >
                <ShieldCheck className="w-4 h-4 mr-2" />
                Pay {formatINR(intent.amount)}
              </Button>
            )}
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
