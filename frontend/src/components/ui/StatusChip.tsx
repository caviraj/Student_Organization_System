import { cn } from '../../lib/utils';
import type { Role } from '../../types/api';

export interface StatusChipProps {
  status: 'active' | 'expired' | 'none' | 'success' | 'failed' | 'pending' | 'warning' | string;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function StatusChip({ status, label, size = 'md', className }: StatusChipProps) {
  const normalized = status.toLowerCase();

  const styles: Record<string, string> = {
    active: 'bg-emerald-50 text-emerald-700 border-emerald-200/80 ring-emerald-500/10',
    expired: 'bg-rose-50 text-rose-700 border-rose-200/80 ring-rose-500/10',
    none: 'bg-slate-100 text-slate-600 border-slate-200 ring-slate-500/10',
    success: 'bg-emerald-50 text-emerald-700 border-emerald-200/80 ring-emerald-500/10',
    failed: 'bg-rose-50 text-rose-700 border-rose-200/80 ring-rose-500/10',
    fail: 'bg-rose-50 text-rose-700 border-rose-200/80 ring-rose-500/10',
    pending: 'bg-amber-50 text-amber-700 border-amber-200/80 ring-amber-500/10',
    warning: 'bg-amber-50 text-amber-700 border-amber-200/80 ring-amber-500/10',
  };

  const dotColors: Record<string, string> = {
    active: 'bg-emerald-500',
    expired: 'bg-rose-500',
    none: 'bg-slate-400',
    success: 'bg-emerald-500',
    failed: 'bg-rose-500',
    fail: 'bg-rose-500',
    pending: 'bg-amber-500',
    warning: 'bg-amber-500',
  };

  const sizes = {
    sm: 'text-xs px-2 py-0.5 gap-1.5',
    md: 'text-xs px-2.5 py-1 gap-1.5 font-medium',
    lg: 'text-sm px-3.5 py-1.5 gap-2 font-semibold',
  };

  const currentStyle = styles[normalized] || 'bg-slate-50 text-slate-700 border-slate-200 ring-slate-500/10';
  const currentDot = dotColors[normalized] || 'bg-slate-400';

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border ring-1 ring-inset uppercase tracking-wider',
        currentStyle,
        sizes[size],
        className
      )}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', currentDot)} />
      <span>{label || status}</span>
    </span>
  );
}

export function RoleBadge({ role, className }: { role: Role; className?: string }) {
  const roleStyles: Record<Role, string> = {
    admin: 'bg-purple-100 text-purple-800 border-purple-200',
    treasurer: 'bg-amber-100 text-amber-800 border-amber-200',
    organizer: 'bg-indigo-100 text-indigo-800 border-indigo-200',
    volunteer: 'bg-blue-100 text-blue-800 border-blue-200',
    member: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    guest: 'bg-slate-100 text-slate-700 border-slate-200',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border',
        roleStyles[role] || roleStyles.guest,
        className
      )}
    >
      {role}
    </span>
  );
}
