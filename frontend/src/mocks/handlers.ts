import { http, HttpResponse } from 'msw';
import { mockPlans, mockUsers, mockMemberships, mockRenewalsDue, mockEvents, mockTickets, mockAnnouncements, mockDeliveries, mockProducts, mockMerchOrders, mockFundraisers, mockTasks, type MockFundraiserRecord, type MockTaskRecord } from './data';
import type { UserMe, MembershipPlan } from '../types/api';
import type { EventDetail, TicketItem, TicketCheckoutResponse } from '../types/events';
import type { Announcement, AnnouncementDetail, AnnouncementDelivery, AnnouncementCategory, AnnouncementAudience } from '../types/announcements';
import type { Product, ProductVariant, MerchOrder, MerchOrderItem, FulfillmentStatus } from '../features/shop/types';

let activeUserEmail = 'member@ssa.org';
// The real API wraps every list in a page envelope. The app unwraps it, so the mocks have to
// answer with one too - returning a bare array here is what let contract drift go unnoticed.
const asPage = <T>(items: T[], pageSize = 100) => ({
  items,
  total: items.length,
  page: 1,
  page_size: pageSize,
});
const plansState: MembershipPlan[] = [...mockPlans];
export const eventsState: EventDetail[] = JSON.parse(JSON.stringify(mockEvents));
export const ticketsState: TicketItem[] = JSON.parse(JSON.stringify(mockTickets));
export const announcementsState: AnnouncementDetail[] = JSON.parse(JSON.stringify(mockAnnouncements));

/** GET /announcements sends the first 200 characters, not the body (DESIGN.md 5). */
const summarise = ({ body, revision_note: _revision_note, ...rest }: AnnouncementDetail): Announcement => ({
  ...rest,
  body_preview: body.slice(0, 200),
});
export const deliveriesState: AnnouncementDelivery[] = JSON.parse(JSON.stringify(mockDeliveries));
export const productsState: Product[] = JSON.parse(JSON.stringify(mockProducts));
export const merchOrdersState: MerchOrder[] = JSON.parse(JSON.stringify(mockMerchOrders));
export const fundraisersState: MockFundraiserRecord[] = JSON.parse(JSON.stringify(mockFundraisers));
export const tasksState: MockTaskRecord[] = JSON.parse(JSON.stringify(mockTasks));
export const ticketOrdersState: Record<string, {
  order_id: string;
  payment_id: string;
  amount: number;
  ticket_type_id: string;
  quantity: number;
  user_email: string;
  user_name: string;
}> = {};


// Orders the checkout page has to be able to describe after a reload: a membership order has no
// other home, and the status of all of them lives here once it is settled.
const membershipOrdersState: Record<string, { amount: number }> = {};
const orderStatusState: Record<string, 'pending' | 'paid' | 'failed'> = {};

// The gateway callback and the simulated buttons settle through one function, exactly as they
// do on the backend. /verify carries no `outcome`, so it always takes the success path.
const settleMockPayment: Parameters<typeof http.post>[1] = async ({ params, request }) => {
  const { orderId } = params;
  const body = (await request.json()) as { outcome: 'success' | 'fail' };

  const ticketOrder = ticketOrdersState[String(orderId)];
  if (ticketOrder) {
    if (body.outcome === 'fail') {
      orderStatusState[String(orderId)] = 'failed';
      orderStatusState[String(orderId)] = 'paid';
      return HttpResponse.json({
        order_id: String(orderId),
        payment_id: ticketOrder.payment_id,
        order_status: 'failed',
        payment_status: 'failed',
        provider_ref: `txn_fail_${Date.now()}`,
      });
    }

    // Success for ticket order
    let foundEvent: EventDetail | undefined;
    let foundType: any;
    for (const ev of eventsState) {
      const tt = ev.ticket_types.find((t) => t.id === ticketOrder.ticket_type_id);
      if (tt) {
        foundEvent = ev;
        foundType = tt;
        break;
      }
    }

    if (foundType && foundEvent) {
      foundType.sold_count = (foundType.sold_count || 0) + ticketOrder.quantity;
      foundType.seats_left = Math.max(0, (foundType.seats_left ?? foundType.capacity) - ticketOrder.quantity);

      for (let i = 0; i < ticketOrder.quantity; i++) {
        const randCode = `${foundEvent.title.replace(/[^A-Za-z]/g, '').substring(0, 4).toUpperCase()}-${Math.floor(1000 + Math.random() * 9000)}`;
        ticketsState.unshift({
          id: `tkt_${Math.random().toString(36).substring(2, 9)}`,
          order_id: String(orderId),
          event_id: foundEvent.id,
          event_title: foundEvent.title,
          venue: foundEvent.venue,
          starts_at: foundEvent.starts_at,
          ends_at: foundEvent.ends_at,
          ticket_type_name: foundType.name,
          code: randCode,
          status: 'valid',
          price_paid: Math.round(ticketOrder.amount / ticketOrder.quantity),
          is_member_price: ticketOrder.amount < foundType.non_member_price * ticketOrder.quantity,
          user_name: ticketOrder.user_name,
          user_email: ticketOrder.user_email,
          checked_in_at: null,
        });
      }
    }

    return HttpResponse.json({
      order_id: String(orderId),
      payment_id: ticketOrder.payment_id,
      order_status: 'paid',
      payment_status: 'succeeded',
      provider_ref: `txn_mock_${Date.now()}`,
    });
  }

  const merchOrder = merchOrdersState.find((o) => o.id === String(orderId));
  if (merchOrder) {
    if (body.outcome === 'fail') {
      orderStatusState[String(orderId)] = 'failed';
      merchOrder.status = 'failed';
      merchOrder.updated_at = new Date().toISOString();
      return HttpResponse.json({
        order_id: String(orderId),
        payment_id: `pay_${Math.random().toString(36).substring(2, 10)}`,
        order_status: 'failed',
        payment_status: 'failed',
        provider_ref: `txn_fail_${Date.now()}`,
      });
    }
    merchOrder.status = 'paid';
    merchOrder.updated_at = new Date().toISOString();
    orderStatusState[String(orderId)] = 'paid';
    return HttpResponse.json({
      order_id: String(orderId),
      payment_id: `pay_${Math.random().toString(36).substring(2, 10)}`,
      order_status: 'paid',
      payment_status: 'succeeded',
      provider_ref: `txn_mock_${Date.now()}`,
    });
  }

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
  orderStatusState[String(orderId)] = 'paid';
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
    order_status: 'paid',
    payment_status: 'succeeded',
    provider_ref: `txn_mock_${Date.now()}`,
    membership: {
      id: `mem_${Math.random().toString(36).substring(2, 9)}`,
      status: 'active',
      end_date: endDate.toISOString(),
    },
  });
};

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
    return HttpResponse.json(asPage(plansState));
  }),

  // 5. Create Plan (Admin)
  http.post('*/api/v1/plans', async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      description?: string;
      price: number;
      duration_months: number;
      ticket_discount_pct?: number;
      merch_discount_pct?: number;
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
      duration_months: body.duration_months,
      ticket_discount_pct: body.ticket_discount_pct ?? 0,
      merch_discount_pct: body.merch_discount_pct ?? 0,
      is_active: body.is_active ?? true,
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
    membershipOrdersState[orderId] = { amount: plan.price };
    orderStatusState[orderId] = 'pending';

    return HttpResponse.json({
      order_id: orderId,
      payment_id: paymentId,
      amount: plan.price,
      provider: 'mock_cashfree',
      status: 'pending',
    });
  }),

  // 8. Mock payment settlement: the simulated buttons and the gateway callback, same code.
  http.post('*/api/v1/payments/:orderId/mock-confirm', settleMockPayment),
  http.post('*/api/v1/payments/:orderId/verify', settleMockPayment),

  // 8b. Which order is this, and what does it cost? The checkout page asks before it opens
  // anything, because the state it was navigated with is gone after a reload.
  http.get('*/api/v1/payments/:orderId', ({ params }) => {
    const orderId = String(params.orderId);
    const ticketOrder = ticketOrdersState[orderId];
    const merchOrder = merchOrdersState.find((o) => o.id === orderId);
    const membershipOrder = membershipOrdersState[orderId];
    const amount = ticketOrder?.amount ?? merchOrder?.amount ?? membershipOrder?.amount;

    if (amount === undefined) {
      return HttpResponse.json(
        { error: { code: 'ORDER_NOT_FOUND', message: 'Order not found', details: {} } },
        { status: 404 }
      );
    }

    const orderStatus = orderStatusState[orderId] ?? 'pending';
    return HttpResponse.json({
      order_id: orderId,
      kind: ticketOrder ? 'ticket' : merchOrder ? 'merch' : 'membership',
      order_status: orderStatus,
      amount,
      currency: 'INR',
      provider: 'mock',
      payment_status: orderStatus === 'paid' ? 'succeeded' : 'created',
      key_id: null,
      gateway_order_id: null,
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

  // ==========================================
  // PHASE 2: EVENTS, TICKETS, CHECK-IN, REPORTS
  // ==========================================

  // 14. Events List (Public & Manage)
  http.get('*/api/v1/events', ({ request }) => {
    const url = new URL(request.url);
    const statusParam = url.searchParams.get('status');
    const page = parseInt(url.searchParams.get('page') || '1', 10);
    const pageSize = parseInt(url.searchParams.get('page_size') || '20', 10);

    let filtered = [...eventsState];
    if (statusParam) {
      filtered = filtered.filter((e) => e.status === statusParam);
    }

    filtered = filtered.map((e) => {
      const prices = (e.ticket_types || []).flatMap((t) => [t.member_price, t.non_member_price]);
      const minP = prices.length > 0 ? Math.min(...prices) : 0;
      return {
        ...e,
        min_price: minP,
      };
    });

    const start = (page - 1) * pageSize;
    const paginated = filtered.slice(start, start + pageSize);

    return HttpResponse.json({
      items: paginated,
      total: filtered.length,
      page,
      page_size: pageSize,
    });
  }),

  // 15. Event Detail
  http.get('*/api/v1/events/:id', ({ params }) => {
    const { id } = params;
    const event = eventsState.find((e) => e.id === id);

    if (!event) {
      return HttpResponse.json(
        {
          error: {
            code: 'NOT_FOUND',
            message: 'Event not found or has been removed.',
          },
        },
        { status: 404 }
      );
    }

    const ticketTypesWithSeats = event.ticket_types.map((t) => {
      const sold = t.sold_count || 0;
      return {
        ...t,
        sold_count: sold,
        seats_left: Math.max(0, t.capacity - sold),
      };
    });

    const prices = ticketTypesWithSeats.flatMap((t) => [t.member_price, t.non_member_price]);

    return HttpResponse.json({
      ...event,
      ticket_types: ticketTypesWithSeats,
      min_price: prices.length > 0 ? Math.min(...prices) : 0,
    });
  }),

  // 16. Event Create (Organizer+)
  http.post('*/api/v1/events', async ({ request }) => {
    const body = (await request.json()) as any;

    const newEvent: EventDetail = {
      id: `evt_${Math.random().toString(36).substring(2, 9)}`,
      title: body.title,
      description: body.description,
      venue: body.venue,
      starts_at: body.starts_at,
      ends_at: body.ends_at,
      banner_url: body.banner_url || null,
      status: body.status || 'draft',
      created_at: new Date().toISOString(),
      ticket_types: [],
      min_price: 0,
    };

    eventsState.unshift(newEvent);

    return HttpResponse.json(newEvent, { status: 201 });
  }),

  // 17. Event Update (Organizer+)
  http.patch('*/api/v1/events/:id', async ({ params, request }) => {
    const { id } = params;
    const body = (await request.json()) as any;

    const index = eventsState.findIndex((e) => e.id === id);
    if (index === -1) {
      return HttpResponse.json(
        {
          error: {
            code: 'NOT_FOUND',
            message: 'Event not found.',
          },
        },
        { status: 404 }
      );
    }

    eventsState[index] = {
      ...eventsState[index],
      ...body,
    };

    return HttpResponse.json(eventsState[index]);
  }),

  // 18. Create Ticket Type (Organizer+)
  http.post('*/api/v1/events/:id/ticket-types', async ({ params, request }) => {
    const { id } = params;
    const body = (await request.json()) as any;

    const event = eventsState.find((e) => e.id === id);
    if (!event) {
      return HttpResponse.json(
        {
          error: {
            code: 'NOT_FOUND',
            message: 'Event not found.',
          },
        },
        { status: 404 }
      );
    }

    const newType = {
      id: `tt_${Math.random().toString(36).substring(2, 9)}`,
      event_id: String(id),
      name: body.name,
      member_price: body.member_price,
      non_member_price: body.non_member_price,
      capacity: body.capacity,
      sold_count: 0,
      seats_left: body.capacity,
      sale_starts_at: body.sale_starts_at || null,
      sale_ends_at: body.sale_ends_at || null,
    };

    event.ticket_types.push(newType);

    return HttpResponse.json(newType, { status: 201 });
  }),

  // 19. Ticket Checkout
  http.post('*/api/v1/tickets/checkout', async ({ request }) => {
    const body = (await request.json()) as { ticket_type_id: string; quantity: number };

    let foundEvent: EventDetail | undefined;
    let foundType: any;

    for (const ev of eventsState) {
      const tt = ev.ticket_types.find((t) => t.id === body.ticket_type_id);
      if (tt) {
        foundEvent = ev;
        foundType = tt;
        break;
      }
    }

    if (!foundEvent || !foundType) {
      return HttpResponse.json(
        {
          error: {
            code: 'TICKET_TYPE_NOT_FOUND',
            message: 'Requested ticket tier does not exist.',
          },
        },
        { status: 404 }
      );
    }

    const seatsLeft = foundType.seats_left ?? (foundType.capacity - (foundType.sold_count || 0));

    if (seatsLeft <= 0 || seatsLeft < body.quantity) {
      return HttpResponse.json(
        {
          error: {
            code: 'SOLD_OUT',
            message: 'Requested ticket tier is sold out or does not have enough seats left.',
            details: {
              available: Math.max(0, seatsLeft),
              requested: body.quantity,
            },
          },
        },
        { status: 409 }
      );
    }

    const currentUser = mockUsers[activeUserEmail] || mockUsers['member@ssa.org'];
    const isMember = currentUser.membership?.status === 'active';
    const unitPrice = isMember ? foundType.member_price : foundType.non_member_price;
    const totalPaise = unitPrice * body.quantity;

    // Free ticket flow
    if (totalPaise === 0) {
      foundType.sold_count = (foundType.sold_count || 0) + body.quantity;
      foundType.seats_left = Math.max(0, seatsLeft - body.quantity);

      for (let i = 0; i < body.quantity; i++) {
        const randCode = `${foundEvent.title.replace(/[^A-Za-z]/g, '').substring(0, 4).toUpperCase()}-${Math.floor(1000 + Math.random() * 9000)}`;
        ticketsState.unshift({
          id: `tkt_${Math.random().toString(36).substring(2, 9)}`,
          order_id: `ord_free_${Date.now()}_${i}`,
          event_id: foundEvent.id,
          event_title: foundEvent.title,
          venue: foundEvent.venue,
          starts_at: foundEvent.starts_at,
          ends_at: foundEvent.ends_at,
          ticket_type_name: foundType.name,
          code: randCode,
          status: 'valid',
          price_paid: 0,
          is_member_price: isMember,
          user_name: currentUser.full_name,
          user_email: currentUser.email,
          checked_in_at: null,
        });
      }

      const res: TicketCheckoutResponse = {
        order_id: `ord_free_${Date.now()}`,
        payment_id: 'free_claim',
        amount: 0,
        provider: 'free_checkout',
        status: 'completed',
        event_title: foundEvent.title,
        ticket_type_name: foundType.name,
        quantity: body.quantity,
        unit_price: 0,
        is_member_price: isMember,
      };

      return HttpResponse.json(res);
    }

    // Paid ticket flow
    const orderId = `ord_tkt_${Math.random().toString(36).substring(2, 10)}`;
    const paymentId = `pay_${Math.random().toString(36).substring(2, 10)}`;

    orderStatusState[orderId] = 'pending';
    ticketOrdersState[orderId] = {
      order_id: orderId,
      payment_id: paymentId,
      amount: totalPaise,
      ticket_type_id: foundType.id,
      quantity: body.quantity,
      user_email: currentUser.email,
      user_name: currentUser.full_name,
    };

    const res: TicketCheckoutResponse = {
      order_id: orderId,
      payment_id: paymentId,
      amount: totalPaise,
      provider: 'mock_cashfree',
      status: 'pending',
      event_title: foundEvent.title,
      ticket_type_name: foundType.name,
      quantity: body.quantity,
      unit_price: unitPrice,
      is_member_price: isMember,
    };

    return HttpResponse.json(res);
  }),

  // 20. My Tickets
  http.get('*/api/v1/tickets/me', () => {
    const currentUser = mockUsers[activeUserEmail] || mockUsers['member@ssa.org'];
    const userTickets = ticketsState.filter(
      (t) => t.user_email === currentUser.email || currentUser.email === 'member@ssa.org'
    );

    return HttpResponse.json(asPage(userTickets));
  }),

  // 21. Check-in Endpoint (Door Scanner)
  http.post('*/api/v1/checkin', async ({ request }) => {
    const body = (await request.json()) as { code: string; event_id: string };

    const searchCode = (body.code || '').trim().toUpperCase();
    const ticket = ticketsState.find((t) => t.code.toUpperCase() === searchCode);

    if (!ticket) {
      return HttpResponse.json({
        result: 'INVALID',
        ticket: null,
      });
    }

    if (ticket.event_id !== body.event_id) {
      return HttpResponse.json({
        result: 'WRONG_EVENT',
        ticket,
      });
    }

    if (ticket.status === 'used') {
      return HttpResponse.json({
        result: 'ALREADY_USED',
        ticket,
        checked_in_at: ticket.checked_in_at || 'Earlier today',
      });
    }

    // Valid check-in
    ticket.status = 'used';
    const nowIso = new Date().toISOString();
    ticket.checked_in_at = nowIso;

    return HttpResponse.json({
      result: 'VALID',
      ticket,
      checked_in_at: nowIso,
    });
  }),

  // 22. Event Report (Organizer+)
  http.get('*/api/v1/events/:id/report', ({ params }) => {
    const { id } = params;
    const event = eventsState.find((e) => e.id === id);

    if (!event) {
      return HttpResponse.json(
        {
          error: {
            code: 'NOT_FOUND',
            message: 'Event not found.',
          },
        },
        { status: 404 }
      );
    }

    const eventTickets = ticketsState.filter((t) => t.event_id === id);
    const totalCapacity = event.ticket_types.reduce((acc, t) => acc + t.capacity, 0);

    const soldCount = eventTickets.length;
    const checkedInCount = eventTickets.filter((t) => t.status === 'used').length;
    const noShows = Math.max(0, soldCount - checkedInCount);
    const seatsLeft = Math.max(0, totalCapacity - soldCount);
    const rate = soldCount > 0 ? Number(((checkedInCount / soldCount) * 100).toFixed(1)) : 0;

    const memberRevenue = eventTickets
      .filter((t) => t.is_member_price)
      .reduce((acc, t) => acc + t.price_paid, 0);

    const nonMemberRevenue = eventTickets
      .filter((t) => !t.is_member_price)
      .reduce((acc, t) => acc + t.price_paid, 0);

    return HttpResponse.json({
      sold: soldCount,
      seats_left: seatsLeft,
      checked_in: checkedInCount,
      no_shows: noShows,
      attendance_rate: rate,
      revenue: {
        member: memberRevenue,
        non_member: nonMemberRevenue,
        total: memberRevenue + nonMemberRevenue,
      },
    });
  }),

  // 23. Event Attendees (Organizer+)
  http.get('*/api/v1/events/:id/attendees', ({ params, request }) => {
    const { id } = params;
    const event = eventsState.find((e) => e.id === id);

    if (!event) {
      return HttpResponse.json(
        {
          error: {
            code: 'NOT_FOUND',
            message: 'Event not found.',
          },
        },
        { status: 404 }
      );
    }

    const url = new URL(request.url);
    const search = (url.searchParams.get('search') || '').toLowerCase();
    const status = url.searchParams.get('status');

    let attendees = ticketsState
      .filter((t) => t.event_id === id)
      .map((t) => ({
        id: t.id,
        ticket_code: t.code,
        user_name: t.user_name || 'Attendee',
        user_email: t.user_email || 'attendee@ssa.org',
        ticket_type_name: t.ticket_type_name,
        price_paid: t.price_paid,
        is_member_price: t.is_member_price,
        status: t.status,
        checked_in_at: t.checked_in_at,
      }));

    if (status) {
      attendees = attendees.filter((a) => a.status === status);
    }

    if (search) {
      attendees = attendees.filter(
        (a) =>
          a.user_name.toLowerCase().includes(search) ||
          a.user_email.toLowerCase().includes(search) ||
          a.ticket_code.toLowerCase().includes(search)
      );
    }

    return HttpResponse.json({
      items: attendees,
      total: attendees.length,
      page: 1,
      page_size: 50,
    });
  }),

  // ==========================================
  // PHASE 3: ANNOUNCEMENTS & PREFERENCES
  // ==========================================

  // 24. List Announcements (Public Feed & Management)
  http.get('*/api/v1/announcements', ({ request }) => {
    const url = new URL(request.url);
    const category = url.searchParams.get('category') as AnnouncementCategory | null;
    const page = parseInt(url.searchParams.get('page') || '1', 10);
    const pageSize = parseInt(url.searchParams.get('page_size') || '20', 10);
    const authHeader = request.headers.get('Authorization');

    const currentUser: UserMe | null = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    let filtered = [...announcementsState];

    // Audience filtering based on user role and tickets
    if (!currentUser || currentUser.role === 'guest') {
      filtered = filtered.filter((a) => a.audience === 'all');
    } else if (currentUser.role === 'member') {
      const userEventIds = ticketsState
        .filter((t) => t.user_email === currentUser.email)
        .map((t) => t.event_id);

      filtered = filtered.filter(
        (a) =>
          a.audience === 'all' ||
          a.audience === 'members' ||
          (a.audience === 'event' && a.event_id && userEventIds.includes(a.event_id))
      );
    }
    // Organizers, Volunteers, and Admins can see all announcements

    // Category filter
    if (category) {
      filtered = filtered.filter((a) => a.category === category);
    }

    // Sort: pinned first, then newest published_at
    filtered.sort((a, b) => {
      if (a.is_pinned && !b.is_pinned) return -1;
      if (!a.is_pinned && b.is_pinned) return 1;
      return new Date(b.published_at).getTime() - new Date(a.published_at).getTime();
    });

    const total = filtered.length;
    const startIndex = (page - 1) * pageSize;
    const items = filtered.slice(startIndex, startIndex + pageSize).map(summarise);

    return HttpResponse.json({
      items,
      total,
      page,
      page_size: pageSize,
    });
  }),

  // 25. Get Single Announcement
  http.get('*/api/v1/announcements/:id', ({ params }) => {
    const { id } = params;
    const announcement = announcementsState.find((a) => a.id === id);

    if (!announcement) {
      return HttpResponse.json(
        {
          error: {
            code: 'ANNOUNCEMENT_NOT_FOUND',
            message: 'The requested announcement could not be found.',
          },
        },
        { status: 404 }
      );
    }

    return HttpResponse.json(announcement);
  }),

  // 26. Create Announcement (Organizer+)
  http.post('*/api/v1/announcements', async ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || (currentUser.role !== 'organizer' && currentUser.role !== 'admin')) {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'You do not have permission to publish announcements.',
          },
        },
        { status: 403 }
      );
    }

    const body = (await request.json()) as {
      title: string;
      body: string;
      category: AnnouncementCategory;
      audience: AnnouncementAudience;
      event_id?: string | null;
      is_pinned?: boolean;
    };

    if (body.audience === 'event' && !body.event_id) {
      return HttpResponse.json(
        {
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Event selection is required when audience is set to event.',
          },
        },
        { status: 422 }
      );
    }

    const newAnnouncement: AnnouncementDetail = {
      id: `ann_${Date.now()}`,
      title: body.title,
      body: body.body,
      category: body.category,
      audience: body.audience,
      event_id: body.audience === 'event' ? body.event_id || null : null,
      is_pinned: Boolean(body.is_pinned),
      author_name: currentUser.full_name,
      published_at: new Date().toISOString(),
      revision_note: null,
      edited_at: null,
    };

    announcementsState.unshift(newAnnouncement);

    // Simulate dispatch deliveries
    const newDeliveries: AnnouncementDelivery[] = [
      {
        id: `del_${Date.now()}_1`,
        announcement_id: newAnnouncement.id,
        user_id: 'usr_member_02',
        user_name: 'Aarav Patel',
        user_email: 'member@ssa.org',
        channel: 'email',
        status: 'sent',
        sent_at: new Date().toISOString(),
      },
      {
        id: `del_${Date.now()}_2`,
        announcement_id: newAnnouncement.id,
        user_id: 'usr_expiring_03',
        user_name: 'Diya Sharma',
        user_email: 'expiring@ssa.org',
        channel: 'email',
        status: 'queued',
        sent_at: null,
      },
    ];
    deliveriesState.unshift(...newDeliveries);

    return HttpResponse.json(
      {
        ...newAnnouncement,
        delivery_summary: {
          inapp_queued: newDeliveries.length,
          email_queued: newDeliveries.length,
          skipped_opted_out: 0,
        },
      },
      { status: 201 }
    );
  }),

  // 27. Update Announcement Revision Note (Organizer+)
  http.patch('*/api/v1/announcements/:id', async ({ params, request }) => {
    const { id } = params;
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || (currentUser.role !== 'organizer' && currentUser.role !== 'admin')) {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'You do not have permission to edit announcements.',
          },
        },
        { status: 403 }
      );
    }

    const body = (await request.json()) as { revision_note: string };
    const announcement = announcementsState.find((a) => a.id === id);

    if (!announcement) {
      return HttpResponse.json(
        {
          error: {
            code: 'ANNOUNCEMENT_NOT_FOUND',
            message: 'Announcement not found.',
          },
        },
        { status: 404 }
      );
    }

    announcement.revision_note = body.revision_note;
    announcement.edited_at = new Date().toISOString();

    return HttpResponse.json(announcement);
  }),

  // 28. Get Announcement Deliveries (Admin Only!)
  http.get('*/api/v1/announcements/:id/deliveries', ({ params, request }) => {
    const { id } = params;
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    // Strict Role Check: Deliveries are Admin Only
    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Only administrators are authorized to inspect announcement delivery logs.',
          },
        },
        { status: 403 }
      );
    }

    const items = deliveriesState.filter((d) => d.announcement_id === id);
    const queued = items.filter((d) => d.status === 'queued').length;
    const sent = items.filter((d) => d.status === 'sent').length;
    const failed = items.filter((d) => d.status === 'failed').length;

    return HttpResponse.json({
      items,
      total: items.length,
      counts: {
        queued,
        sent,
        failed,
        total: items.length,
      },
    });
  }),

  // 29. Update Email Preferences
  http.post('*/api/v1/users/me/email-preferences', async ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        {
          error: {
            code: 'UNAUTHORIZED',
            message: 'Authentication required to update preferences.',
          },
        },
        { status: 401 }
      );
    }

    const body = (await request.json()) as { email_opt_in: boolean };
    currentUser.email_opt_in = body.email_opt_in;

    return HttpResponse.json(currentUser);
  }),

  // 30. Get Products (Public / Admin)
  http.get('*/api/v1/products', ({ request }) => {
    const url = new URL(request.url);
    const includeInactive = url.searchParams.get('include_inactive') === 'true';

    const products = includeInactive
      ? productsState
      : productsState.filter((p) => p.is_active);

    return HttpResponse.json(asPage(products));
  }),

  // 31. Get Single Product
  http.get('*/api/v1/products/:id', ({ params }) => {
    const { id } = params;
    const product = productsState.find((p) => p.id === id);

    if (!product) {
      return HttpResponse.json(
        {
          error: {
            code: 'PRODUCT_NOT_FOUND',
            message: 'Product not found.',
          },
        },
        { status: 404 }
      );
    }

    return HttpResponse.json(product);
  }),

  // 32. Create Product (Admin)
  http.post('*/api/v1/products', async ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required to create products.',
          },
        },
        { status: 403 }
      );
    }

    const body = (await request.json()) as {
      name: string;
      description?: string | null;
      image_url?: string | null;
      base_price: number;
      member_discount_pct: number;
      is_active?: boolean;
    };

    const newProduct: Product = {
      id: `prod_${Math.random().toString(36).substring(2, 9)}`,
      name: body.name,
      description: body.description ?? null,
      image_url: body.image_url ?? null,
      base_price: body.base_price,
      member_discount_pct: body.member_discount_pct ?? 0,
      is_active: body.is_active ?? true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      variants: [],
    };

    productsState.unshift(newProduct);
    return HttpResponse.json(newProduct, { status: 201 });
  }),

  // 33. Update Product (Admin)
  http.patch('*/api/v1/products/:id', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required to update products.',
          },
        },
        { status: 403 }
      );
    }

    const { id } = params;
    const product = productsState.find((p) => p.id === id);
    if (!product) {
      return HttpResponse.json(
        {
          error: {
            code: 'PRODUCT_NOT_FOUND',
            message: 'Product not found.',
          },
        },
        { status: 404 }
      );
    }

    const body = (await request.json()) as Partial<Product>;
    if (body.name !== undefined) product.name = body.name;
    if (body.description !== undefined) product.description = body.description;
    if (body.image_url !== undefined) product.image_url = body.image_url;
    if (body.base_price !== undefined) product.base_price = body.base_price;
    if (body.member_discount_pct !== undefined) product.member_discount_pct = body.member_discount_pct;
    if (body.is_active !== undefined) product.is_active = body.is_active;
    product.updated_at = new Date().toISOString();

    return HttpResponse.json(product);
  }),

  // 34. Create Variant (Admin)
  http.post('*/api/v1/products/:id/variants', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required to create variants.',
          },
        },
        { status: 403 }
      );
    }

    const { id } = params;
    const product = productsState.find((p) => p.id === id);
    if (!product) {
      return HttpResponse.json(
        {
          error: {
            code: 'PRODUCT_NOT_FOUND',
            message: 'Product not found.',
          },
        },
        { status: 404 }
      );
    }

    const body = (await request.json()) as {
      size: string;
      color?: string | null;
      sku: string;
      stock: number;
      low_stock_threshold: number;
    };

    if (body.stock < 0) {
      return HttpResponse.json(
        {
          error: {
            code: 'INVALID_STOCK',
            message: 'Stock cannot be negative.',
          },
        },
        { status: 400 }
      );
    }

    const newVariant: ProductVariant = {
      id: `var_${Math.random().toString(36).substring(2, 9)}`,
      product_id: String(id),
      size: body.size,
      color: body.color ?? null,
      sku: body.sku,
      stock: body.stock,
      low_stock_threshold: body.low_stock_threshold ?? 5,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    product.variants.push(newVariant);
    product.updated_at = new Date().toISOString();

    return HttpResponse.json(newVariant, { status: 201 });
  }),

  // 35. Update Variant (Admin)
  // Contract: PATCH /variants/{variant_id}. It has no stock field - see 35b.
  http.patch('*/api/v1/variants/:variantId', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required to update variants.',
          },
        },
        { status: 403 }
      );
    }

    const { variantId } = params;
    const product = productsState.find((p) => p.variants.some((v) => v.id === variantId));
    const variant = product?.variants.find((v) => v.id === variantId);
    if (!product || !variant) {
      return HttpResponse.json(
        {
          error: {
            code: 'VARIANT_NOT_FOUND',
            message: 'Product variant not found.',
          },
        },
        { status: 404 }
      );
    }

    const body = (await request.json()) as Partial<ProductVariant>;
    if (body.size !== undefined) variant.size = body.size;
    if (body.color !== undefined) variant.color = body.color;
    if (body.sku !== undefined) variant.sku = body.sku;
    if (body.low_stock_threshold !== undefined) variant.low_stock_threshold = body.low_stock_threshold;
    variant.updated_at = new Date().toISOString();
    product.updated_at = new Date().toISOString();

    return HttpResponse.json(variant);
  }),

  // 35b. Adjust Variant Stock (Admin)
  // Contract: POST /variants/{variant_id}/stock-adjust, reason is "restock" | "adjustment".
  http.post('*/api/v1/variants/:variantId/stock-adjust', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required to adjust stock.',
          },
        },
        { status: 403 }
      );
    }

    const { variantId } = params;
    const product = productsState.find((p) => p.variants.some((v) => v.id === variantId));
    const variant = product?.variants.find((v) => v.id === variantId);
    if (!product || !variant) {
      return HttpResponse.json(
        {
          error: {
            code: 'VARIANT_NOT_FOUND',
            message: 'Product variant not found.',
          },
        },
        { status: 404 }
      );
    }

    const body = (await request.json()) as { delta: number; reason: string; note?: string | null };
    if (variant.stock + body.delta < 0) {
      return HttpResponse.json(
        {
          error: {
            code: 'INVALID_STOCK',
            message: 'Stock cannot be negative.',
          },
        },
        { status: 400 }
      );
    }
    variant.stock += body.delta;
    variant.updated_at = new Date().toISOString();
    product.updated_at = new Date().toISOString();

    return HttpResponse.json(variant);
  }),

  // 36. Member Merch Checkout
  http.post('*/api/v1/orders/merch/checkout', async ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        {
          error: {
            code: 'UNAUTHORIZED',
            message: 'Authentication required to checkout.',
          },
        },
        { status: 401 }
      );
    }

    // Role check: Only active members (or staff/organizer/admin) can order
    const isMember = currentUser.membership?.status === 'active' || currentUser.role === 'admin' || currentUser.role === 'organizer';
    if (!isMember) {
      return HttpResponse.json(
        {
          error: {
            code: 'MEMBERSHIP_REQUIRED',
            message: 'Merchandise ordering is an exclusive benefit for active club members. Join a plan to unlock store access.',
          },
        },
        { status: 403 }
      );
    }

    const body = (await request.json()) as {
      items: Array<{ variant_id: string; quantity: number }>;
      delivery_note?: string;
    };

    if (!body.items || body.items.length === 0) {
      return HttpResponse.json(
        {
          error: {
            code: 'EMPTY_CART',
            message: 'Your cart is empty.',
          },
        },
        { status: 400 }
      );
    }

    // Concurrency-safe atomic stock check across all requested items
    type ResolvedLine = {
      product: Product;
      variant: ProductVariant;
      quantity: number;
      unitPrice: number;
    };
    const resolvedLines: ResolvedLine[] = [];

    for (const item of body.items) {
      const reqQty = (item as any).qty ?? (item as any).quantity ?? 1;
      let foundProduct: Product | undefined;
      let foundVariant: ProductVariant | undefined;

      for (const p of productsState) {
        const v = p.variants.find((vr) => vr.id === item.variant_id);
        if (v) {
          foundProduct = p;
          foundVariant = v;
          break;
        }
      }

      if (!foundProduct || !foundVariant) {
        return HttpResponse.json(
          {
            error: {
              code: 'VARIANT_NOT_FOUND',
              message: `Variant ${item.variant_id} does not exist.`,
            },
          },
          { status: 404 }
        );
      }

      if (foundVariant.stock < reqQty) {
        return HttpResponse.json(
          {
            error: {
              code: 'SOLD_OUT',
              message: `Insufficient stock for ${foundProduct.name} (${foundVariant.size}). Available: ${foundVariant.stock}, requested: ${reqQty}.`,
              details: {
                variant_id: foundVariant.id,
                available: foundVariant.stock,
                requested: reqQty,
              },
            },
          },
          { status: 409 }
        );
      }

      // Member discount calculation
      const discountPct = foundProduct.member_discount_pct || 0;
      const unitPrice = discountPct > 0
        ? Math.round(foundProduct.base_price * (1 - discountPct / 100))
        : foundProduct.base_price;

      resolvedLines.push({
        product: foundProduct,
        variant: foundVariant,
        quantity: reqQty,
        unitPrice,
      });
    }

    // Atomically decrement stock
    for (const line of resolvedLines) {
      line.variant.stock -= line.quantity;
      line.variant.updated_at = new Date().toISOString();
      line.product.updated_at = new Date().toISOString();
    }

    const orderId = `ord_merch_${Date.now()}`;
    const paymentId = `pay_${Date.now()}`;
    const totalAmount = resolvedLines.reduce((acc, l) => acc + l.unitPrice * l.quantity, 0);

    const orderItems: MerchOrderItem[] = resolvedLines.map((l, idx) => ({
      id: `item_${orderId}_${idx + 1}`,
      variant_id: l.variant.id,
      product_name: l.product.name,
      size: l.variant.size,
      color: l.variant.color,
      qty: l.quantity,
      unit_price: l.unitPrice,
    }));

    const newOrder: MerchOrder = {
      id: orderId,
      user_id: currentUser.id,
      user_name: currentUser.full_name,
      user_email: currentUser.email,
      kind: 'merch',
      amount: totalAmount,
      status: 'pending',
      delivery_note: body.delivery_note || '',
      fulfilment_status: 'paid',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      items: orderItems,
    };

    merchOrdersState.unshift(newOrder);

    return HttpResponse.json({
      order_id: orderId,
      payment_id: paymentId,
      amount: totalAmount,
      status: 'pending',
      provider: 'mock_cashfree',
      delivery_note: body.delivery_note || '',
      items: orderItems,
    });
  }),

  // 37. Get My Orders
  http.get('*/api/v1/orders/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        {
          error: {
            code: 'UNAUTHORIZED',
            message: 'Authentication required to view orders.',
          },
        },
        { status: 401 }
      );
    }

    const myOrders = merchOrdersState.filter(
      (o) => o.user_id === currentUser.id || o.user_email === currentUser.email
    );

    return HttpResponse.json(asPage(myOrders));
  }),

  // 38. Admin Merch Orders Board
  http.get('*/api/v1/admin/merch/orders', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required.',
          },
        },
        { status: 403 }
      );
    }

    const url = new URL(request.url);
    const fulfilmentStatus = url.searchParams.get('fulfilment_status') as FulfillmentStatus | null;
    const page = parseInt(url.searchParams.get('page') || '1', 10);
    const pageSize = parseInt(url.searchParams.get('page_size') || '50', 10);

    let filtered = [...merchOrdersState];
    if (fulfilmentStatus) {
      filtered = filtered.filter((o) => o.fulfilment_status === fulfilmentStatus);
    }

    const total = filtered.length;
    const startIdx = (page - 1) * pageSize;
    const paginated = filtered.slice(startIdx, startIdx + pageSize);

    return HttpResponse.json({
      items: paginated,
      total,
      page,
      page_size: pageSize,
    });
  }),

  // 39. Update Merch Order Fulfillment Status (Admin)
  http.patch('*/api/v1/admin/merch/orders/:id', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required.',
          },
        },
        { status: 403 }
      );
    }

    const { id } = params;
    const order = merchOrdersState.find((o) => o.id === id);
    if (!order) {
      return HttpResponse.json(
        {
          error: {
            code: 'ORDER_NOT_FOUND',
            message: 'Merchandise order not found.',
          },
        },
        { status: 404 }
      );
    }

    const body = (await request.json()) as { fulfilment_status: FulfillmentStatus };
    const validStatuses: FulfillmentStatus[] = ['paid', 'packed', 'handed_over'];
    if (!validStatuses.includes(body.fulfilment_status)) {
      return HttpResponse.json(
        {
          error: {
            code: 'INVALID_STATUS',
            message: 'Invalid fulfilment status provided.',
          },
        },
        { status: 400 }
      );
    }

    order.fulfilment_status = body.fulfilment_status;
    order.updated_at = new Date().toISOString();

    return HttpResponse.json(order);
  }),

  // 40. Admin Stock Summary
  http.get('*/api/v1/admin/merch/stock-summary', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser || currentUser.role !== 'admin') {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Admin authorization required.',
          },
        },
        { status: 403 }
      );
    }

    const items: Array<{
      product_id: string;
      product_name: string;
      variant_id: string;
      size: string;
      sku: string;
      stock: number;
      low_stock_threshold: number;
      demand: number;
      units_packed: number;
      units_handed_over: number;
      pending_fulfillment: number;
    }> = [];

    let lowStockCount = 0;

    for (const p of productsState) {
      for (const v of p.variants) {
        if (v.stock <= v.low_stock_threshold) {
          lowStockCount++;
        }

        let demand = 0;
        let unitsPacked = 0;
        let unitsHandedOver = 0;

        for (const order of merchOrdersState) {
          if (order.status === 'failed') continue;
          for (const item of order.items) {
            if (item.variant_id === v.id) {
              const itemQty = item.qty ?? (item as any).quantity ?? 0;
              demand += itemQty;
              if (order.fulfilment_status === 'packed') {
                unitsPacked += itemQty;
              } else if (order.fulfilment_status === 'handed_over') {
                unitsHandedOver += itemQty;
              }
            }
          }
        }

        items.push({
          product_id: p.id,
          product_name: p.name,
          variant_id: v.id,
          size: v.size,
          sku: v.sku,
          stock: v.stock,
          low_stock_threshold: v.low_stock_threshold,
          demand,
          units_packed: unitsPacked,
          units_handed_over: unitsHandedOver,
          pending_fulfillment: demand - unitsHandedOver,
        });
      }
    }

    return HttpResponse.json({
      items,
      total_variants: items.length,
      low_stock_count: lowStockCount,
    });
  }),

  // ==========================================
  // PHASE 5: FUNDRAISERS & TASKS HANDLERS
  // ==========================================

  // 40. List Fundraisers (organizer+)
  http.get('*/api/v1/fundraisers', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Organizer authorization required.' } },
        { status: 403 }
      );
    }

    const today = new Date().toISOString().split('T')[0];
    const withProgress = fundraisersState.map((f) => {
      const fTasks = tasksState.filter((t) => t.fundraiser_id === f.id);
      const tasks_total = fTasks.length;
      const done = fTasks.filter((t) => t.status === 'done').length;
      const overdue = fTasks.filter((t) => t.status !== 'done' && t.due_date < today).length;
      return {
        ...f,
        progress: {
          fundraiser_id: f.id,
          tasks_total,
          done,
          overdue,
          raised: f.raised_amount,
          goal: f.goal_amount,
        },
      };
    });

    return HttpResponse.json(withProgress);
  }),

  // 41. Create Fundraiser (organizer+)
  http.post('*/api/v1/fundraisers', async ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Organizer authorization required.' } },
        { status: 403 }
      );
    }

    const body = (await request.json()) as {
      title: string;
      description?: string;
      goal_amount: number;
      event_date?: string;
      status?: 'planning' | 'active' | 'done';
    };

    const newFundraiser: MockFundraiserRecord = {
      id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `fnd_${Math.random().toString(36).substring(2, 9)}`,
      title: body.title,
      description: body.description || '',
      goal_amount: body.goal_amount,
      raised_amount: 0,
      event_date: body.event_date || new Date().toISOString().split('T')[0],
      status: body.status || 'planning',
      owner_id: currentUser.id,
      created_at: new Date().toISOString(),
    };

    fundraisersState.unshift(newFundraiser);

    return HttpResponse.json(newFundraiser, { status: 201 });
  }),

  // 42. Get Fundraiser Detail (volunteer+)
  http.get('*/api/v1/fundraisers/:id', ({ request, params }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'volunteer' && currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Volunteer or organizer authorization required.' } },
        { status: 403 }
      );
    }

    const { id } = params as { id: string };
    const fundraiser = fundraisersState.find((f) => f.id === id);

    if (!fundraiser) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'Fundraiser not found.' } },
        { status: 404 }
      );
    }

    const today = new Date().toISOString().split('T')[0];
    const fTasks = tasksState.filter((t) => t.fundraiser_id === id);
    const tasks_total = fTasks.length;
    const done = fTasks.filter((t) => t.status === 'done').length;
    const overdue = fTasks.filter((t) => t.status !== 'done' && t.due_date < today).length;

    return HttpResponse.json({
      ...fundraiser,
      progress: {
        fundraiser_id: fundraiser.id,
        tasks_total,
        done,
        overdue,
        raised: fundraiser.raised_amount,
        goal: fundraiser.goal_amount,
      },
    });
  }),

  // 43. Get Tasks for Fundraiser (volunteer+)
  http.get('*/api/v1/fundraisers/:id/tasks', ({ request, params }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'volunteer' && currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Volunteer or organizer authorization required.' } },
        { status: 403 }
      );
    }

    const { id } = params as { id: string };
    const fundraiser = fundraisersState.find((f) => f.id === id);

    if (!fundraiser) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'Fundraiser not found.' } },
        { status: 404 }
      );
    }

    const tasks = tasksState.filter((t) => t.fundraiser_id === id);
    // The real board answers TaskBoardOut ({columns, counts, items}); the app only reads items.
    return HttpResponse.json({ items: tasks });
  }),

  // 44. Create Task for Fundraiser (organizer+)
  http.post('*/api/v1/fundraisers/:id/tasks', async ({ request, params }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Organizer authorization required.' } },
        { status: 403 }
      );
    }

    const { id } = params as { id: string };
    const fundraiser = fundraisersState.find((f) => f.id === id);

    if (!fundraiser) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'Fundraiser not found.' } },
        { status: 404 }
      );
    }

    const body = (await request.json()) as {
      title: string;
      description?: string;
      category?: string;
      assignee_id?: string | null;
      due_date: string;
    };

    let assigneeName: string | undefined;
    if (body.assignee_id) {
      const foundUser = Object.values(mockUsers).find((u) => u.id === body.assignee_id);
      assigneeName = foundUser ? foundUser.full_name : undefined;
    }

    const newTask: MockTaskRecord = {
      id: `task_${Math.random().toString(36).substring(2, 9)}`,
      fundraiser_id: id,
      title: body.title,
      description: body.description || '',
      category: body.category || 'General',
      assignee_id: body.assignee_id || null,
      assignee_name: assigneeName,
      due_date: body.due_date,
      status: 'todo',
      created_at: new Date().toISOString(),
    };

    tasksState.push(newTask);
    return HttpResponse.json(newTask, { status: 201 });
  }),

  // 45. Update Task (assignee or organizer+)
  http.patch('*/api/v1/tasks/:id', async ({ request, params }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    const { id } = params as { id: string };
    const task = tasksState.find((t) => t.id === id);

    if (!task) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'Task not found.' } },
        { status: 404 }
      );
    }

    // Permission check: organizer/admin or assigned volunteer
    const isOrganizerOrAdmin = currentUser.role === 'organizer' || currentUser.role === 'admin';
    const isAssignee = task.assignee_id === currentUser.id;

    if (!isOrganizerOrAdmin && !isAssignee) {
      return HttpResponse.json(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Only the assigned volunteer or an organizer can update this task.',
          },
        },
        { status: 403 }
      );
    }

    const body = (await request.json()) as {
      status?: 'todo' | 'doing' | 'done';
      assignee_id?: string | null;
    };

    if (body.status !== undefined) {
      task.status = body.status;
    }

    if (body.assignee_id !== undefined) {
      // Only organizer+ can reassign tasks
      if (!isOrganizerOrAdmin && body.assignee_id !== task.assignee_id) {
        return HttpResponse.json(
          {
            error: {
              code: 'FORBIDDEN',
              message: 'Only an organizer or admin can reassign tasks.',
            },
          },
          { status: 403 }
        );
      }

      task.assignee_id = body.assignee_id;
      if (body.assignee_id) {
        const foundUser = Object.values(mockUsers).find((u) => u.id === body.assignee_id);
        task.assignee_name = foundUser ? foundUser.full_name : undefined;
      } else {
        task.assignee_name = undefined;
      }
    }

    return HttpResponse.json(task);
  }),

  // 46. Log Fundraiser Income (organizer+)
  http.post('*/api/v1/fundraisers/:id/income', async ({ request, params }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Organizer authorization required.' } },
        { status: 403 }
      );
    }

    const { id } = params as { id: string };
    const fundraiser = fundraisersState.find((f) => f.id === id);

    if (!fundraiser) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'Fundraiser not found.' } },
        { status: 404 }
      );
    }

    const body = (await request.json()) as {
      amount: number;
      source: string;
      note?: string;
    };

    if (typeof body.amount !== 'number' || body.amount <= 0 || !Number.isInteger(body.amount)) {
      return HttpResponse.json(
        {
          error: {
            code: 'INVALID_AMOUNT',
            message: 'Amount must be a positive integer in paise.',
          },
        },
        { status: 400 }
      );
    }

    fundraiser.raised_amount += body.amount;

    return HttpResponse.json({
      message: 'Income logged successfully.',
      fundraiser_id: fundraiser.id,
      amount: body.amount,
      new_raised_amount: fundraiser.raised_amount,
    });
  }),

  // 47. Get My Tasks (volunteer+) [Gap (a) assumed endpoint]
  http.get('*/api/v1/tasks/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization');
    const currentUser = authHeader ? (mockUsers[activeUserEmail] || null) : null;

    if (!currentUser) {
      return HttpResponse.json(
        { error: { code: 'UNAUTHORIZED', message: 'Authentication required.' } },
        { status: 401 }
      );
    }

    if (currentUser.role !== 'volunteer' && currentUser.role !== 'organizer' && currentUser.role !== 'admin') {
      return HttpResponse.json(
        { error: { code: 'FORBIDDEN', message: 'Volunteer or organizer authorization required.' } },
        { status: 403 }
      );
    }

    const myTasks = tasksState.filter((t) => t.assignee_id === currentUser.id);
    return HttpResponse.json(asPage(myTasks, 200));
  }),
];

