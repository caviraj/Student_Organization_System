import { useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { hasMinimumRole } from '../../types/api';
import { RoleBadge } from '../ui/StatusChip';
import { Button } from '../ui/Button';
import { Menu, X, LogOut, ShieldCheck, Sparkles, QrCode, Calendar } from 'lucide-react';

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
    setMobileMenuOpen(false);
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-xl text-sm font-medium transition-colors ${
      isActive
        ? 'bg-indigo-50 text-indigo-700 font-semibold'
        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
    }`;

  const isStaff = user ? hasMinimumRole(user.role, 'volunteer') : false;
  const isOrganizer = user ? hasMinimumRole(user.role, 'organizer') : false;
  const isAdmin = user?.role === 'admin';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link
            to="/"
            className="flex items-center gap-2.5 font-bold text-lg tracking-tight text-slate-900 select-none group"
          >
            <div className="w-9 h-9 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-black shadow-md shadow-indigo-600/30 group-hover:scale-105 transition-transform">
              <Sparkles className="w-5 h-5 text-amber-300" />
            </div>
            <div className="flex flex-col">
              <span className="leading-tight text-slate-900">SSA Hub</span>
              <span className="text-[10px] text-slate-500 font-medium tracking-wide">STUDENT CLUB</span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            <NavLink to="/" className={linkClass} end>
              Home
            </NavLink>
            <NavLink to="/events" className={linkClass}>
              Events
            </NavLink>
            <NavLink to="/join" className={linkClass}>
              Plans & Perks
            </NavLink>

            {isAuthenticated && (
              <>
                <NavLink to="/me" className={linkClass}>
                  My Card
                </NavLink>
                <NavLink to="/me/tickets" className={linkClass}>
                  My Tickets
                </NavLink>
              </>
            )}

            {isStaff && (
              <div className="flex items-center gap-1 pl-1 border-l border-slate-200/80">
                <NavLink to="/staff/verify-member" className={linkClass}>
                  <span className="inline-flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-indigo-600" />
                    Member Scanner
                  </span>
                </NavLink>
                <NavLink to="/staff/scan" className={linkClass}>
                  <span className="inline-flex items-center gap-1.5">
                    <QrCode className="w-4 h-4 text-indigo-600" />
                    Door Scanner
                  </span>
                </NavLink>
              </div>
            )}

            {isOrganizer && (
              <NavLink to="/manage/events" className={linkClass}>
                <span className="inline-flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-indigo-600" />
                  Manage Events
                </span>
              </NavLink>
            )}

            {isAdmin && (
              <div className="flex items-center pl-2 ml-2 border-l border-slate-200 gap-1">
                <NavLink to="/admin/members" className={linkClass}>
                  Members
                </NavLink>
                <NavLink to="/admin/plans" className={linkClass}>
                  Plans
                </NavLink>
                <NavLink to="/admin/renewals" className={linkClass}>
                  Renewals
                </NavLink>
              </div>
            )}
          </nav>

          {/* Desktop User Menu / Auth CTAs */}
          <div className="hidden md:flex items-center gap-3">
            {isAuthenticated && user ? (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 pl-2">
                  <div className="flex flex-col text-right">
                    <span className="text-xs font-semibold text-slate-900">{user.full_name}</span>
                    <span className="text-[10px] text-slate-500">{user.email}</span>
                  </div>
                  <RoleBadge role={user.role} />
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleLogout}
                  leftIcon={<LogOut className="w-4 h-4 text-slate-500" />}
                  className="text-slate-600 hover:text-rose-600 hover:bg-rose-50"
                  aria-label="Log out"
                >
                  Logout
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link to="/login">
                  <Button variant="ghost" size="sm">
                    Log in
                  </Button>
                </Link>
                <Link to="/register">
                  <Button variant="primary" size="sm">
                    Join SSA
                  </Button>
                </Link>
              </div>
            )}
          </div>

          {/* Mobile menu toggle */}
          <div className="flex md:hidden">
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
        <div className="md:hidden border-b border-slate-200 bg-white px-4 pt-3 pb-6 space-y-3">
          {isAuthenticated && user && (
            <div className="p-3 mb-2 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-900">{user.full_name}</p>
                <p className="text-xs text-slate-500">{user.email}</p>
              </div>
              <RoleBadge role={user.role} />
            </div>
          )}

          <div className="flex flex-col gap-1">
            <NavLink
              to="/"
              className={linkClass}
              end
              onClick={() => setMobileMenuOpen(false)}
            >
              Home
            </NavLink>
            <NavLink
              to="/events"
              className={linkClass}
              onClick={() => setMobileMenuOpen(false)}
            >
              Events
            </NavLink>
            <NavLink
              to="/join"
              className={linkClass}
              onClick={() => setMobileMenuOpen(false)}
            >
              Plans & Perks
            </NavLink>

            {isAuthenticated && (
              <>
                <NavLink
                  to="/me"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  My Membership Card
                </NavLink>
                <NavLink
                  to="/me/tickets"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  My Event Tickets
                </NavLink>
              </>
            )}

            {isStaff && (
              <div className="pt-2 mt-2 border-t border-slate-100 flex flex-col gap-1">
                <span className="px-3 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  Staff Scanners
                </span>
                <NavLink
                  to="/staff/verify-member"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Member Card Scanner
                </NavLink>
                <NavLink
                  to="/staff/scan"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Door Ticket Scanner
                </NavLink>
              </div>
            )}

            {isOrganizer && (
              <div className="pt-2 mt-2 border-t border-slate-100 flex flex-col gap-1">
                <span className="px-3 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  Organizer
                </span>
                <NavLink
                  to="/manage/events"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Manage Events
                </NavLink>
              </div>
            )}

            {isAdmin && (
              <div className="pt-2 mt-2 border-t border-slate-100 flex flex-col gap-1">
                <span className="px-3 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  Admin Management
                </span>
                <NavLink
                  to="/admin/members"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Member Roster
                </NavLink>
                <NavLink
                  to="/admin/plans"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Plan Editor
                </NavLink>
                <NavLink
                  to="/admin/renewals"
                  className={linkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Renewals Due
                </NavLink>
              </div>
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
              <div className="flex flex-col gap-2">
                <Link to="/login" onClick={() => setMobileMenuOpen(false)}>
                  <Button variant="outline" size="sm" className="w-full justify-center">
                    Log in
                  </Button>
                </Link>
                <Link to="/register" onClick={() => setMobileMenuOpen(false)}>
                  <Button variant="primary" size="sm" className="w-full justify-center">
                    Join SSA Hub
                  </Button>
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
