import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from './components/ui/Toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RequireAuth } from './components/auth/RequireAuth';
import { RequireRole } from './components/auth/RequireRole';
import { Layout } from './components/layout/Layout';

// Core Role Portal Pages
import { Login } from './pages/auth/Login';
import { AdminPortal } from './pages/admin/AdminPortal';
import { MemberDashboard } from './pages/membership/MemberDashboard';
import { DoorScanner } from './pages/staff/DoorScanner';

// Optional Company Product Checkout for Students
import { CartProvider } from './features/shop/context/CartContext';
import { ShopCheckout } from './features/shop/pages/ShopCheckout';
import { Checkout } from './pages/membership/Checkout';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 1000 * 60 * 2, // 2 minutes
    },
  },
});

/**
 * Intelligent Root Redirect:
 * Directly routes users to their respective portal based on role:
 * - Unauthenticated -> /login
 * - Admin -> /admin
 * - Student -> /me
 * - Staff -> /staff/scan
 */
function RootRedirect() {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  if (user.role === 'admin') {
    return <Navigate to="/admin" replace />;
  }

  if (user.role === 'volunteer' || user.role === 'organizer') {
    return <Navigate to="/staff/scan" replace />;
  }

  return <Navigate to="/me" replace />;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <CartProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<Layout />}>
                  {/* Intelligent Root Routing */}
                  <Route index element={<RootRedirect />} />

                  {/* 1. Login Page: Admin / Student / Staff ONLY */}
                  <Route path="login" element={<Login />} />

                  {/* 2. Admin Portal: 9 Departments, Events, Registered Student Emails & Add Company Products */}
                  <Route
                    path="admin"
                    element={
                      <RequireAuth>
                        <RequireRole minRole="admin">
                          <AdminPortal />
                        </RequireRole>
                      </RequireAuth>
                    }
                  />

                  {/* 3. Student Portal: Department Events & Optional Company Products */}
                  <Route
                    path="me"
                    element={
                      <RequireAuth>
                        <MemberDashboard />
                      </RequireAuth>
                    }
                  />

                  {/* 4. Staff Portal: Ticket QR Scanning & Check-in */}
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

                  {/* Optional Checkout for Company Products */}
                  <Route
                    path="shop/checkout"
                    element={
                      <RequireAuth>
                        <ShopCheckout />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="checkout/:orderId"
                    element={
                      <RequireAuth>
                        <Checkout />
                      </RequireAuth>
                    }
                  />

                  {/* Redirects for all legacy/old routes to prevent old options from displaying */}
                  <Route path="events/*" element={<RootRedirect />} />
                  <Route path="events" element={<RootRedirect />} />
                  <Route path="announcements" element={<RootRedirect />} />
                  <Route path="shop/*" element={<Navigate to="/me#company-products" replace />} />
                  <Route path="shop" element={<Navigate to="/me#company-products" replace />} />
                  <Route path="register" element={<Navigate to="/login" replace />} />
                  <Route path="join" element={<Navigate to="/login" replace />} />
                  <Route path="manage/*" element={<Navigate to="/admin" replace />} />
                  <Route path="tasks" element={<Navigate to="/admin" replace />} />
                  <Route path="members" element={<Navigate to="/admin" replace />} />
                  <Route path="admin/*" element={<Navigate to="/admin" replace />} />
                  <Route path="me/*" element={<Navigate to="/me" replace />} />

                  {/* Fallback */}
                  <Route path="*" element={<Navigate to="/login" replace />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </CartProvider>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
