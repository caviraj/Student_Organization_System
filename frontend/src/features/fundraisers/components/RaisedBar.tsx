import React from 'react';
import { formatINR } from '../../../lib/formatINR';
import { calculateRaisedPercentage } from '../utils/taskUtils';

interface RaisedBarProps {
  raised: number; // in paise
  goal: number; // in paise
  className?: string;
  showLabels?: boolean;
}

export const RaisedBar: React.FC<RaisedBarProps> = ({
  raised,
  goal,
  className = '',
  showLabels = true,
}) => {
  const percentage = calculateRaisedPercentage(raised, goal);
  const visualFill = Math.min(100, Math.max(0, percentage));
  const isGoalReached = percentage >= 100;

  return (
    <div className={`space-y-2 ${className}`}>
      {showLabels && (
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-baseline gap-1.5">
            <span className="font-bold text-slate-900">{formatINR(raised)}</span>
            <span className="text-slate-500 text-xs">raised of {formatINR(goal)}</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`font-bold text-xs px-2 py-0.5 rounded-full ${
                isGoalReached
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'bg-indigo-50 text-indigo-700'
              }`}
            >
              {percentage}%
            </span>
            {isGoalReached && (
              <span className="hidden sm:inline-block text-[11px] font-semibold text-emerald-600">
                Goal reached!
              </span>
            )}
          </div>
        </div>
      )}

      {/* Progress Bar Track */}
      <div
        className="h-3 w-full bg-slate-100 rounded-full overflow-hidden p-0.5"
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Fundraiser progress: ${formatINR(raised)} of ${formatINR(goal)} (${percentage}%)`}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${
            isGoalReached
              ? 'bg-gradient-to-r from-emerald-500 to-teal-500 shadow-sm'
              : 'bg-gradient-to-r from-indigo-500 to-indigo-600'
          }`}
          style={{ width: `${visualFill}%` }}
        />
      </div>
    </div>
  );
};
