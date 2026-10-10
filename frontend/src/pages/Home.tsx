import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import {
  Sparkles,
  ShieldCheck,
  QrCode,
  Award,
  ArrowRight,
} from 'lucide-react';

export function Home() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="space-y-12 sm:space-y-16">
      {/* Hero Section */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-900 via-indigo-800 to-slate-900 text-white p-8 sm:p-14 shadow-2xl border border-indigo-700/40">
        <div className="absolute top-0 right-0 -mr-16 -mt-16 w-80 h-80 rounded-full bg-indigo-500/20 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 -ml-16 -mb-16 w-80 h-80 rounded-full bg-amber-500/15 blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/25 border border-indigo-400/30 text-indigo-200 text-xs font-semibold tracking-wide uppercase">
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            Official Student Association Platform
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white leading-tight">
            One Hub for Every Student Leader, Member &amp; Event
          </h1>

          <p className="text-base sm:text-lg text-indigo-100/90 leading-relaxed max-w-2xl">
            Join the campus's premier student community. Get your digital verified ID card, instant access to club privileges, workshops, and exclusive member discounts.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-4">
            {isAuthenticated ? (
              <Link to="/me">
                <Button variant="secondary" size="lg" leftIcon={<QrCode className="w-5 h-5" />}>
                  Open My Membership Card
                </Button>
              </Link>
            ) : (
              <>
                <Link to="/register">
                  <Button variant="secondary" size="lg" rightIcon={<ArrowRight className="w-5 h-5" />}>
                    Join as a Member
                  </Button>
                </Link>
                <Link to="/login">
                  <Button
                    variant="outline"
                    size="lg"
                    className="border-white/30 text-white hover:bg-white/10 hover:border-white/50 bg-white/5"
                  >
                    Sign In
                  </Button>
                </Link>
              </>
            )}
            <Link to="/join">
              <Button
                variant="ghost"
                size="lg"
                className="text-indigo-200 hover:text-white hover:bg-white/10"
              >
                Explore Plans
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Feature Highlights */}
      <section className="space-y-6">
        <div className="text-center max-w-xl mx-auto space-y-2">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Why Join SSA Hub?
          </h2>
          <p className="text-sm text-slate-600">
            Engineered from the ground up for seamless student governance and club perks.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="hover:border-indigo-200 transition-all">
            <CardContent className="p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                <QrCode className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Digital QR Verification</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Scan-ready digital membership card directly on your phone. Verified in milliseconds at club venue entries.
              </p>
            </CardContent>
          </Card>

          <Card className="hover:border-amber-200 transition-all">
            <CardContent className="p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
                <Award className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Transparent Annual Plans</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Clear pricing, instant activations, and renewal tracking with no hidden charges or surprises.
              </p>
            </CardContent>
          </Card>

          <Card className="hover:border-emerald-200 transition-all">
            <CardContent className="p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Role-Based Governance</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Dedicated tools for organizers, treasurers, and volunteers to verify identities and maintain rosters.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* CTA section */}
      <section className="rounded-3xl bg-slate-900 text-white p-8 sm:p-12 text-center max-w-4xl mx-auto space-y-6">
        <h2 className="text-2xl sm:text-3xl font-bold text-white">
          Ready to become an official member?
        </h2>
        <p className="text-sm sm:text-base text-slate-300 max-w-xl mx-auto">
          Sign up today to activate your annual membership and unlock all student privileges.
        </p>
        <div className="flex justify-center gap-4">
          <Link to="/join">
            <Button variant="secondary" size="lg">
              View Membership Plans
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
