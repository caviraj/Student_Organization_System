import { useState } from 'react';
import { useDraggable } from '@dnd-kit/core';
import { GripVertical, MoreVertical, CheckCircle2, User } from 'lucide-react';
import { DueDateChip } from './OverdueChip';
import { isTaskOverdue } from '../utils/taskUtils';
import type { Task, TaskStatus } from '../types';

interface TaskCardProps {
  task: Task;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onSelect: (task: Task) => void;
  isPending?: boolean;
}

export function TaskCard({ task, onStatusChange, onSelect, isPending = false }: TaskCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [announcement, setAnnouncement] = useState('');

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    disabled: isPending,
  });

  const style = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
      }
    : undefined;

  const handleMenuSelect = (newStatus: TaskStatus, e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(false);
    if (newStatus !== task.status) {
      setAnnouncement(`Task "${task.title}" moved to ${newStatus}`);
      onStatusChange(task.id, newStatus);
    }
  };

  const getCategoryColor = (category?: string) => {
    switch (category?.toLowerCase()) {
      case 'marketing':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case 'logistics':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'sponsorship':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'operations':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const isOverdue = isTaskOverdue(task);

  // Assignee initials
  const assigneeName = task.assignee_name || task.assignee_id;
  const assigneeInitials = assigneeName
    ? assigneeName
        .split(' ')
        .map((n) => n[0])
        .join('')
        .substring(0, 2)
        .toUpperCase()
    : null;

  return (
    <>
      {/* Screen reader live announcement */}
      {announcement && (
        <div className="sr-only" aria-live="assertive" role="status">
          {announcement}
        </div>
      )}

      <div
        ref={setNodeRef}
        style={style}
        onClick={() => onSelect(task)}
        className={`group relative bg-white rounded-xl p-4 border border-slate-200/80 shadow-sm transition-all hover:shadow-md hover:border-slate-300 cursor-pointer ${
          isDragging ? 'opacity-50 ring-2 ring-indigo-500 shadow-xl' : ''
        } ${isPending ? 'opacity-60 pointer-events-none' : ''}`}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(task);
          }
        }}
        aria-label={`Task: ${task.title}, Status: ${task.status}`}
      >
        {/* Top Bar: Drag handle, Category, and Action Menu */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5">
            {/* Drag Handle */}
            <button
              type="button"
              {...listeners}
              {...attributes}
              onClick={(e) => e.stopPropagation()}
              className="p-1 -ml-1 text-slate-400 hover:text-slate-600 rounded cursor-grab active:cursor-grabbing focus:outline-none focus:ring-1 focus:ring-indigo-500"
              aria-label={`Drag task ${task.title}`}
            >
              <GripVertical className="w-4 h-4" />
            </button>

            {task.category && (
              <span
                className={`inline-block px-2 py-0.5 text-[11px] font-semibold rounded-md border ${getCategoryColor(
                  task.category
                )}`}
              >
                {task.category}
              </span>
            )}
          </div>

          {/* Accessible "Move to..." Menu */}
          <div className="relative">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(!menuOpen);
              }}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              aria-label={`Options for task ${task.title}`}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <MoreVertical className="w-4 h-4" />
            </button>

            {menuOpen && (
              <>
                <div
                  className="fixed inset-0 z-20"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpen(false);
                  }}
                />
                <div
                  className="absolute right-0 top-full mt-1 w-36 bg-white rounded-xl shadow-lg border border-slate-200 py-1.5 z-30 focus:outline-none"
                  role="menu"
                >
                  <div className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Move to
                  </div>
                  {(['todo', 'doing', 'done'] as TaskStatus[]).map((st) => (
                    <button
                      key={st}
                      type="button"
                      role="menuitem"
                      disabled={st === task.status}
                      onClick={(e) => handleMenuSelect(st, e)}
                      className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between transition-colors ${
                        st === task.status
                          ? 'text-slate-300 cursor-not-allowed bg-slate-50'
                          : 'text-slate-700 hover:bg-indigo-50 hover:text-indigo-600'
                      }`}
                    >
                      <span className="capitalize">{st === 'todo' ? 'To do' : st === 'doing' ? 'In progress' : 'Done'}</span>
                      {st === task.status && <CheckCircle2 className="w-3.5 h-3.5 text-slate-400" />}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Task Title */}
        <h4 className="text-sm font-semibold text-slate-900 leading-snug line-clamp-2 mb-1 group-hover:text-indigo-600 transition-colors">
          {task.title}
        </h4>

        {/* Optional Description (truncated) */}
        {task.description && (
          <p className="text-xs text-slate-500 line-clamp-2 mb-3 leading-relaxed">
            {task.description}
          </p>
        )}

        {/* Card Footer: Due Date & Assignee Avatar */}
        <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs">
          <div>
            <DueDateChip dueDate={task.due_date} isOverdue={isOverdue} />
          </div>

          <div className="flex items-center gap-1.5">
            {assigneeInitials ? (
              <div
                className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 font-bold text-[10px] flex items-center justify-center border border-indigo-200"
                title={`Assigned to: ${assigneeName}`}
                aria-label={`Assigned to ${assigneeName}`}
              >
                {assigneeInitials}
              </div>
            ) : (
              <div
                className="w-6 h-6 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center"
                title="Unassigned"
                aria-label="Unassigned"
              >
                <User className="w-3.5 h-3.5" />
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
