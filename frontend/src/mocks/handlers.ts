import { http, HttpResponse } from 'msw';
import { mockPlans, mockUsers, mockMemberships, mockRenewalsDue, mockEvents, mockTickets } from './data';
import type { UserMe, MembershipPlan } from '../types/api';
import type { EventDetail, TicketItem, TicketCheckoutResponse } from '../types/events';

let activeUserEmail = 'member@ssa.org';
const plansState: MembershipPlan[] = [...mockPlans];
export const eventsState: EventDetail[] = JSON.parse(JSON.stringify(mockEvents));
export const ticketsState: TicketItem[] = JSON.parse(JSON.stringify(mockTickets));
export const ticketOrdersState: Record<string, {
  order_id: string;
  payment_id: string;
  amount: number;
  ticket_type_id: string;
  quantity: number;
  user_email: string;
  user_name: string;
}> = {};


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

    const ticketOrder = ticketOrdersState[String(orderId)];
    if (ticketOrder) {
      if (body.outcome === 'fail') {
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
        order_status: 'completed',
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

    return HttpResponse.json(userTickets);
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
];

