import { useQuery } from '@tanstack/react-query';
import { shopApi } from '../../../api/shop';
import { CANONICAL_SIZES } from '../types';
import { ErrorState } from '../../../components/ui/ErrorState';
import { Button } from '../../../components/ui/Button';
import {
  Package,
  Layers,
  AlertTriangle,
  RefreshCw,
  TrendingUp,
  Boxes,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

export function StockSummaryTable() {
  const {
    data: summary,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['adminStockSummary'],
    queryFn: () => shopApi.getStockSummary(),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
        <div className="h-64 bg-slate-100 rounded-xl animate-pulse" />
      </div>
    );
  }

  if (error || !summary) {
    return (
      <ErrorState
        title="Could not load stock summary"
        message={(error as Error)?.message || 'Failed to fetch inventory demands.'}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Aggregates */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs flex items-center gap-3">
          <div className="p-3 rounded-lg bg-emerald-50 text-emerald-600">
            <Boxes className="w-6 h-6" />
          </div>
          <div>
            <p className="text-2xs font-bold text-slate-500 uppercase tracking-wider">
              Total Units Remaining
            </p>
            <p className="text-2xl font-bold text-slate-900 mt-0.5">
              {summary.total_units_remaining}
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs flex items-center gap-3">
          <div className="p-3 rounded-lg bg-amber-50 text-amber-600">
            <TrendingUp className="w-6 h-6" />
          </div>
          <div>
            <p className="text-2xs font-bold text-slate-500 uppercase tracking-wider">
              Total Units Ordered
            </p>
            <p className="text-2xl font-bold text-slate-900 mt-0.5">
              {summary.total_units_ordered}
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs flex items-center justify-between">
          <div>
            <p className="text-2xs font-bold text-slate-500 uppercase tracking-wider">
              Data Freshness
            </p>
            <p className="text-xs text-slate-600 mt-1">Live order & inventory sync</p>
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={isFetching}
            onClick={() => refetch()}
            className="text-xs h-8"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 mr-1.5 ${isFetching ? 'animate-spin' : ''}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      {/* Aggregate Size Demand Strip */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Layers className="w-4 h-4 text-amber-600" />
          Aggregated Demand Across Sizes
        </h4>
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
          {CANONICAL_SIZES.map((size) => {
            const count = summary.total_demand_per_size[size] || 0;
            return (
              <div
                key={size}
                className="p-2.5 rounded-lg border border-slate-100 bg-slate-50 text-center"
              >
                <span className="text-xs font-bold text-slate-600 block">{size}</span>
                <span className="text-lg font-black text-slate-900 block mt-0.5">
                  {count}
                </span>
                <span className="text-2xs text-slate-400">ordered</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detailed Stock by Product & Variant */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
            <Package className="w-4 h-4 text-amber-600" />
            Product Variant Stock & Fulfillment Demand
          </h4>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-2xs font-semibold text-slate-600 uppercase tracking-wider">
                <th className="py-3 px-4">Product</th>
                <th className="py-3 px-3">Size / Color</th>
                <th className="py-3 px-3 font-mono">SKU</th>
                <th className="py-3 px-3 text-right">In Stock</th>
                <th className="py-3 px-3 text-right">Demand (Orders)</th>
                <th className="py-3 px-4 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {summary.products.flatMap((prod) =>
                prod.variants.map((v) => {
                  const isSoldOut = v.remaining === 0;
                  const isLow = v.low_stock;
                  const hasDeficit = v.remaining < v.demand;

                  return (
                    <tr
                      key={v.variant_id}
                      className="hover:bg-slate-50/50 transition-colors"
                    >
                      <td className="py-3 px-4 font-semibold text-slate-900">
                        {prod.product_name}
                      </td>
                      <td className="py-3 px-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-50 text-amber-900 border border-amber-200 text-xs font-bold">
                          {v.size}
                        </span>
                        {v.color && (
                          <span className="text-xs text-slate-500 ml-1.5">
                            ({v.color})
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 font-mono text-xs text-slate-600">
                        {v.sku}
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-slate-800">
                        {v.remaining}
                      </td>
                      <td className="py-3 px-3 text-right font-semibold text-amber-700">
                        {v.demand}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {hasDeficit ? (
                          <span className="inline-flex items-center gap-1 text-2xs font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-md border border-rose-200">
                            <AlertTriangle className="w-3 h-3" />
                            Stock Deficit
                          </span>
                        ) : isSoldOut ? (
                          <span className="inline-flex items-center gap-1 text-2xs font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                            <XCircle className="w-3 h-3" />
                            Sold Out
                          </span>
                        ) : isLow ? (
                          <span className="inline-flex items-center gap-1 text-2xs font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
                            <AlertTriangle className="w-3 h-3" />
                            Low Stock
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-2xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                            <CheckCircle2 className="w-3 h-3" />
                            Healthy
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
