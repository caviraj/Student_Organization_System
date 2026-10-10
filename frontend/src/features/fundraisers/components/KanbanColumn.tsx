import { useDroppable } from '@dnd-kit/core';
import { Plus } from 'lucide-react';
import { TaskCard } from './TaskCard';
import type { Task, TaskStatus } from '../types';

interface KanbanColumnProps {
  id: TaskStatus;
  title: string;
  tasks: Task[];
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onSelectTask: (task: Task) => void;
  onQuickAdd?: () => void;
  pendingTaskId?: string | null;
}

export function KanbanColumn({
  id,
  title,
  tasks,
  onStatusChange,
  onSelectTask,
  onQuickAdd,
  pendingTaskId,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id,
  });

  const getHeaderAccent = () => {
    switch (id) {
      case 'todo':
        return {
          bar: 'bg-slate-400',
          badge: 'bg-slate-100 text-slate-700',
        };
      case 'doing':
        return {
          bar: 'bg-amber-500',
          badge: 'bg-amber-100 text-amber-800',
        };
      case 'done':
        return {
          bar: 'bg-emerald-500',
          badge: 'bg-emerald-100 text-emerald-800',
        };
    }
  };

  const accent = getHeaderAccent();

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col bg-slate-50/80 rounded-2xl border border-slate-200/80 p-3.5 transition-colors min-h-[500px] ${
        isOver ? 'bg-indigo-50/60 border-indigo-300 ring-2 ring-indigo-400/20' : ''
      }`}
      aria-label={`${title} column with ${tasks.length} tasks`}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-200/60">
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full ${accent.bar}`} />
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">{title}</h3>
          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${accent.badge}`}>
            {tasks.length}
          </span>
        </div>

        {onQuickAdd && (
          <button
            type="button"
            onClick={onQuickAdd}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
            title={`Add task to ${title}`}
            aria-label={`Add task to ${title}`}
          >
            <Plus className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Task List */}
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        {tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            onStatusChange={onStatusChange}
            onSelect={onSelectTask}
            isPending={pendingTaskId === task.id}
          />
        ))}

        {tasks.length === 0 && (
          <div className="h-32 flex flex-col items-center justify-center border-2 border-dashed border-slate-200 rounded-xl text-center p-4 text-slate-400">
            <span className="text-xs">No tasks in this column</span>
            <span className="text-[11px] text-slate-400/80 mt-0.5">Drop tasks here</span>
          </div>
        )}
      </div>
    </div>
  );
}
