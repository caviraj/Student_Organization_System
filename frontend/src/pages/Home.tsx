import { Navigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import {
  GraduationCap,
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  Info,
} from 'lucide-react';

const DEPARTMENTS = [
  'AIDS',
  'CSE',
  'IT',
  'CIVIL',
  'MECH',
  'AIML',
  'BIO TECH',
  'ECE',
  'EEE',
];

export function Home() {
  const { user, isAuthenticated } = useAuth();

  // If user is already logged in, redirect directly to their respective portal
  if (isAuthenticated && user) {
    if (user.role === 'admin' || user.role === 'organizer' || user.role === 'treasurer') {
      return <Navigate to="/admin" replace />;
    }
    if (user.role === 'volunteer') {
      return <Navigate to="/staff/scan" replace />;
    }
    return <Navigate to="/me" replace />;
  }

  return (
    <div className="space-y-12 sm:space-y-16 py-4">
      {/* College Portal Hero Header */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 text-white p-8 sm:p-12 shadow-2xl border border-indigo-800/40">
        <div className="absolute top-0 right-0 -mr-16 -mt-16 w-80 h-80 rounded-full bg-indigo-500/20 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 -ml-16 -mb-16 w-80 h-80 rounded-full bg-emerald-500/15 blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-4xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/20 border border-indigo-400/30 text-indigo-200 text-xs font-semibold tracking-wide uppercase">
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            Official College Student Organization System
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white leading-tight">
            College Department Portal &amp; Student Organization System
          </h1>

          <p className="text-base sm:text-lg text-slate-300 leading-relaxed max-w-3xl">
            Centralized portal covering all 9 College Departments, department events, registered student rosters with Email IDs, and optional company products for students.
          </p>

          {/* 9 Departments Badges */}
          <div className="pt-2">
            <p className="text-xs uppercase font-bold tracking-wider text-indigo-300 mb-2.5">
              Available College Departments (9 Branches):
            </p>
            <div className="flex flex-wrap gap-2">
              {DEPARTMENTS.map((dept) => (
                <span
                  key={dept}
                  className="px-3 py-1 rounded-xl text-xs font-black bg-indigo-900/60 text-indigo-200 border border-indigo-700/60 shadow-xs"
                >
                  {dept}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 3 Dedicated Role Portals */}
      <section className="space-y-6">
        <div className="text-center max-w-2xl mx-auto space-y-2">
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">
            Select Your Portal to Login
          </h2>
          <p className="text-sm text-slate-600">
            Access is organized strictly into 3 dedicated portals: Admin, Student, and Staff.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* 1. Admin Portal Card */}
          <Card className="border-2 border-purple-200/80 hover:border-purple-500 shadow-md hover:shadow-xl transition-all rounded-3xl overflow-hidden bg-gradient-to-b from-purple-50/40 to-white flex flex-col justify-between">
            <CardContent className="p-6 sm:p-7 space-y-5 flex-1 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="w-14 h-14 rounded-2xl bg-purple-600 text-white flex items-center justify-center font-black shadow-lg shadow-purple-600/30">
                  <ShieldAlert className="w-7 h-7" />
                </div>

                <div>
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-100 text-purple-800 border border-purple-200 mb-1.5">
                    Role: Administrator
                  </div>
                  <h3 className="text-xl font-black text-slate-900">
                    Admin Portal
                  </h3>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                    Manage all 9 College Departments, department events, registered student emails, and company products.
                  </p>
                </div>

                <ul className="space-y-2 text-xs text-slate-700 pt-2 border-t border-purple-100">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />
                    <span><strong>9 Departments</strong>: AIDS, CSE, IT, CIVIL, MECH, AIML, BIO TECH, ECE, EEE</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />
                    <span><strong>Department Events</strong>: Registered student count &amp; student <strong>Email IDs</strong></span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />
                    <span><strong>Add Company Products</strong>: Add educational products for students</span>
                  </li>
                </ul>
              </div>

              <div className="pt-4 border-t border-purple-100">
                <Link to="/login" className="block">
                  <Button
                    variant="primary"
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white shadow-md shadow-purple-600/20 py-2.5 font-bold"
                    rightIcon={<ArrowRight className="w-4 h-4" />}
                  >
                    Login to Admin Portal
                  </Button>
                </Link>
                <p className="text-[11px] text-center text-slate-600 mt-2">
                  Default login: <span className="font-mono text-purple-700 font-semibold">admin@ssa.org</span>
                </p>
              </div>
            </CardContent>
          </Card>

          {/* 2. Student Portal Card */}
          <Card className="border-2 border-emerald-200/80 hover:border-emerald-500 shadow-md hover:shadow-xl transition-all rounded-3xl overflow-hidden bg-gradient-to-b from-emerald-50/40 to-white flex flex-col justify-between">
            <CardContent className="p-6 sm:p-7 space-y-5 flex-1 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="w-14 h-14 rounded-2xl bg-emerald-600 text-white flex items-center justify-center font-black shadow-lg shadow-emerald-600/30">
                  <GraduationCap className="w-7 h-7" />
                </div>

                <div>
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 mb-1.5">
                    Role: Student
                  </div>
                  <h3 className="text-xl font-black text-slate-900">
                    Student Portal
                  </h3>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                    View department events, registration status, and company products added for student needs.
                  </p>
                </div>

                <ul className="space-y-2 text-xs text-slate-700 pt-2 border-t border-emerald-100">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <span><strong>Department Events</strong>: Register for branch-specific workshops &amp; events</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <span><strong>Company Products</strong>: Products for student needs (<strong>Optional — Not compulsory to buy</strong>)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <span><strong>Digital Passes</strong>: View registered tickets &amp; QR verification</span>
                  </li>
                </ul>
              </div>

              <div className="pt-4 border-t border-emerald-100">
                <Link to="/login" className="block">
                  <Button
                    variant="primary"
                    className="w-full bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-600/20 py-2.5 font-bold"
                    rightIcon={<ArrowRight className="w-4 h-4" />}
                  >
                    Login to Student Portal
                  </Button>
                </Link>
                <p className="text-[11px] text-center text-slate-600 mt-2">
                  Default login: <span className="font-mono text-emerald-700 font-semibold">student@ssa.org</span>
                </p>
              </div>
            </CardContent>
          </Card>

          {/* 3. Staff Portal Card */}
          <Card className="border-2 border-blue-200/80 hover:border-blue-500 shadow-md hover:shadow-xl transition-all rounded-3xl overflow-hidden bg-gradient-to-b from-blue-50/40 to-white flex flex-col justify-between">
            <CardContent className="p-6 sm:p-7 space-y-5 flex-1 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="w-14 h-14 rounded-2xl bg-blue-600 text-white flex items-center justify-center font-black shadow-lg shadow-blue-600/30">
                  <ShieldCheck className="w-7 h-7" />
                </div>

                <div>
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-200 mb-1.5">
                    Role: Staff / Volunteer
                  </div>
                  <h3 className="text-xl font-black text-slate-900">
                    Staff Portal
                  </h3>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                    Verify student credentials, scan event tickets, and manage event check-ins.
                  </p>
                </div>

                <ul className="space-y-2 text-xs text-slate-700 pt-2 border-t border-blue-100">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                    <span><strong>Ticket Scanner</strong>: Instant camera &amp; barcode ticket validation</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                    <span><strong>Event Check-in</strong>: Real-time attendance tracking</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                    <span><strong>Venue Entry</strong>: Fast pass scanning for registered students</span>
                  </li>
                </ul>
              </div>

              <div className="pt-4 border-t border-blue-100">
                <Link to="/login" className="block">
                  <Button
                    variant="primary"
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-600/20 py-2.5 font-bold"
                    rightIcon={<ArrowRight className="w-4 h-4" />}
                  >
                    Login to Staff Portal
                  </Button>
                </Link>
                <p className="text-[11px] text-center text-slate-600 mt-2">
                  Default login: <span className="font-mono text-blue-700 font-semibold">staff@ssa.org</span>
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Notice Banner: Company Products Optional Policy */}
      <section className="bg-amber-50 border border-amber-200 rounded-3xl p-6 sm:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center shrink-0 mt-0.5">
            <Info className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-amber-950">
              Student Policy: Company Products are Strictly Optional
            </h3>
            <p className="text-xs sm:text-sm text-amber-800 mt-1 leading-relaxed">
              Company products added in the Admin Portal are made available solely for student academic and project convenience. It is <strong>NOT compulsory to buy</strong> any product. Students are free to buy if they require them.
            </p>
          </div>
        </div>

        <Link to="/login" className="shrink-0">
          <Button variant="outline" size="sm" className="border-amber-300 text-amber-900 hover:bg-amber-100 font-semibold">
            Go to Login
          </Button>
        </Link>
      </section>
    </div>
  );
}
