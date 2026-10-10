import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../types/api';
import { LogIn, Mail, Lock, GraduationCap, ShieldCheck, ShieldAlert, Sparkles } from 'lucide-react';

type RoleOption = 'student' | 'staff' | 'admin';

interface RoleConfig {
  id: RoleOption;
  label: string;
  tagline: string;
  defaultEmail: string;
  icon: typeof GraduationCap;
  badge: string;
  accentBg: string;
  accentBorder: string;
  accentText: string;
  activeRing: string;
  redirectDefault: string;
}

const ROLE_CONFIGS: Record<RoleOption, RoleConfig> = {
  student: {
    id: 'student',
    label: 'Student',
    tagline: 'Department events & company products (optional)',
    defaultEmail: 'student@ssa.org',
    icon: GraduationCap,
    badge: 'Student Portal',
    accentBg: 'bg-emerald-50',
    accentBorder: 'border-emerald-300',
    accentText: 'text-emerald-700',
    activeRing: 'ring-2 ring-emerald-500 border-emerald-500 bg-emerald-50/50',
    redirectDefault: '/me',
  },
  staff: {
    id: 'staff',
    label: 'Staff',
    tagline: 'Ticket check-in & desk operations',
    defaultEmail: 'staff@ssa.org',
    icon: ShieldCheck,
    badge: 'Staff Portal',
    accentBg: 'bg-blue-50',
    accentBorder: 'border-blue-300',
    accentText: 'text-blue-700',
    activeRing: 'ring-2 ring-blue-500 border-blue-500 bg-blue-50/50',
    redirectDefault: '/staff/scan',
  },
  admin: {
    id: 'admin',
    label: 'Admin',
    tagline: '9 College Departments & Company Products',
    defaultEmail: 'admin@ssa.org',
    icon: ShieldAlert,
    badge: 'Admin Portal',
    accentBg: 'bg-purple-50',
    accentBorder: 'border-purple-300',
    accentText: 'text-purple-700',
    activeRing: 'ring-2 ring-purple-500 border-purple-500 bg-purple-50/50',
    redirectDefault: '/admin',
  },
};

export function Login() {
  const [selectedRole, setSelectedRole] = useState<RoleOption>('student');
  const [email, setEmail] = useState('student@ssa.org');
  const [password, setPassword] = useState('Passw0rd!');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { success } = useToast();

  const currentRoleConfig = ROLE_CONFIGS[selectedRole];
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

  const handleOneClickLogin = () => {
    executeLogin(currentRoleConfig.defaultEmail, 'Passw0rd!');
  };

  const RoleIcon = currentRoleConfig.icon;

  return (
    <div className="max-w-lg mx-auto pt-4 sm:pt-8 px-2 sm:px-0">
      <Card className="border-slate-200/90 shadow-xl overflow-hidden">
        <CardHeader className="text-center space-y-2 pb-5 border-b border-slate-100 bg-slate-50/50">
          <div
            className={`mx-auto w-12 h-12 rounded-2xl ${currentRoleConfig.accentBg} border ${currentRoleConfig.accentBorder} ${currentRoleConfig.accentText} flex items-center justify-center font-black shadow-xs transition-colors`}
          >
            <RoleIcon className="w-6 h-6" />
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight text-slate-900">
            Sign In to SSA Hub
          </CardTitle>
          <CardDescription className="text-slate-500 text-sm">
            Choose your login option: <span className="font-semibold text-slate-700">Admin</span>,{' '}
            <span className="font-semibold text-slate-700">Student</span>, or{' '}
            <span className="font-semibold text-slate-700">Staff</span>
          </CardDescription>
        </CardHeader>

        <CardContent className="p-5 sm:p-6 space-y-6">
          {/* 3 Role Selection Options */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2.5">
              Select Login Role
            </label>
            <div className="grid grid-cols-3 gap-2.5">
              {(['student', 'staff', 'admin'] as RoleOption[]).map((roleKey) => {
                const config = ROLE_CONFIGS[roleKey];
                const Icon = config.icon;
                const isSelected = selectedRole === roleKey;

                return (
                  <button
                    key={roleKey}
                    type="button"
                    onClick={() => handleRoleSelect(roleKey)}
                    className={`flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all cursor-pointer ${
                      isSelected
                        ? `${config.activeRing} shadow-sm font-semibold`
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 text-slate-700'
                    }`}
                  >
                    <div
                      className={`w-9 h-9 rounded-lg flex items-center justify-center mb-1.5 ${
                        isSelected ? `${config.accentBg} ${config.accentText}` : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                    </div>
                    <span className="text-sm font-medium">{config.label}</span>
                    <span className="text-[10px] text-slate-400 mt-0.5 line-clamp-1">
                      {roleKey === 'student' ? 'Student' : roleKey === 'staff' ? 'Staff' : 'Admin'}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Role Banner */}
          <div
            className={`p-3 rounded-xl border flex items-center justify-between text-xs ${currentRoleConfig.accentBg} ${currentRoleConfig.accentBorder}`}
          >
            <div className="flex items-center space-x-2">
              <RoleIcon className={`w-4 h-4 ${currentRoleConfig.accentText}`} />
              <span className={`font-semibold ${currentRoleConfig.accentText}`}>
                {currentRoleConfig.label} Login Option Selected
              </span>
            </div>
            <span className="text-[11px] text-slate-500 hidden sm:inline">
              Default: {currentRoleConfig.defaultEmail}
            </span>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {errorMsg && (
              <div
                role="alert"
                className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium animate-in fade-in"
              >
                {errorMsg}
              </div>
            )}

            <Input
              label={`${currentRoleConfig.label} Email Address`}
              type="email"
              required
              placeholder={currentRoleConfig.defaultEmail}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              leftIcon={<Mail className="w-4 h-4" />}
              autoComplete="email"
            />

            <Input
              label="Password"
              type="password"
              required
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              leftIcon={<Lock className="w-4 h-4" />}
              autoComplete="current-password"
            />

            <div className="space-y-2.5 pt-1">
              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="w-full font-semibold shadow-sm"
                isLoading={isLoading}
              >
                <LogIn className="w-4 h-4 mr-2" />
                Sign In as {currentRoleConfig.label}
              </Button>

              <button
                type="button"
                onClick={handleOneClickLogin}
                disabled={isLoading}
                className="w-full py-2.5 px-3 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-medium flex items-center justify-center transition-colors cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-500 mr-1.5" />
                1-Click Quick Login as {currentRoleConfig.label} ({currentRoleConfig.defaultEmail})
              </button>
            </div>
          </form>

          {/* Explicit 3 Role Credentials Reference */}
          <div className="pt-4 border-t border-slate-100">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5 text-center">
              Available Login Roles (Password: Passw0rd!)
            </p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <button
                type="button"
                onClick={() => handleRoleSelect('admin')}
                className={`p-2.5 rounded-xl border text-center transition-all cursor-pointer ${
                  selectedRole === 'admin'
                    ? 'border-purple-400 bg-purple-50 text-purple-900 font-bold ring-2 ring-purple-300'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'
                }`}
              >
                <span className="block font-bold">Admin</span>
                <span className="text-[10px] text-slate-400">admin@ssa.org</span>
              </button>

              <button
                type="button"
                onClick={() => handleRoleSelect('student')}
                className={`p-2.5 rounded-xl border text-center transition-all cursor-pointer ${
                  selectedRole === 'student'
                    ? 'border-emerald-400 bg-emerald-50 text-emerald-900 font-bold ring-2 ring-emerald-300'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'
                }`}
              >
                <span className="block font-bold">Student</span>
                <span className="text-[10px] text-slate-400">student@ssa.org</span>
              </button>

              <button
                type="button"
                onClick={() => handleRoleSelect('staff')}
                className={`p-2.5 rounded-xl border text-center transition-all cursor-pointer ${
                  selectedRole === 'staff'
                    ? 'border-blue-400 bg-blue-50 text-blue-900 font-bold ring-2 ring-blue-300'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'
                }`}
              >
                <span className="block font-bold">Staff</span>
                <span className="text-[10px] text-slate-400">staff@ssa.org</span>
              </button>
            </div>
          </div>

          <div className="text-center text-xs text-slate-400 pt-1">
            College Organization System &bull; Secure Access for Admin, Student &amp; Staff
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
