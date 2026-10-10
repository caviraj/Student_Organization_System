import React from 'react';
import { Link } from 'react-router-dom';
import type { Fundraiser } from '../types';
import { RaisedBar } from './RaisedBar';
import { ProgressRing } from './ProgressRing';
import { OverdueCounter } from './OverdueChip';

interface FundraiserCardProps {
  fundraiser: Fundraiser;
}

export const FundraiserCard: React.FC<FundraiserCardProps> = ({ fundraiser }) => {
  const { progress } = fundraiser;
  const statusStyles = {
    planning: 'bg-amber-50 text-amber-700 border-amber-200',
    active: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    done: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  }[fundraiser.status];

  const formattedEventDate = React.useMemo(() => {
    try {
      const parts = fundraiser.event_date.split('-');
      if (parts.length === 3) {
        const date = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
      }
      return fundraiser.event_date;
    } catch {
      return fundraiser.event_date;
    }
  }, [fundraiser.event_date]);

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs hover:shadow-md transition-all duration-200 p-6 flex flex-col justify-between">
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="space-y-1">
            <span
              className={`inline-block text-[11px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${statusStyles}`}
            >
              {fundraiser.status}
            </span>
            <h3 className="text-lg font-bold text-slate-900 leading-snug">
              {fundraiser.title}
            </h3>
          </div>
          {progress && (
            <ProgressRing
              done={progress.done}
              total={progress.tasks_total}
              size={56}
              strokeWidth={5}
            />
          )}
        </div>

        <p className="text-sm text-slate-600 line-clamp-2 mb-4 leading-relaxed">
          {fundraiser.description || 'No description provided.'}
        </p>

        <div className="flex items-center gap-2 text-xs text-slate-500 mb-5">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6.75 3v2.25M17.25 3v2.253 3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25z"
            />
          </svg>
          <span>Target Date: {formattedEventDate}</span>
          {progress && progress.overdue > 0 && (
            <div className="ml-auto">
              <OverdueCounter count={progress.overdue} />
            </div>
          )}
        </div>

        {/* Financial Progress */}
        <div className="bg-slate-50/80 rounded-xl p-3.5 border border-slate-100 mb-5">
          <RaisedBar
            raised={progress?.raised ?? 0}
            goal={fundraiser.goal_amount}
          />
        </div>
      </div>

      <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
        <span className="text-xs text-slate-400 font-medium">
          {progress ? `${progress.tasks_total} total tasks` : 'Tasks loading...'}
        </span>
        <Link
          to={`/manage/fundraisers/${fundraiser.id}`}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors group"
        >
          <span>View Kanban</span>
          <svg
            className="w-4 h-4 transform group-hover:translate-x-0.5 transition-transform"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2.5"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </Link>
      </div>
    </div>
  );
};
