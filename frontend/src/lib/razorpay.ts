/**
 * Razorpay Checkout, loaded on demand.
 *
 * The script comes from Razorpay's CDN rather than npm: it is the only supported way to open the
 * widget, and a bundled copy would be a stale one the day the gateway changes. It is fetched the
 * first time someone actually pays, so a visitor reading the events page never downloads it.
 */

const SCRIPT_SRC = 'https://checkout.razorpay.com/v1/checkout.js';

export interface RazorpaySuccess {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

interface RazorpayOptions {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description?: string;
  prefill?: { name?: string; email?: string };
  theme?: { color?: string };
  handler: (response: RazorpaySuccess) => void;
  modal?: { ondismiss?: () => void };
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => { open: () => void };
  }
}

/** The user closed the widget. A normal thing to do, not an error - the caller shows a quieter
 * message than a failed payment gets. */
export type CheckoutResult = { status: 'paid'; payment: RazorpaySuccess } | { status: 'dismissed' };

let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  loading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = SCRIPT_SRC;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null; // a failed load must be retryable without a reload
      reject(new Error('Could not reach the payment gateway. Check your connection and try again.'));
    };
    document.head.appendChild(script);
  });
  return loading;
}

export interface CheckoutIntent {
  key_id: string;
  gateway_order_id: string;
  amount: number;
  currency: string;
}

export async function openRazorpayCheckout(
  intent: CheckoutIntent,
  prefill: { name?: string; email?: string },
): Promise<CheckoutResult> {
  await loadScript();
  if (!window.Razorpay) throw new Error('The payment gateway did not load. Reload the page and try again.');

  return new Promise<CheckoutResult>((resolve) => {
    const checkout = new window.Razorpay!({
      key: intent.key_id,
      order_id: intent.gateway_order_id,
      amount: intent.amount, // integer paise, straight from the backend
      currency: intent.currency,
      name: 'SSA Hub',
      description: 'Student club payment',
      prefill,
      theme: { color: '#4338CA' },
      // The widget reports a payment, but only the backend can believe it: it verifies the
      // signature against the key secret before anything is settled.
      handler: (payment) => resolve({ status: 'paid', payment }),
      modal: { ondismiss: () => resolve({ status: 'dismissed' }) },
    });
    checkout.open();
  });
}
