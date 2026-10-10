import { http, HttpResponse } from 'msw';
import { mockPlans, mockUsers, mockMemberships, mockRenewalsDue } from './data';
import type { UserMe, MembershipPlan } from '../types/api';

let activeUserEmail = 'member@ssa.org';
const plansState: MembershipPlan[] = [...mockPlans];

export const handlers = [
  // 1. Auth Register
  http.post('*/api/v1/auth/register', async ({ request }) => {
    const body = (await request.json()) as {
      email: string;
      password: string;
      full_name: string;
      phone?: string;
      department?: string;
      year?: number;
    };

    if (mockUsers[body.email]) {
      return HttpResponse.json(
        {
          error: {
            code: 'EMAIL_ALREADY_REGISTERED',
            message: 'An account with this email address already exists.',
          },
        },
        { status: 409 }
      );
    }

    const newUser: UserMe = {
      id: `usr_${Math.random().toString(36).substring(2, 9)}`,
      email: body.email,
      full_name: body.full_name,
      phone: body.phone,
      department: body.department,
      year: body.year,
      role: 'guest',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      membership: null,
    };

    mockUsers[body.email] = newUser;
    activeUserEmail = body.email;

    return HttpResponse.json({
      access_token: `mock_jwt_${newUser.id}`,
      token_type: 'bearer',
      user: newUser,
    });
  }),

  // 2. Auth Login
  http.post('*/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };

    const user = mockUsers[body.email];
    if (!user || body.password !== 'Passw0rd!') {
      // Allow Passw0rd! as the default seed password or any valid password for test users
      if (!user) {
        return HttpResponse.json(
          {
            error: {
              code: 'INVALID_CREDENTIALS',
              message: 'Invalid email or password.',
            },
          },
          { status: 401 }
        );
      }
    }

    activeUserEmail = user.email;

    return HttpResponse.json({
      access_token: `mock_jwt_${user.id}`,
      token_type: 'bearer',
      user,
    });
  }),

  // 3. Auth Me
  http.get('*/api/v1/auth/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    if (!authHeader && !activeUserEmail) {
      return HttpResponse.json(
        {
          error: {
            code: 'UNAUTHORIZED',
            message: 'Authentication token missing or invalid.',
          },
        },
        { status: 401 }
      );
    }

    const user = mockUsers[activeUserEmail] || mockUsers['member@ssa.org'];
    return HttpResponse.json(user);
  }),

  // 4. Get Plans
  http.get('*/api/v1/plans', () => {
    return HttpResponse.json(plansState);
  }),

  // 5. Create Plan (Admin)
  http.post('*/api/v1/plans', async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      description?: string;
      price: number;
      duration_days: number;
      perks: string[];
      is_active?: boolean;
    };

    if (plansState.some((p) => p.name.toLowerCase() === body.name.toLowerCase())) {
      return HttpResponse.json(
        {
          error: {
            code: 'PLAN_NAME_TAKEN',
            message: `A membership plan named "${body.name}" already exists.`,
          },
        },
        { status: 409 }
      );
    }

    const newPlan: MembershipPlan = {
      id: `plan_${Math.random().toString(36).substring(2, 9)}`,
      name: body.name,
      description: body.description || null,
      price: body.price,
      duration_days: body.duration_days,
      perks: body.perks || [],
      is_active: body.is_active ?? true,
      created_at: new Date().toISOString(),
    };

    plansState.push(newPlan);
    return HttpResponse.json(newPlan, { status: 201 });
  }),

  // 6. Update Plan (Admin)
  http.patch('*/api/v1/plans/:planId', async ({ params, request }) => {
    const { planId } = params;
    const body = (await request.json()) as Partial<MembershipPlan>;

    const idx = plansState.findIndex((p) => p.id === planId);
    if (idx === -1) {
      return HttpResponse.json(
        {
          error: {
            code: 'PLAN_NOT_FOUND',
            message: 'Membership plan not found.',
          },
        },
        { status: 404 }
      );
    }

    if (
      body.name &&
      plansState.some(
        (p) => p.id !== planId && p.name.toLowerCase() === body.name?.toLowerCase()
      )
    ) {
      return HttpResponse.json(
        {
          error: {
            code: 'PLAN_NAME_TAKEN',
            message: `A membership plan named "${body.name}" already exists.`,
          },
        },
        { status: 409 }
      );
    }

    plansState[idx] = {
      ...plansState[idx],
      ...body,
    };

    return HttpResponse.json(plansState[idx]);
  }),

  // 7. Checkout Membership
  http.post('*/api/v1/memberships/checkout', async ({ request }) => {
    const body = (await request.json()) as { plan_id: string };
    const plan = plansState.find((p) => p.id === body.plan_id);

    if (!plan) {
      return HttpResponse.json(
        {
          error: {
            code: 'PLAN_NOT_FOUND',
            message: 'The requested plan does not exist or has been archived.',
          },
        },
        { status: 404 }
      );
    }

    const orderId = `ord_${Math.random().toString(36).substring(2, 10)}`;
    const paymentId = `pay_${Math.random().toString(36).substring(2, 10)}`;

    return HttpResponse.json({
      order_id: orderId,
      payment_id: paymentId,
      amount: plan.price,
      provider: 'mock_cashfree',
      status: 'pending',
    });
  }),

  // 8. Mock Payment Confirm
  http.post('*/api/v1/payments/:orderId/mock-confirm', async ({ params, request }) => {
    const { orderId } = params;
    const body = (await request.json()) as { outcome: 'success' | 'fail' };

    if (body.outcome === 'fail') {
      return HttpResponse.json({
        order_id: String(orderId),
        payment_id: `pay_${Math.random().toString(36).substring(2, 10)}`,
        order_status: 'failed',
        payment_status: 'failed',
        provider_ref: `txn_fail_${Date.now()}`,
        membership: null,
      });
    }

    // Success flow
    const endDate = new Date();
    endDate.setDate(endDate.getDate() + 365);

    const currentUser = mockUsers[activeUserEmail] || mockUsers['member@ssa.org'];
    currentUser.role = 'member';
    currentUser.membership = {
      status: 'active',
      plan_name: 'Standard Scholar',
      end_date: endDate.toISOString(),
      days_left: 365,
    };

    return HttpResponse.json({
      order_id: String(orderId),
      payment_id: `pay_${Math.random().toString(36).substring(2, 10)}`,
      order_status: 'completed',
      payment_status: 'succeeded',
      provider_ref: `txn_mock_${Date.now()}`,
      membership: {
        id: `mem_${Math.random().toString(36).substring(2, 9)}`,
        status: 'active',
        end_date: endDate.toISOString(),
      },
    });
  }),

  // 9. Member Me Card
  http.get('*/api/v1/members/me/card', () => {
    const user = mockUsers[activeUserEmail] || mockUsers['member@ssa.org'];
    const isActive = user.membership?.status === 'active';

    return HttpResponse.json({
      member_code: `SSA-2026-${user.id.substring(4, 9).toUpperCase()}`,
      full_name: user.full_name,
      status: isActive ? 'active' : 'expired',
      valid_until: user.membership?.end_date || new Date().toISOString(),
    });
  }),

  // 10. Verify Member (Staff Scanner & Query)
  http.get('*/api/v1/members/verify', ({ request }) => {
    const url = new URL(request.url);
    const code = url.searchParams.get('code');
    const q = url.searchParams.get('q');

    if (!code && !q) {
      return HttpResponse.json(
        {
          error: {
            code: 'MISSING_QUERY',
            message: 'Provide either ?code= or ?q= parameter to verify a member.',
          },
        },
        { status: 400 }
      );
    }

    // Ambiguous test condition
    if (q && q.toLowerCase() === 'ambiguous') {
      return HttpResponse.json(
        {
          error: {
            code: 'AMBIGUOUS_QUERY',
            message: 'Multiple members match this query. Please scan barcode or enter exact code.',
            details: {
              member_codes: ['SSA-2026-M001', 'SSA-2026-M002'],
            },
          },
        },
        { status: 409 }
      );
    }

    const searchTerm = (code || q || '').toLowerCase();

    // Check against mock users
    const matchedUser = Object.values(mockUsers).find((u) => {
      const uCode = `SSA-2026-${u.id.substring(4, 9).toUpperCase()}`.toLowerCase();
      return (
        uCode === searchTerm ||
        u.email.toLowerCase() === searchTerm ||
        u.full_name.toLowerCase().includes(searchTerm)
      );
    });

    if (!matchedUser) {
      // Contract rule: unknown code returns HTTP 200 with { valid: false, reason: "..." }
      return HttpResponse.json({
        valid: false,
        reason: 'No member found matching query',
      });
    }

    const isMemberActive = matchedUser.membership?.status === 'active';

    return HttpResponse.json({
      valid: isMemberActive,
      status: matchedUser.membership?.status || 'none',
      name: matchedUser.full_name,
      member_code: `SSA-2026-${matchedUser.id.substring(4, 9).toUpperCase()}`,
      valid_until: matchedUser.membership?.end_date || null,
      reason: isMemberActive ? undefined : 'Membership expired on ' + matchedUser.membership?.end_date,
    });
  }),

  // 11. Memberships List (Admin)
  http.get('*/api/v1/memberships', () => {
    return HttpResponse.json({
      items: mockMemberships,
      total: mockMemberships.length,
      page: 1,
      page_size: 10,
    });
  }),

  // 12. Renewals Due List (Admin)
  http.get('*/api/v1/memberships/renewals-due', () => {
    return HttpResponse.json({
      items: mockRenewalsDue,
      total: mockRenewalsDue.length,
    });
  }),

  // 13. Users List (Admin)
  http.get('*/api/v1/users', () => {
    const userList = Object.values(mockUsers);
    return HttpResponse.json({
      items: userList,
      total: userList.length,
      page: 1,
      page_size: 10,
    });
  }),
];
