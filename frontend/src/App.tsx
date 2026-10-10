import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from './components/ui/Toast';
import { AuthProvider } from './context/AuthContext';
import { RequireAuth } from './components/auth/RequireAuth';
import { RequireRole } from './components/auth/RequireRole';
import { Layout } from './components/layout/Layout';

import { EventsList } from './pages/events/EventsList';
import { EventDetail } from './pages/events/EventDetail';
import { MyTickets } from './pages/tickets/MyTickets';
import { DoorScanner } from './pages/staff/DoorScanner';
import { ManageEvents } from './pages/manage/ManageEvents';
import { EventForm } from './pages/manage/EventForm';
import { EventReport } from './pages/manage/EventReport';

// Pages
import { Home } from './pages/Home';
import { Login } from './pages/auth/Login';
import { Register } from './pages/auth/Register';
import { Join } from './pages/membership/Join';
import { Checkout } from './pages/membership/Checkout';
import { MemberDashboard } from './pages/membership/MemberDashboard';
import { VerifyMember } from './pages/staff/VerifyMember';
import { AdminMembers } from './pages/admin/AdminMembers';
import { AdminPlans } from './pages/admin/AdminPlans';
import { AdminRenewals } from './pages/admin/AdminRenewals';
import { Button } from './components/ui/Button';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 1000 * 60 * 2, // 2 minutes
    },
  },
});

function NotFound() {
  return (
    <div className="max-w-md mx-auto px-4 py-24 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-800 text-slate-400 font-black text-2xl flex items-center justify-center mx-auto mb-4 border border-slate-700">
        404
      </div>
      <h1 className="text-2xl font-bold text-white mb-2">Page Not Found</h1>
      <p className="text-sm text-slate-400 mb-6">
        The requested URL was not found on SSA Hub or belongs to a later phase.
      </p>
      <a href="/">
        <Button variant="primary">Return Home</Button>
      </a>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Layout />}>
                {/* Public Routes */}
                <Route index element={<Home />} />
                <Route path="events" element={<EventsList />} />
                <Route path="events/:id" element={<EventDetail />} />
                <Route path="login" element={<Login />} />
                <Route path="register" element={<Register />} />
                <Route path="join" element={<Join />} />

                {/* Member / Authenticated Routes */}
                <Route
                  path="checkout/:orderId"
                  element={
                    <RequireAuth>
                      <Checkout />
                    </RequireAuth>
                  }
                />
                <Route
                  path="me"
                  element={
                    <RequireAuth>
                      <MemberDashboard />
                    </RequireAuth>
                  }
                />
                <Route
                  path="me/tickets"
                  element={
                    <RequireAuth>
                      <MyTickets />
                    </RequireAuth>
                  }
                />

                {/* Staff Routes (Volunteer & above) */}
                <Route
                  path="staff/verify-member"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="volunteer">
                        <VerifyMember />
                      </RequireRole>
                    </RequireAuth>
                  }
                />
                <Route
                  path="staff/scan"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="volunteer">
                        <DoorScanner />
                      </RequireRole>
                    </RequireAuth>
                  }
                />

                {/* Organizer Event Management Routes */}
                <Route
                  path="manage/events"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="organizer">
                        <ManageEvents />
                      </RequireRole>
                    </RequireAuth>
                  }
                />
                <Route
                  path="manage/events/new"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="organizer">
                        <EventForm />
                      </RequireRole>
                    </RequireAuth>
                  }
                />
                <Route
                  path="manage/events/:id/edit"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="organizer">
                        <EventForm />
                      </RequireRole>
                    </RequireAuth>
                  }
                />
                <Route
                  path="manage/events/:id/report"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="organizer">
                        <EventReport />
                      </RequireRole>
                    </RequireAuth>
                  }
                />

                {/* Admin Routes */}
                <Route
                  path="admin/members"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="admin">
                        <AdminMembers />
                      </RequireRole>
                    </RequireAuth>
                  }
                />
                <Route
                  path="admin/plans"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="admin">
                        <AdminPlans />
                      </RequireRole>
                    </RequireAuth>
                  }
                />
                <Route
                  path="admin/renewals"
                  element={
                    <RequireAuth>
                      <RequireRole minRole="organizer">
                        <AdminRenewals />
                      </RequireRole>
                    </RequireAuth>
                  }
                />

                {/* Redirects and 404 */}
                <Route path="members" element={<Navigate to="/admin/members" replace />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
