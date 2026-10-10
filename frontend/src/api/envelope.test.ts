import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { authApi } from './auth';
import { plansApi } from './plans';
import { shopApi } from './shop';
import { ticketsApi } from './tickets';
import { fundraisersApi } from './fundraisers';

// The real API wraps every list in a page envelope. These functions hand callers a plain array,
// which is what a page like Join assumes. A bare array from the API used to reach the UI and
// crash it on `plans.filter`, so pin the unwrapping down here.
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 100 });

const stubFetch = (body: unknown, status = 200) => {
  const fn = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
};

describe('list endpoints unwrap the page envelope', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('getPlans returns the items array, not the envelope', async () => {
    stubFetch(page([{ id: 'plan_1', is_active: true }]));
    await expect(plansApi.getPlans()).resolves.toEqual([{ id: 'plan_1', is_active: true }]);
  });

  it('getProducts returns the items array', async () => {
    stubFetch(page([{ id: 'prod_1' }]));
    await expect(shopApi.getProducts()).resolves.toEqual([{ id: 'prod_1' }]);
  });

  it('getMyOrders returns the items array', async () => {
    stubFetch(page([{ id: 'order_1' }]));
    await expect(shopApi.getMyOrders()).resolves.toEqual([{ id: 'order_1' }]);
  });

  it('getMyTickets returns the items array', async () => {
    stubFetch(page([{ id: 'ticket_1' }]));
    await expect(ticketsApi.getMyTickets()).resolves.toEqual([{ id: 'ticket_1' }]);
  });

  it('getMyTasks returns the items array', async () => {
    stubFetch(page([{ id: 'task_1' }]));
    await expect(fundraisersApi.getMyTasks()).resolves.toEqual([{ id: 'task_1' }]);
  });

  it('getFundraiserTasks reads the board out of items', async () => {
    stubFetch({ items: [{ id: 'task_2' }], columns: {}, counts: {} });
    await expect(fundraisersApi.getFundraiserTasks('fr_1')).resolves.toEqual([{ id: 'task_2' }]);
  });

  it('asks for the maximum page size so a list is not silently truncated at 20', async () => {
    const fetchFn = stubFetch(page([]));
    await plansApi.getPlans();
    expect(String(fetchFn.mock.calls[0][0])).toContain('page_size=100');
  });
});

describe('the 401 handler distinguishes a dead session from a failed login', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('keeps an existing session when an unauthenticated login attempt 401s', async () => {
    localStorage.setItem('ssa_token', 'existing-session');
    stubFetch({ error: { code: 'INVALID_CREDENTIALS', message: 'Wrong password.' } }, 401);

    await expect(authApi.login({ email: 'a@b.test', password: 'nope' })).rejects.toThrow();

    expect(localStorage.getItem('ssa_token')).toBe('existing-session');
  });

  it('clears the session when a request we sent a token with 401s', async () => {
    localStorage.setItem('ssa_token', 'expired-session');
    stubFetch({ error: { code: 'UNAUTHORIZED', message: 'Token expired.' } }, 401);

    await expect(plansApi.getPlans()).rejects.toThrow();

    expect(localStorage.getItem('ssa_token')).toBeNull();
  });
});
