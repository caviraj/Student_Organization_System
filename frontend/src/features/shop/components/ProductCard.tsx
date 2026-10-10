import React from 'react';
import { Link } from 'react-router-dom';
import type { Product } from '../types';
import { formatINR } from '../../../lib/formatINR';
import { useAuth } from '../../../context/AuthContext';
import { hasMinimumRole } from '../../../types/api';

interface ProductCardProps {
  product: Product;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product }) => {
  const { user } = useAuth();
  const isMember = user ? hasMinimumRole(user.role, 'member') : false;

  // Calculate total stock across variants
  const totalStock = product.variants?.reduce((sum, v) => sum + v.stock, 0) ?? 0;
  const isSoldOut = totalStock === 0;

  // Compute price preview
  const basePrice = product.base_price;
  const memberDiscountPercent = product.member_discount_pct || 0;
  const memberPrice = Math.round(basePrice * (1 - memberDiscountPercent / 100));

  return (
    <div
      data-testid={`product-card-${product.id}`}
      className="group relative flex flex-col rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-slate-300 hover:shadow-md"
    >
      {/* Product Image / Visual banner */}
      <div className="relative aspect-square w-full overflow-hidden rounded-xl bg-gradient-to-br from-slate-100 to-slate-200/60">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.name}
            className="h-full w-full object-cover object-center transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center p-6 text-center text-slate-400">
            <svg
              className="h-16 w-16 stroke-1 text-slate-400/80 group-hover:text-primary-500 transition-colors"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
              />
            </svg>
            <span className="mt-2 text-xs font-medium uppercase tracking-wider text-slate-500">
              Merch
            </span>
          </div>
        )}

        {/* Badges */}
        <div className="absolute top-3 left-3 flex flex-col gap-1.5">
          {memberDiscountPercent > 0 && (
            <span className="inline-flex items-center rounded-full bg-emerald-500/90 px-2.5 py-0.5 text-xs font-bold text-white shadow-sm backdrop-blur-sm">
              {memberDiscountPercent}% Member Off
            </span>
          )}
          {isSoldOut && (
            <span className="inline-flex items-center rounded-full bg-rose-600/90 px-2.5 py-0.5 text-xs font-bold text-white shadow-sm backdrop-blur-sm">
              Sold out
            </span>
          )}
        </div>
      </div>

      {/* Info Section */}
      <div className="flex flex-1 flex-col pt-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
            Official Merch
          </span>
          <span className="text-xs text-slate-500">
            {product.variants?.length ? `${product.variants.length} sizes` : 'Single size'}
          </span>
        </div>

        <h3 className="mt-1 text-base font-semibold text-slate-900 group-hover:text-primary-600 transition-colors">
          <Link to={`/shop/${product.id}`} className="focus:outline-none">
            <span className="absolute inset-0" aria-hidden="true" />
            {product.name}
          </Link>
        </h3>

        <p className="mt-1 line-clamp-2 text-xs text-slate-500 flex-1">
          {product.description}
        </p>

        {/* Price & Action */}
        <div className="mt-4 flex items-baseline justify-between border-t border-slate-100 pt-3">
          <div>
            {isMember && memberDiscountPercent > 0 ? (
              <div className="flex items-baseline gap-1.5">
                <span className="text-lg font-bold text-slate-900">
                  {formatINR(memberPrice)}
                </span>
                <span className="text-xs text-slate-400 line-through">
                  {formatINR(basePrice)}
                </span>
              </div>
            ) : (
              <div className="flex flex-col">
                <span className="text-lg font-bold text-slate-900">
                  {formatINR(basePrice)}
                </span>
                {!isMember && memberDiscountPercent > 0 && (
                  <span className="text-[11px] font-medium text-emerald-600">
                    {formatINR(memberPrice)} for members
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="text-right">
            {isSoldOut ? (
              <span className="text-xs font-semibold text-rose-600">Sold out</span>
            ) : (
              <span className="text-xs font-medium text-primary-600 group-hover:underline">
                View options →
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
