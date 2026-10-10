import { type ReactNode } from 'react';
import { cn } from '../../lib/utils';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

export interface Column<T> {
  header: string;
  accessorKey?: keyof T;
  cell?: (item: T) => ReactNode;
  accessor?: (item: T) => ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor?: (item: T) => string;
  keyField?: string;
  isLoading?: boolean;
  page?: number;
  pageSize?: number;
  total?: number;
  totalItems?: number;
  onPageChange?: (newPage: number) => void;
  emptyMessage?: string;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  keyField,
  isLoading,
  page = 1,
  pageSize = 10,
  total = 0,
  totalItems,
  onPageChange,
  emptyMessage = 'No records found',
  className,
}: DataTableProps<T>) {
  const actualTotal = total || totalItems || 0;
  const totalPages = Math.ceil(actualTotal / pageSize) || 1;

  const getKey = (item: T, idx: number): string => {
    if (keyExtractor) return keyExtractor(item);
    if (keyField && (item as Record<string, unknown>)[keyField]) {
      return String((item as Record<string, unknown>)[keyField]);
    }
    if ((item as Record<string, unknown>).id) {
      return String((item as Record<string, unknown>).id);
    }
    return String(idx);
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-14 bg-slate-100 animate-pulse rounded-xl" />
        ))}
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="p-8 text-center text-sm text-slate-500 bg-white rounded-xl border border-slate-200">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs', className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-700">
          <thead className="bg-slate-50/80 border-b border-slate-200 text-xs uppercase font-semibold text-slate-500 tracking-wider">
            <tr>
              {columns.map((col, idx) => (
                <th key={idx} className={cn('px-5 py-3.5', col.className)}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((item, idx) => (
              <tr key={getKey(item, idx)} className="hover:bg-slate-50/70 transition-colors">
                {columns.map((col, idx) => (
                  <td key={idx} className={cn('px-5 py-4 whitespace-nowrap', col.className)}>
                    {col.cell
                      ? col.cell(item)
                      : col.accessor
                      ? col.accessor(item)
                      : col.accessorKey
                      ? String(item[col.accessorKey] ?? '—')
                      : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      {actualTotal > 0 && onPageChange && (
        <div className="p-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 bg-slate-50/40">
          <div>
            Showing <span className="font-semibold text-slate-700">{(page - 1) * pageSize + 1}</span> to{' '}
            <span className="font-semibold text-slate-700">{Math.min(page * pageSize, actualTotal)}</span> of{' '}
            <span className="font-semibold text-slate-700">{actualTotal}</span> entries
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              aria-label="Previous Page"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="px-2 font-medium">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              aria-label="Next Page"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
