import type { Task, FundraiserProgress, TasksGroupedByStatus } from '../types';

/**
 * Returns today's date formatted as YYYY-MM-DD in the user's local timezone.
 */
export function getLocalDateString(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * A task is overdue iff due_date < today (date-only comparison in local time)
 * AND status !== 'done'. Done tasks are NEVER overdue.
 */
export function isTaskOverdue(task: Pick<Task, 'due_date' | 'status'>, todayStr?: string): boolean {
  if (task.status === 'done') {
    return false;
  }
  const today = todayStr || getLocalDateString();
  return task.due_date < today;
}

/**
 * Calculates progress metrics for a fundraiser.
 */
export function calculateProgress(
  _fundraiserId: string,
  tasks: Task[],
  raised: number,
  goal: number
): FundraiserProgress {
  const tasks_total = tasks.length;
  const done = tasks.filter((t) => t.status === 'done').length;
  const overdue = tasks.filter((t) => isTaskOverdue(t)).length;

  return {
    tasks_total,
    done,
    overdue,
    raised,
    goal,
  };
}

/**
 * Calculates true percentage raised (can exceed 100%).
 */
export function calculateRaisedPercentage(raised: number, goal: number): number {
  if (!goal || goal <= 0) return 0;
  return Math.round((raised / goal) * 100);
}

/**
 * Groups tasks by status and sorts each list deterministically:
 * due_date ascending (soonest first), then created_at ascending.
 */
export function groupAndSortTasks(tasks: Task[]): TasksGroupedByStatus {
  const grouped: TasksGroupedByStatus = {
    todo: [],
    doing: [],
    done: [],
  };

  for (const t of tasks) {
    if (grouped[t.status]) {
      grouped[t.status].push(t);
    } else {
      grouped.todo.push(t);
    }
  }

  const sortFn = (a: Task, b: Task) => {
    if (a.due_date !== b.due_date) {
      return a.due_date.localeCompare(b.due_date);
    }
    return (a.created_at || '').localeCompare(b.created_at || '');
  };

  grouped.todo.sort(sortFn);
  grouped.doing.sort(sortFn);
  grouped.done.sort(sortFn);

  return grouped;
}
