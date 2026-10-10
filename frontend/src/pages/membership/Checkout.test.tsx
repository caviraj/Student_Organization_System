import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../context/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { Checkout } from './Checkout';
import type { PaymentIntent } from '../../types/api';

const intent = (overrides: Partial<PaymentIntent> = {}): PaymentIntent => ({
  order_id: 'ord_1',
  kind: 'membership',
  order_status: 'pending',
  amount: 90000,
  currency: 'INR',
  provider: 'razorpay',
  payment_status: 'created',
  key_id: 'rzp_test_key',
  gateway_order_id: 'order_ABC123',
  ...overrides,
});

// The checkout page used to read everything from the router state it was navigated with, so a
// reload (or a return from a bank page, which loses that state) showed a made-up ₹500 order. It
// asks the API now, which is the only thing that is still there after a reload.
const renderCheckout = (body: PaymentIntent) => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })),
  );
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={['/checkout/ord_1']}>
            <Routes>
              <Route path="/checkout/:orderId" element={<Checkout />} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
};

describe('Checkout', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('draws the order from the API when the router state is gone, and opens the real gateway', async () => {
    renderCheckout(intent());

    await waitFor(() => expect(screen.getByText('₹900')).toBeInTheDocument());
    expect(screen.getByText('ord_1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pay ₹900/i })).toBeInTheDocument();
    // No simulate buttons while a real provider is configured: that is the whole point.
    expect(screen.queryByRole('button', { name: /simulate/i })).not.toBeInTheDocument();
  });

  it('offers the simulated buttons only under the mock provider', async () => {
    renderCheckout(intent({ provider: 'mock', key_id: null, gateway_order_id: null }));

    await waitFor(() => expect(screen.getByRole('button', { name: /simulate payment success/i })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /^pay /i })).not.toBeInTheDocument();
    expect(screen.getByText('Mock gateway (development)')).toBeInTheDocument();
  });

  it('shows an already-paid order as settled without offering to charge again', async () => {
    renderCheckout(intent({ order_status: 'paid', payment_status: 'succeeded' }));

    await waitFor(() => expect(screen.getByText(/payment successful/i)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /^pay /i })).not.toBeInTheDocument();
  });
});
