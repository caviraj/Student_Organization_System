import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckSquare, Search, AlertCircle } from 'lucide-react';
import { fundraisersApi } from '../../../api/fundraisers';
import { DueDateChip } from '../components/OverdueChip';
import { isTaskOverdue } from '../utils/taskUtils';
import { Button } from '../../../components/ui/Button';
import { useToast } from '../../../components/ui/Toast';
import type { Task, TaskStatus } from '../types';

export function MyTasks() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');

  const {
    data: tasks = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['my-tasks'],
    queryFn: () => fundraisersApi.getMyTasks(),
  });

  const patchMutation = useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: string; newStatus: TaskStatus }) =>
      fundraisersApi.patchTask(taskId, { status: newStatus }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['my-tasks'] });
      addToast({
        type: 'success',
        title: 'Task Updated',
        message: `Task status updated to ${updated.status}.`,
      });
    },
    onError: (err: any) => {
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: err?.message || 'Could not update task status',
      });
    },
  });

  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      const matchesSearch =
        t.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (t.description && t.description.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchesStatus = statusFilter === 'all' || t.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [tasks, searchTerm, statusFilter]);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 mb-2">
            <CheckSquare className="w-3.5 h-3.5" />
            <span>Volunteer Personal Queue</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            My Assigned Tasks
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Track and complete club tasks assigned to your account across all campaigns.
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search my tasks..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:text-slate-400"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {[
            { id: 'all', label: 'All Tasks' },
            { id: 'todo', label: 'To do' },
            { id: 'doing', label: 'In progress' },
            { id: 'done', label: 'Completed' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all whitespace-nowrap ${
                statusFilter === tab.id
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="space-y-3" aria-label="Loading your tasks">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm animate-pulse space-y-3"
            >
              <div className="flex justify-between items-center">
                <div className="h-5 bg-slate-200 rounded w-1/3" />
                <div className="h-5 bg-slate-200 rounded w-20" />
              </div>
              <div className="h-4 bg-slate-200 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {isError && (
        <div className="p-8 text-center bg-rose-50/50 border border-rose-200 rounded-2xl">
          <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-3">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-base font-bold text-slate-900 mb-1">Failed to load tasks</h2>
          <p className="text-sm text-slate-600 mb-4 max-w-md mx-auto">
            {error instanceof Error ? error.message : 'An error occurred.'}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !isError && filteredTasks.length === 0 && (
        <div className="text-center py-16 px-4 bg-white rounded-2xl border border-dashed border-slate-300">
          <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
            <CheckSquare className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 mb-1">
            {searchTerm || statusFilter !== 'all' ? 'No tasks matched filter' : 'No tasks assigned to you'}
          </h2>
          <p className="text-sm text-slate-500 max-w-sm mx-auto">
            {searchTerm || statusFilter !== 'all'
              ? 'Try resetting the filter to view all your tasks.'
              : 'You have no pending tasks right now. Once campaign organizers assign tasks to you, they will appear here.'}
          </p>
        </div>
      )}

      {/* Task List */}
      {!isLoading && !isError && filteredTasks.length > 0 && (
        <div className="space-y-3">
          {filteredTasks.map((task: Task) => (
            <div
              key={task.id}
              className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm transition-all hover:shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">{task.title}</h3>
                  {task.category && (
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 capitalize border border-slate-200">
                      {task.category}
                    </span>
                  )}
                </div>

                {task.description && (
                  <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                    {task.description}
                  </p>
                )}

                <div className="flex items-center gap-3 pt-1 text-xs">
                  <DueDateChip dueDate={task.due_date} isOverdue={isTaskOverdue(task)} />
                  <span className="text-slate-400">•</span>
                  <span className="text-slate-500">
                    Campaign ID: <strong className="font-mono text-slate-700">{task.fundraiser_id}</strong>
                  </span>
                </div>
              </div>

              {/* Quick Status Buttons */}
              <div className="flex items-center gap-1.5 self-start sm:self-center border-t sm:border-t-0 pt-3 sm:pt-0 border-slate-100">
                {(['todo', 'doing', 'done'] as TaskStatus[]).map((st) => {
                  const isActive = task.status === st;
                  const label = st === 'todo' ? 'To do' : st === 'doing' ? 'In progress' : 'Done';
                  return (
                    <button
                      key={st}
                      type="button"
                      disabled={patchMutation.isPending}
                      onClick={() => {
                        if (task.status !== st) {
                          patchMutation.mutate({ taskId: task.id, newStatus: st });
                        }
                      }}
                      className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                        isActive
                          ? st === 'done'
                            ? 'bg-emerald-600 text-white shadow-sm'
                            : st === 'doing'
                            ? 'bg-amber-500 text-white shadow-sm'
                            : 'bg-slate-900 text-white shadow-sm'
                          : 'bg-slate-50 text-slate-600 border border-slate-200 hover:bg-slate-100 hover:text-slate-900'
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
