import React, { useState } from 'react';
import { Pin, Calendar, Clock, AlertTriangle, Bell, Edit3 } from 'lucide-react';
import type { Announcement, AnnouncementCategory } from '../../../types/announcements';
import { formatRelativeTime } from '../../../lib/formatRelativeTime';
import { formatDate } from '../../../lib/formatDate';
import { cn } from '../../../lib/utils';

export interface AnnouncementCardProps {
  announcement: Announcement;
  className?: string;
}

const CATEGORY_CONFIG: Record<
  AnnouncementCategory,
  { label: string; icon: React.ComponentType<{ className?: string }>; badgeClass: string }
> = {
  meeting: {
    label: 'Meeting',
    icon: Calendar,
    badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200/80',
  },
  deadline: {
    label: 'Deadline',
    icon: Clock,
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-200/80',
  },
  change: {
    label: 'Update / Change',
    icon: AlertTriangle,
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-200/80',
  },
  general: {
    label: 'General',
    icon: Bell,
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
  },
};

export function AnnouncementCard({
  announcement,
  className,
}: AnnouncementCardProps) {
  const [showRevisionTooltip, setShowRevisionTooltip] = useState(false);

  const categoryMeta = CATEGORY_CONFIG[announcement.category] || CATEGORY_CONFIG.general;
  const CategoryIcon = categoryMeta.icon;

  return (
    <article
      className={cn(
        'relative flex flex-col rounded-xl border p-5 transition-all duration-200',
        announcement.is_pinned
          ? 'border-indigo-300 bg-gradient-to-br from-indigo-50/40 via-white to-white shadow-sm ring-1 ring-indigo-200'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm',
        className
      )}
      aria-labelledby={`ann-title-${announcement.id}`}
    >
      {/* Top Header metadata */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100">
        <div className="flex flex-wrap items-center gap-2">
          {announcement.is_pinned && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-600 text-white shadow-xs"
              data-testid="pinned-badge"
            >
              <Pin className="w-3 h-3 fill-current" />
              <span>Pinned</span>
            </span>
          )}

          <span
            className={cn(
              'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border uppercase tracking-wider',
              categoryMeta.badgeClass
            )}
            data-testid={`category-badge-${announcement.category}`}
          >
            <CategoryIcon className="w-3.5 h-3.5" />
            <span>{categoryMeta.label}</span>
          </span>

          {announcement.edited_at && (
            <div className="relative inline-block">
              <button
                type="button"
                onClick={() => setShowRevisionTooltip((prev) => !prev)}
                onMouseEnter={() => setShowRevisionTooltip(true)}
                onMouseLeave={() => setShowRevisionTooltip(false)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200 transition-colors cursor-pointer"
                aria-label="View revision note"
                data-testid="edited-badge"
              >
                <Edit3 className="w-3 h-3" />
                <span>Edited</span>
              </button>

              {showRevisionTooltip && (
                <div
                  role="tooltip"
                  className="absolute left-0 bottom-full mb-1.5 z-20 w-64 p-2.5 text-xs bg-slate-900 text-white rounded-lg shadow-lg"
                >
                  <p className="font-semibold text-slate-200 mb-0.5">Last edited:</p>
                  <p className="text-slate-300">{formatDate(announcement.edited_at)}</p>
                </div>
              )}
            </div>
          )}
        </div>

        <time
          dateTime={announcement.published_at}
          title={formatDate(announcement.published_at)}
          className="text-xs text-slate-500 font-medium"
        >
          {formatRelativeTime(announcement.published_at)}
        </time>
      </div>

      {/* Main Content */}
      <div className="pt-3 flex-1 flex flex-col justify-between">
        <div>
          <h3
            id={`ann-title-${announcement.id}`}
            className="text-lg font-bold text-slate-900 tracking-tight mb-2"
          >
            {announcement.title}
          </h3>

          {/* Golden Rule: Plain text only, React escapes automatically, NO dangerouslySetInnerHTML */}
          <p
            className="text-slate-700 text-sm leading-relaxed whitespace-pre-line"
            data-testid="announcement-body"
          >
            {announcement.body_preview}
          </p>
        </div>

        {/* Footer author stamp */}
        <div className="mt-4 pt-3 border-t border-slate-50 flex items-center justify-between text-xs text-slate-400">
          <span>By {announcement.author_name ?? 'the club'}</span>
          {announcement.audience !== 'all' && (
            <span className="capitalize text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-100 font-medium">
              Audience: {announcement.audience}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
