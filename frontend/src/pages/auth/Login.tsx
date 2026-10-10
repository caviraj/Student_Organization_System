import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../types/api';
import { LogIn, Mail, Lock } from 'lucide-react';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { success } = useToast();

  const redirectPath = searchParams.get('redirect') || '/me';

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg('Please enter both email and password.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);

    try {
      await login({ email, password });
      success('Welcome back to SSA Hub!');
      navigate(redirectPath, { replace: true });
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

  const handleQuickFill = (demoEmail: string) => {
    setEmail(demoEmail);
    setPassword('Passw0rd!');
    setErrorMsg(null);
  };

  return (
    <div className="max-w-md mx-auto pt-6 sm:pt-10">
      <Card className="border-slate-200/90 shadow-xl">
        <CardHeader className="text-center space-y-2 pb-6 border-b border-slate-100">
          <div className="mx-auto w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center font-black shadow-xs">
            <LogIn className="w-6 h-6" />
          </div>
          <CardTitle className="text-2xl font-bold">Welcome Back</CardTitle>
          <CardDescription>Sign in to your SSA student account</CardDescription>
        </CardHeader>

        <CardContent className="p-6 pt-6">
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
              label="Email Address"
              type="email"
              required
              placeholder="you@campus.edu"
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

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full mt-2"
              isLoading={isLoading}
            >
              Sign In
            </Button>
          </form>

          {/* Quick Demo Fill Buttons */}
          <div className="mt-8 pt-6 border-t border-slate-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 text-center">
              Quick Test Accounts (Password: Passw0rd!)
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => handleQuickFill('admin@ssa.org')}
                className="px-2.5 py-1.5 rounded-lg border border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 font-medium text-left transition-colors"
              >
                Dr. Sarah (Admin)
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('member@ssa.org')}
                className="px-2.5 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 font-medium text-left transition-colors"
              >
                Aarav (Member)
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('volunteer@ssa.org')}
                className="px-2.5 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 font-medium text-left transition-colors"
              >
                Vikram (Staff)
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('expiring@ssa.org')}
                className="px-2.5 py-1.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 font-medium text-left transition-colors"
              >
                Diya (Expiring 10d)
              </button>
            </div>
          </div>

          <div className="mt-6 text-center text-xs text-slate-500">
            New to SSA Hub?{' '}
            <Link to="/register" className="font-semibold text-indigo-600 hover:text-indigo-700">
              Create an account
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
