import { formatINR } from '../../../lib/formatINR';
import { formatDate } from '../../../lib/formatDate';
import type { MerchOrder, FulfillmentStatus } from '../types';
import { Button } from '../../../components/ui/Button';
import {
  Package,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Truck,
  Building,
  User,
} from 'lucide-react';

interface OrderCardProps {
  order: MerchOrder;
  onStatusChange: (
    orderId: string,
    newStatus: FulfillmentStatus,
    direction: 'forward' | 'backward'
  ) => void;
  isUpdating?: boolean;
}

export function OrderCard({
  order,
  onStatusChange,
  isUpdating = false,
}: OrderCardProps) {
  const isDelivery =
    order.delivery_note?.toLowerCase().includes('delivery') ||
    order.delivery_note?.toLowerCase().includes('address');

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs hover:shadow-xs transition-all space-y-3">
      {/* Header: Order ID & Date */}
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-2.5">
        <div>
          <span className="font-mono text-xs font-bold text-slate-800">
            #{order.id.slice(-6).toUpperCase()}
          </span>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5">
            <User className="w-3 h-3 text-slate-400" />
            <span className="font-medium text-slate-700 truncate max-w-[150px]">
              {order.user_name || order.user_email || 'Member'}
            </span>
          </div>
        </div>
        <span className="text-2xs text-slate-400 shrink-0">
          {formatDate(order.created_at)}
        </span>
      </div>

      {/* Fulfillment Note (Pickup or Delivery) */}
      <div
        className={`px-2.5 py-1.5 rounded-lg text-xs flex items-start gap-1.5 ${
          isDelivery
            ? 'bg-blue-50/70 text-blue-800 border border-blue-100'
            : 'bg-amber-50/70 text-amber-800 border border-amber-100'
        }`}
      >
        {isDelivery ? (
          <Truck className="w-3.5 h-3.5 shrink-0 mt-0.5 text-blue-600" />
        ) : (
          <Building className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-600" />
        )}
        <span className="line-clamp-2 text-2xs font-medium">
          {order.delivery_note || 'Campus club pickup'}
        </span>
      </div>

      {/* Items list */}
      <div className="space-y-1.5 py-1">
        {order.items.map((item, idx) => (
          <div
            key={idx}
            className="flex items-center justify-between text-xs text-slate-700"
          >
            <div className="flex items-center gap-1.5 truncate pr-2">
              <span className="font-bold text-slate-900 shrink-0">
                {item.qty}×
              </span>
              <span className="truncate text-slate-800 font-medium">
                {item.product_name}
              </span>
              <span className="px-1.5 py-0.2 rounded-sm bg-slate-100 text-slate-700 text-2xs font-semibold shrink-0">
                {item.size}
              </span>
            </div>
            <span className="text-slate-500 shrink-0 text-2xs font-mono">
              {formatINR(item.unit_price * item.qty)}
            </span>
          </div>
        ))}
      </div>

      {/* Total amount */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
        <span className="text-slate-500 font-medium">Total Paid</span>
        <span className="font-bold text-slate-900 text-sm">
          {formatINR(order.amount)}
        </span>
      </div>

      {/* Kanban Actions */}
      <div className="pt-2 flex items-center justify-between gap-2">
        {order.fulfilment_status === 'paid' && (
          <Button
            size="sm"
            disabled={isUpdating}
            onClick={() => onStatusChange(order.id, 'packed', 'forward')}
            className="w-full bg-amber-600 hover:bg-amber-700 text-white text-xs h-8"
          >
            <Package className="w-3.5 h-3.5 mr-1.5" />
            Mark Packed
            <ArrowRight className="w-3.5 h-3.5 ml-1" />
          </Button>
        )}

        {order.fulfilment_status === 'packed' && (
          <>
            <Button
              size="sm"
              variant="outline"
              disabled={isUpdating}
              onClick={() => onStatusChange(order.id, 'paid', 'backward')}
              className="text-xs h-8 px-2.5 text-slate-600 hover:text-slate-900"
              title="Revert to Paid"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" />
              Revert
            </Button>
            <Button
              size="sm"
              disabled={isUpdating}
              onClick={() => onStatusChange(order.id, 'handed_over', 'forward')}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8"
            >
              <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
              Hand Over
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </>
        )}

        {order.fulfilment_status === 'handed_over' && (
          <div className="flex items-center justify-between w-full">
            <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Completed
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={isUpdating}
              onClick={() => onStatusChange(order.id, 'packed', 'backward')}
              className="text-2xs h-7 px-2 text-slate-500 hover:text-slate-800"
              title="Revert to Packed"
            >
              <ArrowLeft className="w-3 h-3 mr-1" />
              Revert
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
