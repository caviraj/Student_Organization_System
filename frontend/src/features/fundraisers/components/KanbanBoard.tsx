import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  DndContext,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { AlertCircle } from 'lucide-react';
import { KanbanColumn } from './KanbanColumn';
import { TaskDetailDrawer } from './TaskDetailDrawer';
import { fundraisersApi } from '../../../api/fundraisers';
import { groupAndSortTasks } from '../utils/taskUtils';
import { useToast } from '../../../components/ui/Toast';
import { Button } from '../../../components/ui/Button';
import type { Task, TaskStatus } from '../types';

interface KanbanBoardProps {
  fundraiserId: string;
  onOpenCreateTask?: (defaultStatus?: TaskStatus) => void;
}

export function KanbanBoard({ fundraiserId, onOpenCreateTask }: KanbanBoardProps) {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [mobileTab, setMobileTab] = useState<TaskStatus>('todo');

  // Fetch tasks for this fundraiser
  const {
    data: tasks = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['fundraiser-tasks', fundraiserId],
    queryFn: () => fundraisersApi.getFundraiserTasks(fundraiserId),
  });

  // Group & Sort tasks deterministically
  const groupedTasks = useMemo(() => {
    return groupAndSortTasks(tasks);
  }, [tasks]);

  // Keep selectedTask in sync with cached tasks if it updates
  const activeTask = useMemo(() => {
    if (!selectedTask) return null;
    return tasks.find((t) => t.id === selectedTask.id) || selectedTask;
  }, [tasks, selectedTask]);

  // Optimistic status update mutation
  const statusMutation = useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: string; newStatus: TaskStatus }) =>
      fundraisersApi.patchTask(taskId, { status: newStatus }),

    onMutate: async ({ taskId, newStatus }) => {
      // Cancel outgoing refetches so they don't overwrite optimistic update
      await queryClient.cancelQueries({ queryKey: ['fundraiser-tasks', fundraiserId] });

      // Snapshot the previous tasks
      const previousTasks = queryClient.getQueryData<Task[]>(['fundraiser-tasks', fundraiserId]);

      // Optimistically update the cache
      if (previousTasks) {
        queryClient.setQueryData<Task[]>(
          ['fundraiser-tasks', fundraiserId],
          previousTasks.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t))
        );
      }

      return { previousTasks };
    },

    onError: (err, _variables, context) => {
      // Rollback to previous state
      if (context?.previousTasks) {
        queryClient.setQueryData(['fundraiser-tasks', fundraiserId], context.previousTasks);
      }
      const message =
        err instanceof Error
          ? err.message
          : 'Failed to update task status. You may not have permission.';
      addToast({
        type: 'error',
        title: 'Action Failed',
        message,
      });
    },

    onSuccess: (updatedTask) => {
      addToast({
        type: 'success',
        title: 'Status Updated',
        message: `Task moved to ${updatedTask.status}.`,
      });
    },

    onSettled: () => {
      // Invalidate tasks query and fundraiser detail query (which updates the progress ring!)
      queryClient.invalidateQueries({ queryKey: ['fundraiser-tasks', fundraiserId] });
      queryClient.invalidateQueries({ queryKey: ['fundraiser', fundraiserId] });
    },
  });

  // Configure Sensors (Pointer distance 8px to prevent accidental drag on click; touch with 200ms delay)
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: 200,
        tolerance: 5,
      },
    })
  );

  const handleStatusChange = (taskId: string, newStatus: TaskStatus) => {
    statusMutation.mutate({ taskId, newStatus });
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;

    const taskId = active.id as string;
    const targetColumn = over.id as TaskStatus;

    if (!['todo', 'doing', 'done'].includes(targetColumn)) return;

    const task = tasks.find((t) => t.id === taskId);
    if (task && task.status !== targetColumn) {
      handleStatusChange(taskId, targetColumn);
    }
  };

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 py-6" aria-label="Loading task board">
        {(['To do', 'In progress', 'Done'] as const).map((_title, i) => (
          <div key={i} className="bg-slate-50/80 rounded-2xl border border-slate-200/80 p-4 min-h-[450px]">
            <div className="h-5 bg-slate-200 rounded w-24 mb-4 animate-pulse" />
            <div className="space-y-3">
              {[1, 2].map((n) => (
                <div key={n} className="bg-white rounded-xl p-4 border border-slate-200 h-28 animate-pulse" />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-8 text-center bg-rose-50/50 border border-rose-200 rounded-2xl my-6">
        <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-3">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h3 className="text-base font-bold text-slate-900 mb-1">Failed to load campaign tasks</h3>
        <p className="text-sm text-slate-600 mb-4 max-w-md mx-auto">
          {error instanceof Error ? error.message : 'An error occurred while fetching tasks.'}
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="py-4">
      {/* Mobile Column Navigation Tabs */}
      <div className="md:hidden flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl mb-4">
        {[
          { id: 'todo', label: 'To do', count: groupedTasks.todo.length },
          { id: 'doing', label: 'Doing', count: groupedTasks.doing.length },
          { id: 'done', label: 'Done', count: groupedTasks.done.length },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setMobileTab(tab.id as TaskStatus)}
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
              mobileTab === tab.id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <span>{tab.label}</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                mobileTab === tab.id ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-200 text-slate-600'
              }`}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* DnD Context Container */}
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        {/* Desktop: 3 Columns Grid | Mobile: Active Tab Column */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className={`${mobileTab === 'todo' ? 'block' : 'hidden md:block'}`}>
            <KanbanColumn
              id="todo"
              title="To do"
              tasks={groupedTasks.todo}
              onStatusChange={handleStatusChange}
              onSelectTask={setSelectedTask}
              onQuickAdd={() => onOpenCreateTask?.('todo')}
              pendingTaskId={statusMutation.isPending ? statusMutation.variables?.taskId : null}
            />
          </div>

          <div className={`${mobileTab === 'doing' ? 'block' : 'hidden md:block'}`}>
            <KanbanColumn
              id="doing"
              title="In progress"
              tasks={groupedTasks.doing}
              onStatusChange={handleStatusChange}
              onSelectTask={setSelectedTask}
              onQuickAdd={() => onOpenCreateTask?.('doing')}
              pendingTaskId={statusMutation.isPending ? statusMutation.variables?.taskId : null}
            />
          </div>

          <div className={`${mobileTab === 'done' ? 'block' : 'hidden md:block'}`}>
            <KanbanColumn
              id="done"
              title="Done"
              tasks={groupedTasks.done}
              onStatusChange={handleStatusChange}
              onSelectTask={setSelectedTask}
              onQuickAdd={() => onOpenCreateTask?.('done')}
              pendingTaskId={statusMutation.isPending ? statusMutation.variables?.taskId : null}
            />
          </div>
        </div>
      </DndContext>

      {/* Task Detail Slide-over Drawer */}
      <TaskDetailDrawer
        task={activeTask}
        isOpen={Boolean(selectedTask)}
        onClose={() => setSelectedTask(null)}
        onStatusChange={handleStatusChange}
        isUpdating={statusMutation.isPending}
      />
    </div>
  );
}
