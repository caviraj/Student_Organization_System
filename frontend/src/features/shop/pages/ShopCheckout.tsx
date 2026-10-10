import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useCart } from '../context/CartContext';
import { useAuth } from '../../../context/AuthContext';
import { shopApi } from '../../../api/shop';
import { formatINR } from '../../../lib/formatINR';
import { useToast } from '../../../components/ui/Toast';

import { hasMinimumRole } from '../../../types/api';

export const ShopCheckout: React.FC = () => {
  const { items, subtotalPaise, clearCart, revalidateCart } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  const [fulfillmentType, setFulfillmentType] = useState<'pickup' | 'delivery'>('pickup');
  const [deliveryNote, setDeliveryNote] = useState('');
  const [phone, setPhone] = useState('');

  const isMember = user ? hasMinimumRole(user.role, 'member') : false;

  const checkoutMutation = useMutation({
    mutationFn: () => {
      const payloadItems = items.map((item) => ({
        variant_id: item.variant_id,
        qty: item.qty,
      }));
      const note =
        fulfillmentType === 'pickup'
          ? `Campus Pickup${phone ? ` (Phone: ${phone})` : ''}${deliveryNote ? ` - Note: ${deliveryNote}` : ''}`
          : `Delivery${phone ? ` (Phone: ${phone})` : ''}: ${deliveryNote || 'Campus delivery'}`;

      return shopApi.checkoutMerch({
        items: payloadItems,
        delivery_note: note,
      });
    },
    onSuccess: (data) => {
      clearCart();
      navigate(`/checkout/${data.order_id}`, {
        state: {
          checkoutData: {
            order_id: data.order_id,
            amount: data.amount,
            is_merch: true,
            order_type: 'merch',
            items_count: items.reduce((s, i) => s + i.qty, 0),
            delivery_note: deliveryNote || (fulfillmentType === 'pickup' ? 'Campus Pickup' : 'Campus Delivery'),
          },
        },
      });
    },
    onError: async (error: any) => {
      const errCode = error?.error?.code || error?.code;
      const errMsg = error?.error?.message || error?.message || 'Checkout failed.';

      if (errCode === 'SOLD_OUT' || errMsg.toLowerCase().includes('sold out') || errMsg.toLowerCase().includes('stock')) {
        toast.show(
          `Stock error: ${errMsg}. We have updated your cart with current availability.`,
          'error'
        );
        // Do not clear cart on 409! Revalidate so user can adjust
        await revalidateCart();
      } else if (errCode === 'MEMBERSHIP_REQUIRED') {
        toast.show('Active SSA Membership is required to purchase merchandise.', 'error');
      } else {
        toast.show(errMsg, 'error');
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (items.length === 0) return;
    if (!isMember) {
      toast.show('You must be an active club member to complete merchandise checkout.', 'error');
      return;
    }
    checkoutMutation.mutate();
  };

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center">
        <div className="mx-auto h-16 w-16 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 mb-4">
          <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-slate-900">Your cart is empty</h2>
        <p className="mt-2 text-sm text-slate-500">
          Add items from our merchandise store to proceed with member checkout.
        </p>
        <Link
          to="/shop"
          className="mt-6 inline-flex rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
        >
          Return to Shop
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50/60 py-10">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <Link to="/shop" className="text-xs font-semibold text-primary-600 hover:underline">
            ← Continue Shopping
          </Link>
          <h1 className="mt-2 text-3xl font-extrabold text-slate-900 tracking-tight">
            Merchandise Checkout
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Review your order items, select pickup or delivery, and proceed to payment.
          </p>
        </div>

        {/* Member Check Warning */}
        {!isMember && (
          <div className="mb-8 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-900 flex items-start gap-3">
            <svg className="h-6 w-6 text-amber-600 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="flex-1">
              <h3 className="text-sm font-bold">Active Membership Required</h3>
              <p className="mt-0.5 text-xs text-amber-800">
                Official merchandise purchases are reserved for registered SSA club members. Join now to complete your order.
              </p>
              <div className="mt-3">
                <Link
                  to="/join"
                  className="rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-amber-700"
                >
                  Join SSA Membership →
                </Link>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left Column: Fulfillment Details */}
          <div className="lg:col-span-7 space-y-6">
            {/* Fulfillment Options */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <h2 className="text-base font-bold text-slate-900">1. Fulfillment Method</h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup">
                <label
                  className={`flex flex-col rounded-2xl border p-4 cursor-pointer transition-all ${
                    fulfillmentType === 'pickup'
                      ? 'border-primary-600 bg-primary-50/50 ring-1 ring-primary-500'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">Campus Pickup</span>
                    <input
                      type="radio"
                      name="fulfillment"
                      value="pickup"
                      checked={fulfillmentType === 'pickup'}
                      onChange={() => setFulfillmentType('pickup')}
                      className="text-primary-600 focus:ring-primary-500"
                    />
                  </div>
                  <span className="mt-2 text-xs text-slate-500 leading-relaxed">
                    Collect directly from the SSA Club Desk / Student Union after packing. Free.
                  </span>
                </label>

                <label
                  className={`flex flex-col rounded-2xl border p-4 cursor-pointer transition-all ${
                    fulfillmentType === 'delivery'
                      ? 'border-primary-600 bg-primary-50/50 ring-1 ring-primary-500'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">Campus Delivery</span>
                    <input
                      type="radio"
                      name="fulfillment"
                      value="delivery"
                      checked={fulfillmentType === 'delivery'}
                      onChange={() => setFulfillmentType('delivery')}
                      className="text-primary-600 focus:ring-primary-500"
                    />
                  </div>
                  <span className="mt-2 text-xs text-slate-500 leading-relaxed">
                    Delivered to your campus hostel block or departmental lobby during festival days.
                  </span>
                </label>
              </div>

              {/* Delivery Note / Instructions */}
              <div className="space-y-1.5 pt-2">
                <label htmlFor="deliveryNote" className="block text-xs font-semibold text-slate-700">
                  {fulfillmentType === 'delivery' ? 'Hostel / Room / Dept Address' : 'Pickup Note (Optional)'}
                </label>
                <textarea
                  id="deliveryNote"
                  rows={2}
                  value={deliveryNote}
                  onChange={(e) => setDeliveryNote(e.target.value)}
                  placeholder={
                    fulfillmentType === 'delivery'
                      ? 'e.g., Brahmaputra Hostel, Room 314, Block B'
                      : 'e.g., Preferred collection after 5 PM'
                  }
                  className="w-full rounded-xl border border-slate-200 p-3 text-xs text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                />
              </div>

              {/* Contact Phone */}
              <div className="space-y-1.5">
                <label htmlFor="phone" className="block text-xs font-semibold text-slate-700">
                  WhatsApp / Contact Number
                </label>
                <input
                  type="tel"
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="e.g. +91 98765 43210"
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                />
                <span className="text-[11px] text-slate-400">
                  We'll message you once your apparel is packed and ready for pickup.
                </span>
              </div>
            </div>

            {/* Member Details Review */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-3">
              <h2 className="text-base font-bold text-slate-900">2. Member Profile</h2>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-slate-400">Name:</span>
                  <div className="font-semibold text-slate-800">{user?.full_name || 'Member'}</div>
                </div>
                <div>
                  <span className="text-slate-400">Email:</span>
                  <div className="font-semibold text-slate-800">{user?.email || '—'}</div>
                </div>
                <div>
                  <span className="text-slate-400">Membership Status:</span>
                  <div className="font-semibold text-emerald-600 capitalize">
                    {user?.role || 'Guest'}
                  </div>
                </div>
                <div>
                  <span className="text-slate-400">Campus ID / Dept:</span>
                  <div className="font-semibold text-slate-800">
                    {user?.department ? `${user.department}${user.year ? ` (Yr ${user.year})` : ''}` : 'SSA-MEMBER'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Order Summary */}
          <div className="lg:col-span-5">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sticky top-6 space-y-6">
              <h2 className="text-base font-bold text-slate-900">Order Summary</h2>

              {/* Items List */}
              <ul className="divide-y divide-slate-100 max-h-72 overflow-y-auto pr-1">
                {items.map((item) => (
                  <li key={item.variant_id} className="py-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="h-12 w-12 rounded-lg bg-slate-100 border border-slate-200 overflow-hidden flex-shrink-0 flex items-center justify-center">
                        {item.image_url ? (
                          <img src={item.image_url} alt={item.product_name} className="h-full w-full object-cover" />
                        ) : (
                          <span className="text-[10px] font-bold text-slate-400">{item.size}</span>
                        )}
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900 line-clamp-1">{item.product_name}</h4>
                        <span className="text-[11px] text-slate-500">
                          Size {item.size} × {item.qty}
                        </span>
                      </div>
                    </div>
                    <span className="text-xs font-bold text-slate-900 shrink-0">
                      {formatINR(item.unit_price * item.qty)}
                    </span>
                  </li>
                ))}
              </ul>

              {/* Cost Breakdown */}
              <div className="border-t border-slate-100 pt-4 space-y-2 text-xs">
                <div className="flex justify-between text-slate-600">
                  <span>Subtotal</span>
                  <span className="font-semibold text-slate-900">{formatINR(subtotalPaise)}</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Campus Delivery / Pickup</span>
                  <span className="font-semibold text-emerald-600">FREE</span>
                </div>
                <div className="border-t border-slate-200 pt-3 flex justify-between items-baseline">
                  <span className="text-sm font-bold text-slate-900">Total Payable</span>
                  <span className="text-2xl font-black text-primary-700">
                    {formatINR(subtotalPaise)}
                  </span>
                </div>
              </div>

              {/* Submit CTA */}
              <button
                type="submit"
                disabled={checkoutMutation.isPending || !isMember}
                className="w-full rounded-2xl bg-primary-600 py-3.5 text-center text-sm font-bold text-white shadow-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {checkoutMutation.isPending ? 'Reserving Items...' : 'Proceed to Payment →'}
              </button>

              <div className="text-center text-[11px] text-slate-400">
                🔒 Safe simulated payment powered by SSA Hub Payment Gateway.
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
