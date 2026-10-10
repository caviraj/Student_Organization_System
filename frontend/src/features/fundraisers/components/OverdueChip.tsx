import React from 'react';

interface OverdueCounterProps {
  count: number;
  className?: string;
}

export const OverdueCounter: React.FC<OverdueCounterProps> = ({ count, className = '' }) => {
  if (count <= 0) return null;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200/80 shadow-xs ${className}`}
      role="status"
      aria-label={`${count} overdue tasks`}
    >
      <svg
        className="w-3.5 h-3.5 text-rose-600 animate-pulse"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="2.5"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
        />
      </svg>
      <span>{count} overdue</span>
    </span>
  );
};

interface DueDateChipProps {
  dueDate: string;
  isOverdue: boolean;
  className?: string;
}

export const DueDateChip: React.FC<DueDateChipProps> = ({
  dueDate,
  isOverdue,
  className = '',
}) => {
  // Format YYYY-MM-DD to readable format like "25 Oct"
  const formattedDate = React.useMemo(() => {
    try {
      const parts = dueDate.split('-');
      if (parts.length === 3) {
        const date = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
      }
      return dueDate;
    } catch {
      return dueDate;
    }
  }, [dueDate]);

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md ${
        isOverdue
          ? 'bg-rose-50 text-rose-700 font-semibold border border-rose-200'
          : 'bg-slate-100 text-slate-600'
      } ${className}`}
      aria-label={`Due date: ${formattedDate}${isOverdue ? ' (Overdue)' : ''}`}
    >
      <svg
        className={`w-3.5 h-3.5 ${isOverdue ? 'text-rose-600' : 'text-slate-400'}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M6.75 3v2.25M17.25 3v2.253 3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25z"
        />
      </svg>
      <span>{formattedDate}</span>
      {isOverdue && <span className="text-[10px] uppercase font-bold tracking-wider">Late</span>}
    </span>
  );
};
