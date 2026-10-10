import { X, Calendar, User, Tag, CheckCircle2, Clock, Circle, AlertTriangle } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { DueDateChip } from './OverdueChip';
import { isTaskOverdue } from '../utils/taskUtils';
import type { Task, TaskStatus } from '../types';

interface TaskDetailDrawerProps {
  task: Task | null;
  isOpen: boolean;
  onClose: () => void;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  isUpdating?: boolean;
}

export function TaskDetailDrawer({
  task,
  isOpen,
  onClose,
  onStatusChange,
  isUpdating = false,
}: TaskDetailDrawerProps) {
  if (!isOpen || !task) return null;

  const isOverdue = isTaskOverdue(task);

  return (
    <div className="fixed inset-0 z-50 overflow-hidden" role="dialog" aria-modal="true" aria-labelledby="task-detail-title">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white shadow-2xl flex flex-col border-l border-slate-200">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Task Details
              </span>
              {task.category && (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {task.category}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Close task details"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
            {/* Title */}
            <div>
              <h2 id="task-detail-title" className="text-lg font-bold text-slate-900 leading-snug">
                {task.title}
              </h2>
            </div>

            {/* Overdue Alert Banner if applicable */}
            {isOverdue && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-bold text-rose-800">Task is Overdue</div>
                  <div className="text-xs text-rose-600 mt-0.5">
                    This task was scheduled to be completed by {task.due_date}. Please update status or follow up with the assignee.
                  </div>
                </div>
              </div>
            )}

            {/* Status Selector Section */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Current Status
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: 'todo', label: 'To do', icon: Circle, color: 'text-slate-600 hover:bg-slate-100' },
                  { id: 'doing', label: 'In Progress', icon: Clock, color: 'text-amber-700 hover:bg-amber-100' },
                  { id: 'done', label: 'Completed', icon: CheckCircle2, color: 'text-emerald-700 hover:bg-emerald-100' },
                ].map((s) => {
                  const Icon = s.icon;
                  const isActive = task.status === s.id;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      disabled={isUpdating}
                      onClick={() => onStatusChange(task.id, s.id as TaskStatus)}
                      className={`flex flex-col items-center justify-center p-3 rounded-xl border text-xs font-semibold transition-all ${
                        isActive
                          ? 'border-indigo-600 bg-indigo-50 text-indigo-700 ring-2 ring-indigo-500/20'
                          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <Icon className={`w-4 h-4 mb-1.5 ${isActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                      <span>{s.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Metadata Fields */}
            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200/80 space-y-3.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-slate-400" />
                  Due Date
                </span>
                <div>
                  <DueDateChip dueDate={task.due_date} isOverdue={isOverdue} />
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-200/60">
                <span className="text-slate-500 flex items-center gap-2">
                  <User className="w-4 h-4 text-slate-400" />
                  Assignee
                </span>
                <span className="font-semibold text-slate-900">
                  {task.assignee_name || task.assignee_id || 'Unassigned'}
                </span>
              </div>

              {task.category && (
                <div className="flex items-center justify-between pt-2 border-t border-slate-200/60">
                  <span className="text-slate-500 flex items-center gap-2">
                    <Tag className="w-4 h-4 text-slate-400" />
                    Category
                  </span>
                  <span className="font-semibold text-slate-900 capitalize">
                    {task.category}
                  </span>
                </div>
              )}
            </div>

            {/* Description */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Description
              </label>
              <div className="p-4 rounded-xl bg-white border border-slate-200 text-sm text-slate-700 leading-relaxed min-h-[100px] whitespace-pre-wrap">
                {task.description || (
                  <span className="text-slate-400 italic">No description provided for this task.</span>
                )}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end">
            <Button variant="outline" size="sm" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
