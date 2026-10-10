import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { formatINR } from '../../../lib/formatINR';
import { useAuth } from '../../../context/AuthContext';
import { hasMinimumRole } from '../../../types/api';

export const CartDrawer: React.FC = () => {
  const {
    items,
    isCartOpen,
    setIsCartOpen,
    updateQuantity,
    removeFromCart,
    subtotalPaise,
    totalItems,
    revalidateCart,
  } = useCart();

  const { user } = useAuth();
  const navigate = useNavigate();
  const [revalidateWarnings, setRevalidateWarnings] = useState<string[]>([]);
  const [isRevalidating, setIsRevalidating] = useState(false);

  // Trigger revalidation when drawer opens
  useEffect(() => {
    if (isCartOpen && items.length > 0) {
      setIsRevalidating(true);
      revalidateCart()
        .then((result) => {
          if (result.changed && result.messages.length > 0) {
            setRevalidateWarnings(result.messages);
          } else {
            setRevalidateWarnings([]);
          }
        })
        .finally(() => setIsRevalidating(false));
    }
  }, [isCartOpen, items.length, revalidateCart]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isCartOpen) {
        setIsCartOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCartOpen, setIsCartOpen]);

  if (!isCartOpen) return null;

  const isMember = hasMinimumRole(user?.role || 'guest', 'member');

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden"
      aria-labelledby="cart-drawer-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
        onClick={() => setIsCartOpen(false)}
        aria-hidden="true"
      />

      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10">
        <div className="w-screen max-w-md bg-white shadow-2xl flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <div className="flex items-center gap-2">
              <h2 id="cart-drawer-title" className="text-lg font-bold text-slate-900">
                Your Cart
              </h2>
              <span className="inline-flex items-center rounded-full bg-primary-100 px-2.5 py-0.5 text-xs font-semibold text-primary-800">
                {totalItems} {totalItems === 1 ? 'item' : 'items'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setIsCartOpen(false)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
              aria-label="Close cart"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Revalidation alerts */}
          {revalidateWarnings.length > 0 && (
            <div className="bg-amber-50 border-b border-amber-200 p-4 text-xs text-amber-800 space-y-1">
              <div className="font-semibold flex items-center gap-1.5 text-amber-900">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                Stock updates adjusted your cart:
              </div>
              <ul className="list-disc pl-5 space-y-0.5">
                {revalidateWarnings.map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Cart Items List */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-12">
                <div className="h-16 w-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-4">
                  <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
                    />
                  </svg>
                </div>
                <h3 className="text-base font-semibold text-slate-900">Your cart is empty</h3>
                <p className="mt-1 text-sm text-slate-500 max-w-xs">
                  Official club tees, hoodies, and accessories are waiting for you in the shop.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setIsCartOpen(false);
                    navigate('/shop');
                  }}
                  className="mt-6 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 transition-colors"
                >
                  Explore Merchandise
                </button>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {items.map((item) => (
                  <li key={item.variantId} className="py-4 flex gap-4">
                    <div className="h-20 w-20 flex-shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 flex items-center justify-center">
                      {item.imageUrl ? (
                        <img
                          src={item.imageUrl}
                          alt={item.productName}
                          className="h-full w-full object-cover object-center"
                        />
                      ) : (
                        <svg className="h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                        </svg>
                      )}
                    </div>

                    <div className="flex flex-1 flex-col justify-between">
                      <div className="flex justify-between items-start">
                        <div>
                          <h4 className="text-sm font-semibold text-slate-900">{item.productName}</h4>
                          <span className="inline-block mt-0.5 rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                            Size: {item.size}
                          </span>
                        </div>
                        <span className="text-sm font-bold text-slate-900">
                          {formatINR(item.unitPrice * item.quantity)}
                        </span>
                      </div>

                      <div className="flex items-center justify-between mt-3">
                        <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                          <button
                            type="button"
                            onClick={() => updateQuantity(item.variantId, item.quantity - 1)}
                            className="rounded p-1 text-slate-500 hover:bg-white hover:text-slate-800 transition-colors"
                            aria-label={`Decrease quantity of ${item.productName}`}
                          >
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                            </svg>
                          </button>
                          <span className="px-2.5 text-xs font-semibold text-slate-800">
                            {item.quantity}
                          </span>
                          <button
                            type="button"
                            disabled={item.quantity >= item.maxStock}
                            onClick={() => updateQuantity(item.variantId, item.quantity + 1)}
                            className="rounded p-1 text-slate-500 hover:bg-white hover:text-slate-800 transition-colors disabled:opacity-40 disabled:hover:bg-transparent"
                            aria-label={`Increase quantity of ${item.productName}`}
                          >
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                          </button>
                        </div>

                        <button
                          type="button"
                          onClick={() => removeFromCart(item.variantId)}
                          className="text-xs font-medium text-rose-600 hover:text-rose-700 hover:underline"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Footer */}
          {items.length > 0 && (
            <div className="border-t border-slate-200 bg-slate-50/50 p-6 space-y-4">
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm text-slate-600">
                  <span>Subtotal</span>
                  <span className="font-semibold text-slate-900">{formatINR(subtotalPaise)}</span>
                </div>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>Fulfillment</span>
                  <span>Campus pickup / delivery</span>
                </div>
              </div>

              {!isMember && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 flex items-start gap-2.5">
                  <svg className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <div>
                    <span className="font-semibold">Membership required to order:</span> Only active members can place merchandise orders.
                    <button
                      type="button"
                      onClick={() => {
                        setIsCartOpen(false);
                        navigate('/join');
                      }}
                      className="ml-1 text-primary-700 underline font-semibold hover:text-primary-800"
                    >
                      Join SSA now →
                    </button>
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  disabled={isRevalidating}
                  onClick={() => {
                    setIsCartOpen(false);
                    if (!user) {
                      navigate('/login?redirect=/shop/checkout');
                    } else if (!isMember) {
                      navigate('/join');
                    } else {
                      navigate('/shop/checkout');
                    }
                  }}
                  className="w-full rounded-xl bg-primary-600 py-3 text-center text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-all"
                >
                  {!user
                    ? 'Log in to Checkout'
                    : !isMember
                    ? 'Join to Complete Order'
                    : 'Proceed to Checkout'}
                </button>

                <button
                  type="button"
                  onClick={() => setIsCartOpen(false)}
                  className="w-full text-center text-xs text-slate-500 hover:text-slate-700 py-1"
                >
                  Continue Shopping
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
