import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { shopApi } from '../../../api/shop';
import { FulfillmentTracker } from '../components/FulfillmentTracker';
import { formatINR } from '../../../lib/formatINR';
import { formatDate } from '../../../lib/formatDate';
import { StatusChip } from '../../../components/ui/StatusChip';
import { Skeleton } from '../../../components/ui/Skeleton';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ErrorState } from '../../../components/ui/ErrorState';

export const MyOrders = () => {
  const {
    data: orders = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['myMerchOrders'],
    queryFn: () => shopApi.getMyOrders(),
  });

  const getStatusVariant = (status: string) => {
    switch (status.toLowerCase()) {
      case 'handed_over':
        return 'success';
      case 'packed':
        return 'warning';
      case 'paid':
        return 'active';
      default:
        return 'none';
    }
  };

  return (
    <div className="min-h-screen bg-slate-50/60 py-10">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">
              My Merchandise Orders
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Track the packing and collection status of your club apparel and accessories.
            </p>
          </div>
          <Link
            to="/shop"
            className="inline-flex items-center gap-1.5 self-start rounded-xl bg-primary-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-primary-700 transition-colors"
          >
            <span>Browse Shop</span>
            <span>→</span>
          </Link>
        </div>

        {/* Content States */}
        {isLoading ? (
          <div className="space-y-6">
            {[1, 2].map((n) => (
              <div key={n} className="rounded-3xl border border-slate-200 bg-white p-6 space-y-4">
                <div className="flex justify-between">
                  <Skeleton className="h-6 w-48 rounded" />
                  <Skeleton className="h-6 w-24 rounded" />
                </div>
                <Skeleton className="h-16 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
              </div>
            ))}
          </div>
        ) : error ? (
          <ErrorState
            title="Failed to load your orders"
            message="We could not retrieve your merchandise orders. Please check your network connection and try again."
            onRetry={() => refetch()}
          />
        ) : orders.length === 0 ? (
          <EmptyState
            title="No merchandise orders yet"
            description="You haven't purchased any club merchandise. Explore our official collection of hoodies, tees, and caps!"
            actionLabel="Explore Shop"
            onAction={() => {
              window.location.href = '/shop';
            }}
          />
        ) : (
          <div className="space-y-8">
            {orders.map((order) => {
              const status = order.fulfilment_status || 'paid';
              const isFulfilled = status.toLowerCase() === 'handed_over';

              return (
                <div
                  key={order.id}
                  data-testid={`order-card-${order.id}`}
                  className="overflow-hidden rounded-3xl border border-slate-200/90 bg-white shadow-sm transition-all hover:shadow-md"
                >
                  {/* Top Bar */}
                  <div className="border-b border-slate-100 bg-slate-50/70 px-6 py-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs font-bold text-slate-800 bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs">
                        {order.id}
                      </span>
                      <span className="text-xs text-slate-500">
                        Placed on {formatDate(order.created_at)}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <StatusChip
                        status={getStatusVariant(status)}
                        label={
                          status.toLowerCase() === 'handed_over'
                            ? 'Handed Over'
                            : status.toLowerCase() === 'packed'
                            ? 'Packed & Ready'
                            : 'Payment Confirmed'
                        }
                      />
                    </div>
                  </div>

                  {/* Body Content */}
                  <div className="p-6 space-y-6">
                    {/* Visual Fulfillment Tracker */}
                    <div className="rounded-2xl bg-slate-50/50 p-4 border border-slate-100">
                      <FulfillmentTracker status={status} />
                    </div>

                    {/* Delivery / Pickup Note */}
                    {order.delivery_note && (
                      <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-3 text-xs text-slate-600 flex items-start gap-2">
                        <svg className="h-4 w-4 text-slate-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <div>
                          <span className="font-bold text-slate-700">Fulfillment Note: </span>
                          <span>{order.delivery_note}</span>
                        </div>
                      </div>
                    )}

                    {/* Order Items Table */}
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                        Ordered Items
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-slate-100 text-slate-400">
                              <th className="pb-2 font-semibold">Item & Description</th>
                              <th className="pb-2 font-semibold text-center">Size</th>
                              <th className="pb-2 font-semibold text-center">Qty</th>
                              <th className="pb-2 font-semibold text-right">Unit Price</th>
                              <th className="pb-2 font-semibold text-right">Line Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 text-slate-700">
                            {order.items?.map((item) => (
                              <tr key={item.id || item.variant_id} className="py-2.5">
                                <td className="py-3 font-semibold text-slate-900">
                                  {item.product_name}
                                </td>
                                <td className="py-3 text-center">
                                  <span className="rounded bg-slate-100 px-2 py-0.5 font-bold text-slate-700">
                                    {item.size}
                                  </span>
                                </td>
                                <td className="py-3 text-center font-medium">{item.qty}</td>
                                <td className="py-3 text-right text-slate-500">
                                  {formatINR(item.unit_price)}
                                </td>
                                <td className="py-3 text-right font-bold text-slate-900">
                                  {formatINR(item.qty * item.unit_price)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Order Total & Pickup Advice */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between border-t border-slate-100 pt-4 gap-4">
                      <div className="text-xs text-slate-500">
                        {isFulfilled ? (
                          <span className="text-emerald-700 font-semibold flex items-center gap-1.5">
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Order completed and handed over. Enjoy your merchandise!
                          </span>
                        ) : (
                          <span>
                            Please show your order ID or student card when collecting your order at the club booth.
                          </span>
                        )}
                      </div>

                      <div className="flex items-baseline justify-between sm:justify-end gap-3 text-right">
                        <span className="text-xs text-slate-500">Total Paid:</span>
                        <span className="text-xl font-black text-slate-900">
                          {formatINR(order.amount ?? 0)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
