import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900 font-sans">
      <Navbar />

      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white/70 py-6 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-700">SSA Hub</span>
            <span>&bull;</span>
            <span>Student Organization System</span>
            <span>&bull;</span>
            <span className="text-indigo-600 font-medium">Phase 1 (Auth & Membership)</span>
          </div>
          <div className="flex items-center gap-1 text-slate-400">
            <span>Built with precision for student club governance</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
