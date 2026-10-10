import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../types/api';
import { UserPlus, Mail, Lock, User, Phone, GraduationCap, Calendar } from 'lucide-react';
import { z } from 'zod';

const registerSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters long'),
  full_name: z.string().min(2, 'Full name is required'),
  phone: z.string().optional(),
  department: z.string().optional(),
  year: z.coerce.number().min(1, 'Year must be 1 to 5').max(5, 'Year must be 1 to 5').optional(),
});

export function Register() {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    full_name: '',
    phone: '',
    department: '',
    year: '',
  });

  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();
  const { success } = useToast();

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (formErrors[field]) {
      setFormErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setApiError(null);

    const validation = registerSchema.safeParse({
      ...formData,
      year: formData.year ? Number(formData.year) : undefined,
    });

    if (!validation.success) {
      const fieldErrors: Record<string, string> = {};
      validation.error.issues.forEach((issue) => {
        const fieldName = String(issue.path[0]);
        fieldErrors[fieldName] = issue.message;
      });
      setFormErrors(fieldErrors);
      return;
    }

    setIsLoading(true);
    try {
      await register({
        email: formData.email,
        password: formData.password,
        full_name: formData.full_name,
        phone: formData.phone || undefined,
        department: formData.department || undefined,
        year: formData.year ? Number(formData.year) : undefined,
      });

      success('Account created successfully! Choose a plan to activate your membership.');
      navigate('/join');
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setApiError(err.message);
      } else {
        setApiError('An unexpected error occurred during registration.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto pt-4 sm:pt-8">
      <Card className="border-slate-200/90 shadow-xl">
        <CardHeader className="text-center space-y-2 pb-6 border-b border-slate-100">
          <div className="mx-auto w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center font-black shadow-xs">
            <UserPlus className="w-6 h-6" />
          </div>
          <CardTitle className="text-2xl font-bold">Join SSA Hub</CardTitle>
          <CardDescription>Create your student account to activate club membership</CardDescription>
        </CardHeader>

        <CardContent className="p-6 pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {apiError && (
              <div
                role="alert"
                className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium animate-in fade-in"
              >
                {apiError}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                label="Full Name"
                required
                placeholder="Aarav Patel"
                value={formData.full_name}
                onChange={(e) => handleChange('full_name', e.target.value)}
                error={formErrors.full_name}
                leftIcon={<User className="w-4 h-4" />}
              />

              <Input
                label="Email Address"
                type="email"
                required
                placeholder="aarav@campus.edu"
                value={formData.email}
                onChange={(e) => handleChange('email', e.target.value)}
                error={formErrors.email}
                leftIcon={<Mail className="w-4 h-4" />}
              />
            </div>

            <Input
              label="Password"
              type="password"
              required
              hint="Must be at least 8 characters"
              placeholder="••••••••"
              value={formData.password}
              onChange={(e) => handleChange('password', e.target.value)}
              error={formErrors.password}
              leftIcon={<Lock className="w-4 h-4" />}
            />

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
              <Input
                label="Phone (Optional)"
                type="tel"
                placeholder="+91 98765 43210"
                value={formData.phone}
                onChange={(e) => handleChange('phone', e.target.value)}
                error={formErrors.phone}
                leftIcon={<Phone className="w-4 h-4" />}
              />

              <Input
                label="Department"
                placeholder="CSE / ECE / Mech"
                value={formData.department}
                onChange={(e) => handleChange('department', e.target.value)}
                error={formErrors.department}
                leftIcon={<GraduationCap className="w-4 h-4" />}
              />

              <Input
                label="Year of Study"
                type="number"
                min={1}
                max={5}
                placeholder="1 - 4"
                value={formData.year}
                onChange={(e) => handleChange('year', e.target.value)}
                error={formErrors.year}
                leftIcon={<Calendar className="w-4 h-4" />}
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full mt-4"
              isLoading={isLoading}
            >
              Create Account &amp; Proceed to Plans
            </Button>
          </form>

          <div className="mt-6 text-center text-xs text-slate-500">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
              Sign In
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
