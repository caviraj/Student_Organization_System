import { cn } from '../../lib/utils';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

export interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        'p-6 sm:p-8 rounded-2xl border border-rose-200 bg-rose-50/60 text-center flex flex-col items-center justify-center',
        className
      )}
    >
      <div className="w-12 h-12 rounded-2xl bg-rose-100 flex items-center justify-center text-rose-600 mb-3 shadow-xs">
        <AlertCircle className="w-6 h-6" />
      </div>
      <h3 className="text-base font-semibold text-rose-900 mb-1">{title}</h3>
      <p className="text-sm text-rose-700 max-w-md mb-4">{message}</p>
      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          className="border-rose-300 text-rose-800 hover:bg-rose-100"
        >
          Try Again
        </Button>
      )}
    </div>
  );
}
