import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  isTaskOverdue,
  calculateProgress,
  calculateRaisedPercentage,
  groupAndSortTasks,
} from './utils/taskUtils';
import { ProgressRing } from './components/ProgressRing';
import { RaisedBar } from './components/RaisedBar';
import { DueDateChip, OverdueCounter } from './components/OverdueChip';
import { TaskCard } from './components/TaskCard';
import { LogIncomeModal } from './components/LogIncomeModal';
import { CreateFundraiserSchema, CreateTaskSchema, LogIncomeSchema } from './schemas';
import type { Task } from './types';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '../../components/ui/Toast';

const mockTasks: Task[] = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    fundraiser_id: 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
    title: 'Print Event Posters',
    description: 'A3 size glossy posters',
    status: 'todo',
    category: 'Marketing',
    assignee_id: 'usr_vol_1',
    assignee_name: 'Alex Rivera',
    due_date: '2020-01-01', // definitely past
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:00:00Z',
  },
  {
    id: '22222222-2222-4222-8222-222222222222',
    fundraiser_id: 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
    title: 'Procure Sound Gear',
    description: '',
    status: 'doing',
    category: 'Logistics',
    assignee_id: null,
    assignee_name: undefined,
    due_date: '2099-12-31', // future
    created_at: '2026-10-01T11:00:00Z',
    updated_at: '2026-10-01T11:00:00Z',
  },
  {
    id: '33333333-3333-4333-8333-333333333333',
    fundraiser_id: 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
    title: 'Book Campus Stage',
    description: '',
    status: 'done',
    category: 'Operations',
    assignee_id: 'usr_vol_2',
    assignee_name: 'Priya Sharma',
    due_date: '2020-01-01', // past date, but status is DONE
    created_at: '2026-10-01T12:00:00Z',
    updated_at: '2026-10-01T12:00:00Z',
  },
];

describe('Phase 5 Fundraisers & Tasks - Unit & Utility Tests', () => {
  describe('taskUtils: isTaskOverdue', () => {
    it('marks pending tasks in the past as overdue', () => {
      expect(isTaskOverdue(mockTasks[0])).toBe(true);
    });

    it('returns false for pending tasks due in the future', () => {
      expect(isTaskOverdue(mockTasks[1])).toBe(false);
    });

    it('returns false for completed (done) tasks even if due date is in the past', () => {
      expect(isTaskOverdue(mockTasks[2])).toBe(false);
    });
  });

  describe('taskUtils: calculateProgress', () => {
    it('handles 0 total tasks gracefully without returning NaN', () => {
      const progress = calculateProgress('fr_1', [], 0, 100000);
      expect(progress.done).toBe(0);
      expect(progress.tasks_total).toBe(0);
      expect(progress.overdue).toBe(0);
    });

    it('calculates metrics correctly for mixed tasks', () => {
      const progress = calculateProgress('fr_1', mockTasks, 50000, 100000);
      expect(progress.tasks_total).toBe(3);
      expect(progress.done).toBe(1);
      expect(progress.overdue).toBe(1); // Only tsk_1 is overdue and not done
    });
  });

  describe('taskUtils: calculateRaisedPercentage', () => {
    it('calculates money progress correctly with integer paise', () => {
      // Raised ₹5,000 of ₹10,000 goal
      expect(calculateRaisedPercentage(500000, 1000000)).toBe(50);
    });

    it('reports true percentage > 100%', () => {
      // Raised ₹15,000 of ₹10,000 goal (150%)
      expect(calculateRaisedPercentage(1500000, 1000000)).toBe(150);
    });

    it('handles goal of 0 gracefully without NaN', () => {
      expect(calculateRaisedPercentage(500000, 0)).toBe(0);
    });
  });

  describe('taskUtils: groupAndSortTasks', () => {
    it('groups tasks by status and sorts by due date', () => {
      const grouped = groupAndSortTasks(mockTasks);
      expect(grouped.todo).toHaveLength(1);
      expect(grouped.doing).toHaveLength(1);
      expect(grouped.done).toHaveLength(1);
      expect(grouped.todo[0].title).toBe('Print Event Posters');
    });
  });

  describe('Zod Validation Schemas', () => {
    it('validates CreateFundraiserSchema with valid inputs', () => {
      const valid = CreateFundraiserSchema.safeParse({
        title: 'Spring Concert 2026',
        description: 'Fundraiser for campus music festival',
        goal_amount: 5000000, // paise
        event_date: '2026-10-31',
      });
      expect(valid.success).toBe(true);
    });

    it('rejects CreateFundraiserSchema with short title or non-positive goal', () => {
      const invalid = CreateFundraiserSchema.safeParse({
        title: 'A',
        goal_amount: -10,
        event_date: '2026-10-01',
      });
      expect(invalid.success).toBe(false);
    });

    it('validates CreateTaskSchema requiring title and category', () => {
      const valid = CreateTaskSchema.safeParse({
        title: 'Order LED stage lights',
        category: 'Logistics',
        due_date: '2026-11-01',
      });
      expect(valid.success).toBe(true);

      const invalid = CreateTaskSchema.safeParse({
        title: '',
        category: '',
        due_date: '',
      });
      expect(invalid.success).toBe(false);
    });

    it('validates LogIncomeSchema requiring positive integer paise amount', () => {
      const valid = LogIncomeSchema.safeParse({
        amount: 250000, // paise
        source: 'sponsorship',
        note: 'Donation from Alumni Batch of 2022',
      });
      expect(valid.success).toBe(true);

      const zeroAmount = LogIncomeSchema.safeParse({
        amount: 0,
        source: 'cash',
      });
      expect(zeroAmount.success).toBe(false);
    });
  });
});

describe('Phase 5 UI Components', () => {
  describe('ProgressRing', () => {
    it('renders 0% fallback without NaN when done is 0 and total is 0', () => {
      render(<ProgressRing done={0} total={0} />);
      expect(screen.getByText('0%')).toBeInTheDocument();
      expect(screen.getByText('0/0')).toBeInTheDocument();
      expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    });

    it('renders correct percentage and task count', () => {
      render(<ProgressRing done={3} total={4} />);
      expect(screen.getByText('75%')).toBeInTheDocument();
      expect(screen.getByText('3/4')).toBeInTheDocument();
    });
  });

  describe('RaisedBar', () => {
    it('renders raised vs goal in rupees and capped width bar', () => {
      const { container } = render(
        <RaisedBar raised={750000} goal={1000000} />
      );
      expect(screen.getByText('₹7,500')).toBeInTheDocument();
      expect(screen.getByText('75%')).toBeInTheDocument();

      const fillBar = container.querySelector('[style*="width"]');
      expect(fillBar?.getAttribute('style')).toContain('width: 75%');
    });

    it('displays true figure > 100% while visual bar is visually capped at 100%', () => {
      const { container } = render(
        <RaisedBar raised={1500000} goal={1000000} />
      );
      // True percentage displayed
      expect(screen.getByText('150%')).toBeInTheDocument();
      expect(screen.getByText('₹15,000')).toBeInTheDocument();

      // Style width is capped at 100%
      const fillBar = container.querySelector('[style*="width"]');
      expect(fillBar?.getAttribute('style')).toContain('width: 100%');
    });
  });

  describe('OverdueChip & OverdueCounter', () => {
    it('renders DueDateChip with Overdue state for past tasks', () => {
      render(<DueDateChip dueDate="2020-01-01" isOverdue={true} />);
      expect(screen.getByText(/Late/i)).toBeInTheDocument();
    });

    it('renders OverdueCounter showing number of delayed tasks', () => {
      render(<OverdueCounter count={4} />);
      expect(screen.getByText('4 overdue')).toBeInTheDocument();
    });

    it('renders nothing when overdueCount is 0', () => {
      const { container } = render(<OverdueCounter count={0} />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe('TaskCard with Accessible Move To Menu', () => {
    it('renders task card details and quick move menu buttons', async () => {
      const user = userEvent.setup();
      const onStatusChange = vi.fn();
      const onSelect = vi.fn();

      render(
        <TaskCard
          task={mockTasks[0]}
          onStatusChange={onStatusChange}
          onSelect={onSelect}
        />
      );

      expect(screen.getByText('Print Event Posters')).toBeInTheDocument();
      expect(screen.getByText('Marketing')).toBeInTheDocument();
      expect(screen.getByText('AR')).toBeInTheDocument(); // Alex Rivera initials

      // Click "Options for task..." menu trigger
      const moveMenuButton = screen.getByRole('button', {
        name: /Options for task Print Event Posters/i,
      });
      await user.click(moveMenuButton);

      // Verify accessible options: In progress and Done (since current is todo)
      const moveDoingBtn = screen.getByRole('menuitem', { name: /In progress/i });
      expect(moveDoingBtn).toBeInTheDocument();

      await user.click(moveDoingBtn);
      expect(onStatusChange).toHaveBeenCalledWith(
        '11111111-1111-4111-8111-111111111111',
        'doing'
      );
    });
  });

  describe('LogIncomeModal - Multi-step Ledger Confirmation & Paise Conversion', () => {
    it('requires reviewing ledger confirmation warning and converts rupees to integer paise', async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      });

      const { fundraisersApi } = await import('../../api/fundraisers');
      const logIncomeSpy = vi.spyOn(fundraisersApi, 'logIncome').mockResolvedValue({
        message: 'Income logged successfully',
        raised: 150050,
      });

      render(
        <ToastProvider>
          <QueryClientProvider client={queryClient}>
            <LogIncomeModal
              isOpen={true}
              fundraiserId="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
              fundraiserTitle="Campus Food Festival"
              onClose={onClose}
            />
          </QueryClientProvider>
        </ToastProvider>
      );

      // Verify modal header
      expect(screen.getByText(/Log Campaign Income/i)).toBeInTheDocument();

      // Enter amount: ₹1,500.50
      const amountInput = screen.getByLabelText(/Amount Raised \(₹\)/i);
      await user.clear(amountInput);
      await user.type(amountInput, '1500.50');

      // Add a note
      const noteInput = screen.getByLabelText(/Note \/ Donor Reference/i);
      await user.type(noteInput, 'Sponsor donation by Campus Cafe');

      // Continue to review button
      const reviewBtn = screen.getByRole('button', { name: /Review & Confirm/i });
      expect(reviewBtn).not.toBeDisabled();
      await user.click(reviewBtn);

      // Now on Step 2: Confirmation Dialog with warning
      expect(
        screen.getByText(/Permanent Ledger Record Warning/i)
      ).toBeInTheDocument();
      expect(screen.getAllByText('₹1,500.50').length).toBeGreaterThanOrEqual(1);

      // Click Confirm & Write to Ledger
      const confirmBtn = screen.getByRole('button', { name: /Confirm & Write to Ledger/i });
      await user.click(confirmBtn);

      await waitFor(() => {
        expect(logIncomeSpy).toHaveBeenCalledTimes(1);
      });

      // Verify integer paise conversion: 1500.50 * 100 = 150050 paise
      expect(logIncomeSpy).toHaveBeenCalledWith(
        'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
        {
          amount: 150050,
          source: 'cash',
          note: 'Sponsor donation by Campus Cafe',
        }
      );
    });
  });
});
