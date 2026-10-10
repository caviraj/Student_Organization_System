import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { shopApi } from '../../../api/shop';
import { OrderCard } from '../components/OrderCard';
import { StockSummaryTable } from '../components/StockSummaryTable';
import { Modal } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { useToast } from '../../../components/ui/Toast';
import type { MerchOrder, FulfillmentStatus } from '../types';
import type { PaginatedResponse } from '../../../types/api';
import {
  Kanban,
  Table,
  Search,
  Package,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';

export function AdminMerchOrders() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<'board' | 'stock'>('board');
  const [searchTerm, setSearchTerm] = useState('');

  // Confirmation modal state for backward transitions
  const [revertModalOpen, setRevertModalOpen] = useState(false);
  const [revertTarget, setRevertTarget] = useState<{
    orderId: string;
    newStatus: FulfillmentStatus;
    oldStatus: FulfillmentStatus;
  } | null>(null);

  // Fetch all merch orders
  const {
    data: ordersData,
    isLoading,
  } = useQuery({
    queryKey: ['adminMerchOrders'],
    queryFn: () => shopApi.getAdminMerchOrders({ page_size: 100 }),
  });

  const orders = ordersData?.items || [];

  // Update status mutation with optimistic update & rollback
  const updateStatusMutation = useMutation({
    mutationFn: ({
      orderId,
      status,
    }: {
      orderId: string;
      status: FulfillmentStatus;
    }) => shopApi.updateFulfillmentStatus(orderId, status),
    onMutate: async ({ orderId, status }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['adminMerchOrders'] });

      // Snapshot previous value
      const previousData = queryClient.getQueryData<PaginatedResponse<MerchOrder>>([
        'adminMerchOrders',
      ]);

      // Optimistically update cache
      if (previousData) {
        queryClient.setQueryData<PaginatedResponse<MerchOrder>>(
          ['adminMerchOrders'],
          {
            ...previousData,
            items: previousData.items.map((ord) =>
              ord.id === orderId ? { ...ord, fulfilment_status: status } : ord
            ),
          }
        );
      }

      return { previousData };
    },
    onError: (err: any, _, context) => {
      // Rollback on error
      if (context?.previousData) {
        queryClient.setQueryData(['adminMerchOrders'], context.previousData);
      }
      toast.show(
        err.error?.message || err.message || 'Failed to update order status.',
        'error'
      );
    },
    onSuccess: (data) => {
      toast.show(
        `Order #${data.id.slice(-6).toUpperCase()} updated to ${data.fulfilment_status.replace(
          '_',
          ' '
        )}!`,
        'success'
      );
      queryClient.invalidateQueries({ queryKey: ['adminMerchOrders'] });
      queryClient.invalidateQueries({ queryKey: ['adminStockSummary'] });
    },
  });

  const handleStatusChange = (
    orderId: string,
    newStatus: FulfillmentStatus,
    direction: 'forward' | 'backward'
  ) => {
    const order = orders.find((o) => o.id === orderId);
    if (!order) return;

    if (direction === 'backward') {
      // Open confirmation modal for backward transition
      setRevertTarget({
        orderId,
        newStatus,
        oldStatus: order.fulfilment_status,
      });
      setRevertModalOpen(true);
    } else {
      // Execute forward transition optimistically
      updateStatusMutation.mutate({ orderId, status: newStatus });
    }
  };

  const handleConfirmRevert = () => {
    if (!revertTarget) return;
    updateStatusMutation.mutate({
      orderId: revertTarget.orderId,
      status: revertTarget.newStatus,
    });
    setRevertModalOpen(false);
    setRevertTarget(null);
  };

  // Filter orders by search term
  const filteredOrders = orders.filter((o) => {
    const term = searchTerm.toLowerCase();
    return (
      o.id.toLowerCase().includes(term) ||
      (o.user_name && o.user_name.toLowerCase().includes(term)) ||
      (o.user_email && o.user_email.toLowerCase().includes(term)) ||
      (o.delivery_note && o.delivery_note.toLowerCase().includes(term)) ||
      o.items.some((i) => i.product_name.toLowerCase().includes(term))
    );
  });

  // Group orders into kanban columns
  const paidOrders = filteredOrders.filter((o) => o.fulfilment_status === 'paid');
  const packedOrders = filteredOrders.filter((o) => o.fulfilment_status === 'packed');
  const handedOverOrders = filteredOrders.filter(
    (o) => o.fulfilment_status === 'handed_over'
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2.5">
            <Package className="w-6 h-6 text-amber-600" />
            Merchandise Fulfillment Board
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Track merchandise orders from payment through packing and student handover.
          </p>
        </div>

        {/* Tab switchers */}
        <div className="flex items-center p-1 rounded-xl bg-slate-100 border border-slate-200 self-start sm:self-auto">
          <button
            onClick={() => setActiveTab('board')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'board'
                ? 'bg-white text-slate-900 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Kanban className="w-3.5 h-3.5 text-amber-600" />
            Order Board
          </button>
          <button
            onClick={() => setActiveTab('stock')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'stock'
                ? 'bg-white text-slate-900 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Table className="w-3.5 h-3.5 text-amber-600" />
            Stock Summary
          </button>
        </div>
      </div>

      {activeTab === 'stock' ? (
        <StockSummaryTable />
      ) : (
        <div className="space-y-4">
          {/* Search bar */}
          <div className="bg-white p-3.5 rounded-xl border border-slate-200 flex items-center gap-3">
            <div className="relative w-full sm:w-80">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search orders by customer or product..."
                className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-hidden focus:ring-2 focus:ring-amber-500"
              />
            </div>
            <span className="text-xs text-slate-400 hidden sm:inline">
              Showing {filteredOrders.length} orders
            </span>
          </div>

          {/* 3-Column Kanban Board */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
            {/* Column 1: Paid */}
            <div className="bg-slate-50 rounded-2xl border border-slate-200 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  <h3 className="font-bold text-slate-800 text-sm">Paid (To Pack)</h3>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-xs font-bold">
                  {paidOrders.length}
                </span>
              </div>
              <p className="text-2xs text-slate-500">
                Payment verified. Ready for club volunteers to pack.
              </p>

              <div className="space-y-3 pt-1">
                {isLoading ? (
                  <div className="p-4 bg-white rounded-xl border border-slate-200 animate-pulse h-28" />
                ) : paidOrders.length === 0 ? (
                  <div className="p-6 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
                    No orders waiting to be packed
                  </div>
                ) : (
                  paidOrders.map((ord) => (
                    <OrderCard
                      key={ord.id}
                      order={ord}
                      onStatusChange={handleStatusChange}
                      isUpdating={updateStatusMutation.isPending}
                    />
                  ))
                )}
              </div>
            </div>

            {/* Column 2: Packed */}
            <div className="bg-slate-50 rounded-2xl border border-slate-200 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                  <h3 className="font-bold text-slate-800 text-sm">Packed (Ready)</h3>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-xs font-bold">
                  {packedOrders.length}
                </span>
              </div>
              <p className="text-2xs text-slate-500">
                Packed and staged for student pickup or dispatch.
              </p>

              <div className="space-y-3 pt-1">
                {isLoading ? (
                  <div className="p-4 bg-white rounded-xl border border-slate-200 animate-pulse h-28" />
                ) : packedOrders.length === 0 ? (
                  <div className="p-6 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
                    No packed orders awaiting collection
                  </div>
                ) : (
                  packedOrders.map((ord) => (
                    <OrderCard
                      key={ord.id}
                      order={ord}
                      onStatusChange={handleStatusChange}
                      isUpdating={updateStatusMutation.isPending}
                    />
                  ))
                )}
              </div>
            </div>

            {/* Column 3: Handed Over */}
            <div className="bg-slate-50 rounded-2xl border border-slate-200 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  <h3 className="font-bold text-slate-800 text-sm">Handed Over</h3>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold">
                  {handedOverOrders.length}
                </span>
              </div>
              <p className="text-2xs text-slate-500">
                Successfully collected by students / delivered.
              </p>

              <div className="space-y-3 pt-1">
                {isLoading ? (
                  <div className="p-4 bg-white rounded-xl border border-slate-200 animate-pulse h-28" />
                ) : handedOverOrders.length === 0 ? (
                  <div className="p-6 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
                    No fulfilled orders yet
                  </div>
                ) : (
                  handedOverOrders.map((ord) => (
                    <OrderCard
                      key={ord.id}
                      order={ord}
                      onStatusChange={handleStatusChange}
                      isUpdating={updateStatusMutation.isPending}
                    />
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Backward Transition Confirmation Modal */}
      <Modal
        isOpen={revertModalOpen}
        onClose={() => {
          setRevertModalOpen(false);
          setRevertTarget(null);
        }}
        title="Confirm Status Reversion"
        description="Reverting an order's fulfillment status affects student tracking and volunteer inventory counts."
        maxWidth="sm"
      >
        <div className="space-y-4">
          <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-900 space-y-1">
              <p className="font-semibold">
                Revert order #{revertTarget?.orderId.slice(-6).toUpperCase()}?
              </p>
              <p>
                Status will change from{' '}
                <span className="font-bold">
                  {revertTarget?.oldStatus.replace('_', ' ')}
                </span>{' '}
                back to{' '}
                <span className="font-bold">
                  {revertTarget?.newStatus.replace('_', ' ')}
                </span>
                .
              </p>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRevertModalOpen(false);
                setRevertTarget(null);
              }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="bg-amber-600 hover:bg-amber-700 text-white"
              isLoading={updateStatusMutation.isPending}
              onClick={handleConfirmRevert}
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              Confirm Revert
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
