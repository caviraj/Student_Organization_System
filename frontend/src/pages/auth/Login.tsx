import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../types/api';
import { Interactive3DCharacters } from '../../components/auth/Interactive3DCharacters';
import { Eye, EyeOff, GraduationCap, ShieldCheck, ShieldAlert, LogIn } from 'lucide-react';

type RoleOption = 'student' | 'staff' | 'admin';

interface RoleConfig {
  id: RoleOption;
  label: string;
  defaultEmail: string;
  icon: typeof GraduationCap;
  redirectDefault: string;
  colorClass: string;
}

const ROLE_CONFIGS: Record<RoleOption, RoleConfig> = {
  student: {
    id: 'student',
    label: 'Student',
    defaultEmail: 'student@ssa.org',
    icon: GraduationCap,
    redirectDefault: '/me',
    colorClass: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  },
  staff: {
    id: 'staff',
    label: 'Staff',
    defaultEmail: 'staff@ssa.org',
    icon: ShieldCheck,
    redirectDefault: '/staff/scan',
    colorClass: 'text-blue-700 bg-blue-50 border-blue-200',
  },
  admin: {
    id: 'admin',
    label: 'Admin',
    defaultEmail: 'admin@ssa.org',
    icon: ShieldAlert,
    redirectDefault: '/admin',
    colorClass: 'text-purple-700 bg-purple-50 border-purple-200',
  },
};

export function Login() {
  const [selectedRole, setSelectedRole] = useState<RoleOption>('student');
  const [email, setEmail] = useState('student@ssa.org');
  const [password, setPassword] = useState('Passw0rd!');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // States to trigger 3D characters' eyes closing when entering/hovering/focusing password
  const [isPasswordHovered, setIsPasswordHovered] = useState(false);
  const [isPasswordFocused, setIsPasswordFocused] = useState(false);

  const isPasswordActive = isPasswordHovered || isPasswordFocused;

  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { success } = useToast();

  const queryRedirect = searchParams.get('redirect');

  const handleRoleSelect = (role: RoleOption) => {
    setSelectedRole(role);
    setEmail(ROLE_CONFIGS[role].defaultEmail);
    setPassword('Passw0rd!');
    setErrorMsg(null);
  };

  const executeLogin = async (loginEmail: string, loginPass: string) => {
    if (!loginEmail || !loginPass) {
      setErrorMsg('Please enter both email and password.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);

    try {
      await login({ email: loginEmail, password: loginPass });
      success(`Welcome to SSA Hub (${ROLE_CONFIGS[selectedRole].label})!`);
      const targetPath = queryRedirect || ROLE_CONFIGS[selectedRole].redirectDefault;
      navigate(targetPath, { replace: true });
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to sign in. Please check your credentials.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    executeLogin(email, password);
  };

  return (
    <div className="w-full flex items-center justify-center py-4 sm:py-8 px-2 sm:px-4">
      {/* Main Split Login Card matching user image */}
      <div className="bg-white rounded-[32px] sm:rounded-[36px] shadow-2xl border border-slate-200/90 overflow-hidden max-w-5xl w-full grid grid-cols-1 lg:grid-cols-2 transition-all">
        {/* ================= LEFT SIDE: INTERACTIVE 3D ANIMATION TOYS ================= */}
        <div className="bg-[#eef1f6] border-b lg:border-b-0 lg:border-r border-slate-200/80 flex flex-col justify-between relative overflow-hidden">
          <Interactive3DCharacters isPasswordActive={isPasswordActive} />
        </div>

        {/* ================= RIGHT SIDE: AUTHENTICATION FORM ================= */}
        <div className="p-6 sm:p-10 lg:p-12 flex flex-col justify-center bg-white">
          <div className="max-w-md w-full mx-auto space-y-6">
            {/* Header: Sparkle Icon + Title */}
            <div className="text-center space-y-2">
              <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-slate-100 text-slate-900 mb-1">
                {/* 4-pointed sparkle icon from screenshot */}
                <svg
                  viewBox="0 0 24 24"
                  className="w-5 h-5 fill-slate-900"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path d="M12 0L14.59 9.41L24 12L14.59 14.59L12 24L9.41 14.59L0 12L9.41 9.41L12 0Z" />
                </svg>
              </div>
              <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                Welcome back!
              </h1>
              <p className="text-sm text-slate-500 font-medium">
                Please enter your details
              </p>
            </div>

            {/* Role Switcher Tabs */}
            <div className="bg-slate-100 p-1.5 rounded-2xl flex items-center gap-1">
              {(['student', 'staff', 'admin'] as RoleOption[]).map((r) => {
                const config = ROLE_CONFIGS[r];
                const Icon = config.icon;
                const isSelected = selectedRole === r;

                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => handleRoleSelect(r)}
                    className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{config.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Error Message */}
            {errorMsg && (
              <div
                role="alert"
                className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium animate-in fade-in"
              >
                {errorMsg}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Email Input */}
              <div className="space-y-1.5 text-left">
                <label className="block text-xs font-bold text-slate-700">
                  Email
                </label>
                <input
                  type="email"
                  required
                  placeholder="anna@gmail.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/15 focus:border-slate-800 text-sm font-medium text-slate-900 placeholder:text-slate-400 transition-all bg-white"
                />
              </div>

              {/* Password Input with eye toggle and mouse enter/leave tracking */}
              <div
                className="space-y-1.5 text-left"
                onMouseEnter={() => setIsPasswordHovered(true)}
                onMouseLeave={() => setIsPasswordHovered(false)}
              >
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-bold text-slate-700">
                    Password
                  </label>
                  {isPasswordActive && (
                    <span className="text-[10px] text-amber-600 font-semibold flex items-center gap-1 animate-in fade-in">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping" />
                      Eyes hidden for privacy
                    </span>
                  )}
                </div>

                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    placeholder="••••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onFocus={() => setIsPasswordFocused(true)}
                    onBlur={() => setIsPasswordFocused(false)}
                    autoComplete="current-password"
                    className="w-full pl-4 pr-11 py-3 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/15 focus:border-slate-800 text-sm font-medium text-slate-900 placeholder:text-slate-400 transition-all bg-white"
                  />
                  <button
                    type="button"
                    tabIndex={-1}
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Remember for 30 days & Forgot Password Row */}
              <div className="flex items-center justify-between pt-1 text-xs">
                <label className="flex items-center gap-2 cursor-pointer select-none text-slate-600 font-medium">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-800 focus:ring-1 cursor-pointer"
                  />
                  <span>Remember for 30 days</span>
                </label>

                <button
                  type="button"
                  onClick={() => {
                    setPassword('Passw0rd!');
                    success('Demo password pre-filled: Passw0rd!');
                  }}
                  className="font-semibold text-slate-500 hover:text-slate-800 transition-colors"
                >
                  Forgot password?
                </button>
              </div>

              {/* Primary Dark Pill Button matching screenshot */}
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3.5 px-6 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white font-bold text-sm shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 active:scale-[0.98] cursor-pointer disabled:opacity-60"
              >
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Signing In...</span>
                  </>
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    <span>Log In</span>
                  </>
                )}
              </button>

              {/* Log in with Google button */}
              <button
                type="button"
                onClick={() => {
                  executeLogin(ROLE_CONFIGS[selectedRole].defaultEmail, 'Passw0rd!');
                }}
                disabled={isLoading}
                className="w-full py-3 px-4 rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center justify-center gap-2.5 transition-colors cursor-pointer shadow-xs"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
                <span>Log in with Google</span>
              </button>
            </form>

            {/* Quick 1-Click Role Login Shortcuts */}
            <div className="pt-2 flex items-center justify-center gap-2 text-[11px] text-slate-500">
              <span className="text-slate-400">Quick Test:</span>
              <button
                type="button"
                onClick={() => {
                  setSelectedRole('admin');
                  executeLogin('admin@ssa.org', 'Passw0rd!');
                }}
                className="hover:text-purple-700 font-semibold cursor-pointer underline underline-offset-2"
              >
                Admin
              </button>
              <span>&bull;</span>
              <button
                type="button"
                onClick={() => {
                  setSelectedRole('staff');
                  executeLogin('staff@ssa.org', 'Passw0rd!');
                }}
                className="hover:text-blue-700 font-semibold cursor-pointer underline underline-offset-2"
              >
                Operator
              </button>
              <span>&bull;</span>
              <button
                type="button"
                onClick={() => {
                  setSelectedRole('student');
                  executeLogin('student@ssa.org', 'Passw0rd!');
                }}
                className="hover:text-emerald-700 font-semibold cursor-pointer underline underline-offset-2"
              >
                Student
              </button>
            </div>

            {/* Sign Up Footer Link */}
            <div className="text-center text-xs text-slate-500 pt-2 border-t border-slate-100">
              Don't have an account?{' '}
              <Link to="/register" className="font-bold text-slate-900 hover:underline">
                Sign Up
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
