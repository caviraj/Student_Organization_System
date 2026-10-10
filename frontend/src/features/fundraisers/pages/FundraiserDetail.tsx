import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  Calendar,
  Plus,
  Coins,
  AlertCircle,
} from 'lucide-react';
import { fundraisersApi } from '../../../api/fundraisers';
import { Button } from '../../../components/ui/Button';
import { ProgressRing } from '../components/ProgressRing';
import { RaisedBar } from '../components/RaisedBar';
import { OverdueCounter } from '../components/OverdueChip';
import { KanbanBoard } from '../components/KanbanBoard';
import { CreateTaskModal } from '../components/CreateTaskModal';
import { LogIncomeModal } from '../components/LogIncomeModal';
import { formatDate } from '../../../lib/formatDate';
import { isTaskOverdue } from '../utils/taskUtils';
import { useAuth } from '../../../context/AuthContext';
import { hasMinimumRole } from '../../../types/api';
import type { TaskStatus } from '../types';

export function FundraiserDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const isOrganizer = user ? hasMinimumRole(user.role, 'organizer') : false;

  const [isLogIncomeOpen, setIsLogIncomeOpen] = useState(false);
  const [isCreateTaskOpen, setIsCreateTaskOpen] = useState(false);
  const [createTaskInitialStatus, setCreateTaskInitialStatus] = useState<TaskStatus>('todo');

  // Fetch Fundraiser Detail
  const {
    data: fundraiser,
    isLoading: isFundraiserLoading,
    isError: isFundraiserError,
    error: fundraiserError,
  } = useQuery({
    queryKey: ['fundraiser', id],
    queryFn: () => fundraisersApi.getFundraiser(id!),
    enabled: Boolean(id),
  });

  // Fetch Tasks for this Fundraiser
  const {
    data: tasks = [],
    isLoading: isTasksLoading,
  } = useQuery({
    queryKey: ['fundraiser-tasks', id],
    queryFn: () => fundraisersApi.getFundraiserTasks(id!),
    enabled: Boolean(id),
  });

  const isLoading = isFundraiserLoading || isTasksLoading;

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-pulse space-y-6">
        <div className="h-4 bg-slate-200 rounded w-28" />
        <div className="bg-white rounded-2xl p-6 border border-slate-200 space-y-4">
          <div className="h-7 bg-slate-200 rounded w-1/3" />
          <div className="h-4 bg-slate-200 rounded w-2/3" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4 border-t border-slate-100">
            <div className="h-20 bg-slate-100 rounded-xl" />
            <div className="h-20 bg-slate-100 rounded-xl" />
            <div className="h-20 bg-slate-100 rounded-xl" />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-96">
          <div className="bg-slate-100 rounded-2xl" />
          <div className="bg-slate-100 rounded-2xl" />
          <div className="bg-slate-100 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (isFundraiserError || !fundraiser) {
    return (
      <div className="max-w-md mx-auto px-4 py-20 text-center">
        <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-3">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-slate-900 mb-1">Fundraiser Not Found</h2>
        <p className="text-sm text-slate-600 mb-6">
          {fundraiserError instanceof Error
            ? fundraiserError.message
            : 'Could not load details for this campaign.'}
        </p>
        <Link to="/manage/fundraisers">
          <Button variant="outline" size="sm">
            Back to Fundraisers
          </Button>
        </Link>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'completed':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'paused':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const tasksTotal = fundraiser.progress?.tasks_total ?? tasks.length;
  const tasksDone = fundraiser.progress?.done ?? tasks.filter((t) => t.status === 'done').length;
  const overdueCount = fundraiser.progress?.overdue ?? tasks.filter((t) => isTaskOverdue(t)).length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Back Link */}
      <div>
        <Link
          to="/manage/fundraisers"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-indigo-600 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to all campaigns
        </Link>
      </div>

      {/* Campaign Header Card */}
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200/90 shadow-sm space-y-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
          {/* Title & Metadata */}
          <div className="space-y-2 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize border ${getStatusBadge(
                  fundraiser.status
                )}`}
              >
                {fundraiser.status}
              </span>
              {fundraiser.event_date && (
                <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 font-medium bg-slate-50 px-2.5 py-0.5 rounded-full border border-slate-200">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  Target: {formatDate(fundraiser.event_date)}
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              {fundraiser.title}
            </h1>

            {fundraiser.description && (
              <p className="text-sm text-slate-600 max-w-3xl leading-relaxed">
                {fundraiser.description}
              </p>
            )}
          </div>

          {/* Action CTAs */}
          <div className="flex flex-wrap items-center gap-3 self-start">
            {isOrganizer && (
              <Button
                variant="outline"
                size="sm"
                leftIcon={<Coins className="w-4 h-4 text-emerald-600" />}
                onClick={() => setIsLogIncomeOpen(true)}
                className="border-emerald-200 hover:bg-emerald-50 text-emerald-800 font-semibold"
              >
                Log Money Raised
              </Button>
            )}
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="w-4 h-4" />}
              onClick={() => {
                setCreateTaskInitialStatus('todo');
                setIsCreateTaskOpen(true);
              }}
            >
              Add Task
            </Button>
          </div>
        </div>

        {/* Campaign Metrics Section */}
        <div className="pt-6 border-t border-slate-100 grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
          {/* Raised Bar (6 cols) */}
          <div className="md:col-span-6 bg-slate-50/70 p-4 rounded-2xl border border-slate-200/70">
            <RaisedBar
              raised={fundraiser.progress?.raised ?? 0}
              goal={fundraiser.progress?.goal ?? fundraiser.goal_amount}
            />
          </div>

          {/* Progress Ring (3 cols) */}
          <div className="md:col-span-3 flex items-center justify-center p-3 bg-slate-50/70 rounded-2xl border border-slate-200/70">
            <ProgressRing
              total={tasksTotal}
              done={tasksDone}
              size={90}
              strokeWidth={9}
            />
          </div>

          {/* Overdue Counter (3 cols) */}
          <div className="md:col-span-3 flex items-center justify-center p-4 bg-slate-50/70 rounded-2xl border border-slate-200/70 h-full">
            {overdueCount > 0 ? (
              <OverdueCounter count={overdueCount} />
            ) : (
              <div className="text-xs text-slate-500 font-medium text-center">
                <span className="text-emerald-600 font-semibold">✓ No overdue tasks</span>
                <p className="text-[11px] text-slate-400 mt-0.5">All tasks are on track</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Task Operations Kanban Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Campaign Task Board</h2>
            <p className="text-xs text-slate-500">
              Drag cards between columns or use the action menu on mobile to organize tasks.
            </p>
          </div>
          <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-3 py-1 rounded-full border border-slate-200">
            {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}
          </span>
        </div>

        {/* Kanban Board Component */}
        <KanbanBoard
          fundraiserId={id!}
          onOpenCreateTask={(col) => {
            setCreateTaskInitialStatus(col || 'todo');
            setIsCreateTaskOpen(true);
          }}
        />
      </div>

      {/* Create Task Modal */}
      <CreateTaskModal
        fundraiserId={id!}
        isOpen={isCreateTaskOpen}
        onClose={() => setIsCreateTaskOpen(false)}
        defaultStatus={createTaskInitialStatus}
      />

      {/* Log Income Modal */}
      <LogIncomeModal
        fundraiserId={id!}
        fundraiserTitle={fundraiser.title}
        isOpen={isLogIncomeOpen}
        onClose={() => setIsLogIncomeOpen(false)}
      />
    </div>
  );
}
