import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../context/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { Join } from './Join';
import type { MembershipPlan } from '../../types/api';

const plan: MembershipPlan = {
  id: 'plan_1',
  name: 'Standard',
  description: 'One year of membership',
  price: 50000,
  duration_days: 365,
  perks: ['Event discounts'],
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

// Regression: /plans answers with a page envelope ({items,...}), not a bare array. The page used to
// receive the envelope itself and die on `plans.filter`, which rendered a blank screen.
describe('Join', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders the plans out of the page envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const isPlans = String(input).includes('/plans');
        const body = isPlans
          ? { items: [plan], total: 1, page: 1, page_size: 100 }
          : { error: { code: 'UNAUTHORIZED', message: 'Not signed in.' } };
        return new Response(JSON.stringify(body), {
          status: isPlans ? 200 : 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ToastProvider>
          <AuthProvider>
            <MemoryRouter>
              <Join />
            </MemoryRouter>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('Standard')).toBeInTheDocument());
    expect(screen.getByText('₹500')).toBeInTheDocument();
  });
});
