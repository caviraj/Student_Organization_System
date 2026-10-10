import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { shopApi } from '../../../api/shop';
import { SizeSelector } from '../components/SizeSelector';
import { useCart } from '../context/CartContext';
import { useAuth } from '../../../context/AuthContext';
import { hasMinimumRole } from '../../../types/api';
import { formatINR } from '../../../lib/formatINR';
import type { ProductVariant } from '../types';
import { Skeleton } from '../../../components/ui/Skeleton';
import { ErrorState } from '../../../components/ui/ErrorState';

export const ProductDetail = () => {
  const { productId } = useParams<{ productId: string }>();
  const { user } = useAuth();
  const { addToCart } = useCart();

  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedToast, setAddedToast] = useState(false);

  const {
    data: product,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['product', productId],
    queryFn: () => shopApi.getProduct(productId!),
    enabled: !!productId,
  });

  // Default to first in-stock variant when loaded
  useEffect(() => {
    if (product && product.variants?.length) {
      const inStock = product.variants.find((v) => v.stock > 0);
      setSelectedVariant(inStock || product.variants[0]);
    }
  }, [product]);

  // Adjust quantity if selected variant's stock is less
  useEffect(() => {
    if (selectedVariant && quantity > selectedVariant.stock) {
      setQuantity(Math.max(1, selectedVariant.stock));
    }
  }, [selectedVariant, quantity]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <Skeleton className="h-6 w-32 rounded mb-6" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
          <Skeleton className="aspect-square w-full rounded-2xl" />
          <div className="space-y-6">
            <Skeleton className="h-8 w-3/4 rounded" />
            <Skeleton className="h-6 w-1/3 rounded" />
            <Skeleton className="h-20 w-full rounded" />
            <Skeleton className="h-12 w-full rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <ErrorState
          title="Product not found"
          message="The merchandise you are looking for does not exist or has been retired."
          onRetry={() => refetch()}
        />
        <div className="mt-4 text-center">
          <Link to="/shop" className="text-sm font-semibold text-primary-600 hover:underline">
            ← Back to Shop
          </Link>
        </div>
      </div>
    );
  }

  const isMember = hasMinimumRole(user?.role || 'guest', 'member');
  const basePrice = product.base_price;
  const discountPercent = product.member_discount_pct || 0;
  const memberPrice = Math.round(basePrice * (1 - discountPercent / 100));
  const effectivePrice = isMember && discountPercent > 0 ? memberPrice : basePrice;

  const isSoldOut = !selectedVariant || selectedVariant.stock === 0;

  const handleAddToCart = () => {
    if (!selectedVariant || isSoldOut) return;

    addToCart(
      {
        product_id: product.id,
        productId: product.id,
        product_name: product.name,
        productName: product.name,
        variant_id: selectedVariant.id,
        variantId: selectedVariant.id,
        size: selectedVariant.size,
        color: selectedVariant.color,
        unit_price: effectivePrice,
        unitPrice: effectivePrice,
        base_price: product.base_price,
        member_discount_pct: product.member_discount_pct,
        stock: selectedVariant.stock,
        maxStock: selectedVariant.stock,
        image_url: product.image_url,
        imageUrl: product.image_url,
      },
      quantity
    );

    setAddedToast(true);
    setTimeout(() => setAddedToast(false), 3000);
  };

  return (
    <div className="min-h-screen bg-slate-50/50 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb Navigation */}
        <nav className="mb-6 flex items-center gap-2 text-xs font-medium text-slate-500">
          <Link to="/shop" className="hover:text-primary-600 transition-colors">
            Merchandise
          </Link>
          <span>/</span>
          <span className="capitalize">Apparel</span>
          <span>/</span>
          <span className="text-slate-800 truncate max-w-xs">{product.name}</span>
        </nav>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 bg-white rounded-3xl border border-slate-200/80 p-6 sm:p-10 shadow-sm">
          {/* Left Column: Product Image */}
          <div className="lg:col-span-6 flex flex-col items-center">
            <div className="relative aspect-square w-full max-w-lg overflow-hidden rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200/60 border border-slate-100 flex items-center justify-center">
              {product.image_url ? (
                <img
                  src={product.image_url}
                  alt={product.name}
                  className="h-full w-full object-cover object-center"
                />
              ) : (
                <div className="flex flex-col items-center justify-center text-slate-400 p-8 text-center">
                  <svg className="h-24 w-24 stroke-1 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                  </svg>
                  <span className="mt-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
                    {product.name}
                  </span>
                </div>
              )}

              {discountPercent > 0 && (
                <span className="absolute top-4 left-4 rounded-full bg-emerald-500 px-3 py-1 text-xs font-bold text-white shadow-md">
                  {discountPercent}% Member Discount
                </span>
              )}
            </div>
          </div>

          {/* Right Column: Details & Ordering */}
          <div className="lg:col-span-6 flex flex-col justify-between">
            <div className="space-y-6">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-primary-600">
                  Official SSA Merch
                </span>
                <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  {product.name}
                </h1>
              </div>

              {/* Pricing section */}
              <div className="rounded-2xl bg-slate-50 border border-slate-100 p-4">
                <div className="flex items-baseline gap-3">
                  <span className="text-3xl font-extrabold text-slate-900">
                    {formatINR(effectivePrice)}
                  </span>
                  {discountPercent > 0 && (
                    <span className="text-base text-slate-400 line-through font-medium">
                      {formatINR(basePrice)}
                    </span>
                  )}
                </div>

                {!isMember && discountPercent > 0 && (
                  <p className="mt-2 text-xs font-medium text-emerald-700 flex items-center gap-1.5">
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>
                      SSA Members pay <strong className="font-bold">{formatINR(memberPrice)}</strong> ({discountPercent}% off).{' '}
                      <Link to="/join" className="underline font-bold hover:text-emerald-900">
                        Join club
                      </Link>
                    </span>
                  </p>
                )}
              </div>

              {/* Description */}
              <div>
                <h3 className="text-sm font-semibold text-slate-900 mb-2">Description</h3>
                <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">
                  {product.description}
                </p>
              </div>

              {/* Size Selector */}
              {product.variants && product.variants.length > 0 && (
                <div className="pt-2 border-t border-slate-100">
                  <SizeSelector
                    variants={product.variants}
                    selectedVariantId={selectedVariant?.id || null}
                    onSelectVariant={(variant) => setSelectedVariant(variant)}
                  />
                </div>
              )}

              {/* Quantity Stepper */}
              {!isSoldOut && selectedVariant && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <label className="block text-sm font-medium text-slate-700">Quantity</label>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center rounded-xl border border-slate-200 bg-slate-50 p-1">
                      <button
                        type="button"
                        onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                        disabled={quantity <= 1}
                        className="rounded-lg p-2 text-slate-500 hover:bg-white hover:text-slate-800 disabled:opacity-40 transition-colors"
                        aria-label="Decrease quantity"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                        </svg>
                      </button>
                      <span className="w-12 text-center text-sm font-bold text-slate-900">
                        {quantity}
                      </span>
                      <button
                        type="button"
                        onClick={() => setQuantity((q) => Math.min(selectedVariant.stock, q + 1))}
                        disabled={quantity >= selectedVariant.stock}
                        className="rounded-lg p-2 text-slate-500 hover:bg-white hover:text-slate-800 disabled:opacity-40 transition-colors"
                        aria-label="Increase quantity"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                      </button>
                    </div>

                    <span className="text-xs text-slate-500">
                      (Maximum {selectedVariant.stock} available)
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Actions & Ordering CTAs */}
            <div className="mt-8 space-y-4 pt-6 border-t border-slate-100">
              {addedToast && (
                <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-xs font-semibold text-emerald-800 flex items-center justify-between">
                  <span>Item added to your cart!</span>
                  <Link to="/shop" className="underline hover:text-emerald-950">
                    Keep browsing
                  </Link>
                </div>
              )}

              <button
                type="button"
                data-testid="add-to-cart-button"
                disabled={isSoldOut}
                onClick={handleAddToCart}
                className={`w-full rounded-2xl py-4 text-center text-base font-bold shadow-md transition-all ${
                  isSoldOut
                    ? 'bg-slate-100 text-slate-400 cursor-not-allowed border border-slate-200'
                    : 'bg-primary-600 text-white hover:bg-primary-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2'
                }`}
              >
                {isSoldOut ? 'Sold Out' : 'Add to Cart'}
              </button>

              {!isMember && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-center">
                  <p className="text-xs text-slate-600">
                    Merchandise orders are restricted to active SSA club members.
                  </p>
                  <Link
                    to="/join"
                    className="mt-2 inline-flex items-center text-xs font-bold text-primary-700 hover:text-primary-800 underline"
                  >
                    Join SSA Membership to Order →
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
