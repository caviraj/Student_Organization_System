import type { FulfillmentStatus } from '../types';

interface FulfillmentTrackerProps {
  status: FulfillmentStatus | string;
}

const STEPS: { key: FulfillmentStatus; label: string; desc: string }[] = [
  { key: 'paid', label: 'Payment Confirmed', desc: 'Order received & queued' },
  { key: 'packed', label: 'Packed & Ready', desc: 'Tagged for pickup' },
  { key: 'handed_over', label: 'Handed Over', desc: 'Collected by student' },
];

export const FulfillmentTracker: React.FC<FulfillmentTrackerProps> = ({ status }) => {
  const normalizedStatus = status.toLowerCase();

  const getStepIndex = (st: string): number => {
    switch (st) {
      case 'paid':
        return 0;
      case 'packed':
        return 1;
      case 'handed_over':
        return 2;
      default:
        return 0;
    }
  };

  const currentIdx = getStepIndex(normalizedStatus);

  return (
    <div className="w-full py-4" aria-label={`Fulfillment status: ${status}`}>
      <div className="relative flex items-center justify-between">
        {/* Connecting Progress Bar */}
        <div className="absolute left-6 right-6 top-1/2 -translate-y-1/2 h-1 bg-slate-200 -z-0">
          <div
            className="h-full bg-emerald-500 transition-all duration-500"
            style={{
              width: `${(currentIdx / (STEPS.length - 1)) * 100}%`,
            }}
          />
        </div>

        {STEPS.map((step, idx) => {
          const isCompleted = idx < currentIdx;
          const isCurrent = idx === currentIdx;

          return (
            <div key={step.key} className="relative z-10 flex flex-col items-center text-center">
              {/* Node Circle */}
              <div
                className={`flex h-10 w-10 items-center justify-center rounded-full border-2 text-xs font-bold transition-all shadow-sm ${
                  isCompleted
                    ? 'border-emerald-500 bg-emerald-500 text-white'
                    : isCurrent
                    ? 'border-primary-600 bg-white text-primary-600 ring-4 ring-primary-100 scale-110'
                    : 'border-slate-300 bg-white text-slate-400'
                }`}
                aria-current={isCurrent ? 'step' : undefined}
              >
                {isCompleted ? (
                  <svg className="h-5 w-5 stroke-[2.5]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {/* Step Label */}
              <div className="mt-2.5">
                <span
                  className={`block text-xs font-bold ${
                    isCurrent
                      ? 'text-primary-700 font-extrabold'
                      : isCompleted
                      ? 'text-slate-800'
                      : 'text-slate-400'
                  }`}
                >
                  {step.label}
                </span>
                <span className="hidden sm:block text-[10px] text-slate-400 mt-0.5">
                  {step.desc}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
