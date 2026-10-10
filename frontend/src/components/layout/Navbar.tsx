import { useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { RoleBadge } from '../ui/StatusChip';
import { Button } from '../ui/Button';
import {
  Menu,
  X,
  LogOut,
  Building2,
  Package,
  GraduationCap,
  ShieldCheck,
  LogIn,
  ShoppingBag,
} from 'lucide-react';
import { useCart } from '../../features/shop/context/CartContext';
import { CartDrawer } from '../../features/shop/components/CartDrawer';

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const { itemCount, setIsCartOpen } = useCart();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
    setMobileMenuOpen(false);
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-semibold transition-all ${
      isActive
        ? 'bg-indigo-600 text-white shadow-xs'
        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
    }`;

  const isAdmin = user?.role === 'admin';
  const isStudent = user?.role === 'member';
  const isStaff = user?.role === 'volunteer' || user?.role === 'organizer';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200/80 bg-white/95 backdrop-blur-md shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo / Brand */}
          <Link
            to={isAdmin ? '/admin' : isStudent ? '/me' : isStaff ? '/staff/scan' : '/login'}
            className="flex items-center gap-2.5 select-none group"
          >
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-700 to-indigo-500 text-white flex items-center justify-center font-black shadow-md shadow-indigo-600/20 group-hover:scale-105 transition-transform">
              <Building2 className="w-5 h-5 text-indigo-100" />
            </div>
            <div className="flex flex-col">
              <span className="font-extrabold text-base tracking-tight text-slate-900 leading-tight">
                College Org System
              </span>
              <span className="text-[10px] text-indigo-600 font-semibold tracking-wider uppercase">
                {isAdmin ? 'Admin Console' : isStudent ? 'Student Portal' : isStaff ? 'Staff Portal' : 'Admin • Student • Staff'}
              </span>
            </div>
          </Link>

          {/* Desktop Navigation - Role-Specific Options Only */}
          <nav className="hidden md:flex items-center gap-1.5">
            {isAdmin && (
              <>
                <NavLink to="/admin" className={linkClass} end>
                  <Building2 className="w-4 h-4" />
                  College Departments (9 Branches)
                </NavLink>
                <NavLink to="/admin?tab=products" className={linkClass}>
                  <Package className="w-4 h-4" />
                  Company Products
                </NavLink>
              </>
            )}

            {isStudent && (
              <>
                <NavLink to="/me" className={linkClass} end>
                  <GraduationCap className="w-4 h-4" />
                  Student Portal (Departments & Events)
                </NavLink>
                <NavLink to="/me#company-products" className={linkClass}>
                  <Package className="w-4 h-4" />
                  Company Products (Optional)
                </NavLink>
              </>
            )}

            {isStaff && (
              <>
                <NavLink to="/staff/scan" className={linkClass}>
                  <ShieldCheck className="w-4 h-4" />
                  Staff Ticket Scanner
                </NavLink>
              </>
            )}

            {!isAuthenticated && (
              <>
                <NavLink to="/login" className={linkClass}>
                  <LogIn className="w-4 h-4" />
                  Login (Admin / Student / Staff)
                </NavLink>
              </>
            )}
          </nav>

          {/* Desktop User Menu & Actions */}
          <div className="hidden md:flex items-center gap-3">
            {/* Student Cart Trigger for Company Products */}
            {isStudent && (
              <button
                type="button"
                onClick={() => setIsCartOpen(true)}
                className="relative p-2.5 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label={`Open shopping cart with ${itemCount} items`}
                title="Cart (Company Products)"
              >
                <ShoppingBag className="w-5 h-5 text-indigo-600" />
                {itemCount > 0 && (
                  <span className="absolute -top-1 -right-1 inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-indigo-600 text-[11px] font-bold text-white shadow-sm ring-2 ring-white">
                    {itemCount}
                  </span>
                )}
              </button>
            )}

            {isAuthenticated && user ? (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2.5 pl-3 border-l border-slate-200">
                  <div className="flex flex-col text-right">
                    <span className="text-xs font-bold text-slate-900">{user.full_name}</span>
                    <span className="text-[10px] text-slate-500 font-medium">{user.email}</span>
                  </div>
                  <RoleBadge role={user.role} />
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleLogout}
                  leftIcon={<LogOut className="w-4 h-4 text-rose-500" />}
                  className="text-slate-600 hover:text-rose-600 hover:bg-rose-50"
                  aria-label="Log out"
                >
                  Logout
                </Button>
              </div>
            ) : (
              <Link to="/login">
                <Button variant="primary" size="sm" leftIcon={<LogIn className="w-4 h-4" />}>
                  Sign In
                </Button>
              </Link>
            )}
          </div>

          {/* Mobile Menu Button */}
          <div className="flex items-center gap-2 md:hidden">
            {isStudent && (
              <button
                type="button"
                onClick={() => setIsCartOpen(true)}
                className="relative p-2 rounded-xl text-slate-600 hover:bg-slate-100"
                aria-label="Open cart"
              >
                <ShoppingBag className="w-5 h-5 text-indigo-600" />
                {itemCount > 0 && (
                  <span className="absolute -top-1 -right-1 inline-flex items-center justify-center min-w-4 h-4 px-1 rounded-full bg-indigo-600 text-[10px] font-bold text-white">
                    {itemCount}
                  </span>
                )}
              </button>
            )}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-xl text-slate-600 hover:bg-slate-100 focus:outline-none"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-slate-200 bg-white px-4 pt-3 pb-6 space-y-3 shadow-lg">
          {isAuthenticated && user && (
            <div className="p-3 mb-2 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold text-slate-900">{user.full_name}</p>
                <p className="text-xs text-slate-500">{user.email}</p>
              </div>
              <RoleBadge role={user.role} />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            {isAdmin && (
              <>
                <NavLink
                  to="/admin"
                  className={linkClass}
                  end
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <Building2 className="w-4 h-4" />
                  College Departments (9 Branches)
                </NavLink>
                <NavLink
                  to="/admin?tab=products"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <Package className="w-4 h-4" />
                  Company Products
                </NavLink>
              </>
            )}

            {isStudent && (
              <>
                <NavLink
                  to="/me"
                  className={linkClass}
                  end
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <GraduationCap className="w-4 h-4" />
                  Student Portal (Departments & Events)
                </NavLink>
                <NavLink
                  to="/me#company-products"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <Package className="w-4 h-4" />
                  Company Products (Optional)
                </NavLink>
              </>
            )}

            {isStaff && (
              <>
                <NavLink
                  to="/staff/scan"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <ShieldCheck className="w-4 h-4" />
                  Staff Ticket Scanner
                </NavLink>
              </>
            )}

            {!isAuthenticated && (
              <>
                <NavLink
                  to="/login"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <LogIn className="w-4 h-4" />
                  Login (Admin / Student / Staff)
                </NavLink>
              </>
            )}
          </div>

          <div className="pt-3 border-t border-slate-100">
            {isAuthenticated ? (
              <Button
                variant="danger"
                size="sm"
                onClick={handleLogout}
                className="w-full justify-center"
              >
                Log Out
              </Button>
            ) : (
              <Link to="/login" onClick={() => setMobileMenuOpen(false)}>
                <Button variant="primary" size="sm" className="w-full justify-center">
                  Sign In
                </Button>
              </Link>
            )}
          </div>
        </div>
      )}

      {/* Cart Drawer for student optional purchases */}
      <CartDrawer />
    </header>
  );
}
