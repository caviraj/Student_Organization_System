export type {
  FundraiserStatus,
  TaskStatus,
  FundraiserProgress,
  Fundraiser,
  FundraiserDetail,
  Task,
  CreateFundraiserInput,
  CreateTaskInput,
  PatchTaskInput,
  LogIncomeInput,
} from './schemas';

export interface TasksGroupedByStatus {
  todo: import('./schemas').Task[];
  doing: import('./schemas').Task[];
  done: import('./schemas').Task[];
}
