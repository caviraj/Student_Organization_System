import React from 'react';
import { CANONICAL_SIZES, type ProductVariant } from '../types';

interface SizeSelectorProps {
  variants: ProductVariant[];
  selectedVariantId: string | null;
  onSelectVariant: (variant: ProductVariant) => void;
  lowStockThreshold?: number;
}

export function sortVariantsByCanonicalSize(variants: ProductVariant[]): ProductVariant[] {
  return [...variants].sort((a, b) => {
    const aUpper = a.size.toUpperCase().trim();
    const bUpper = b.size.toUpperCase().trim();
    const aIdx = CANONICAL_SIZES.indexOf(aUpper as (typeof CANONICAL_SIZES)[number]);
    const bIdx = CANONICAL_SIZES.indexOf(bUpper as (typeof CANONICAL_SIZES)[number]);

    if (aIdx !== -1 && bIdx !== -1) {
      return aIdx - bIdx;
    }
    if (aIdx !== -1) return -1;
    if (bIdx !== -1) return 1;
    return a.size.localeCompare(b.size);
  });
}

export const SizeSelector: React.FC<SizeSelectorProps> = ({
  variants,
  selectedVariantId,
  onSelectVariant,
  lowStockThreshold = 5,
}) => {
  const sortedVariants = sortVariantsByCanonicalSize(variants);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm font-medium text-slate-700">
        <span>Select Size</span>
        {selectedVariantId && (() => {
          const selected = sortedVariants.find((v) => v.id === selectedVariantId);
          if (!selected) return null;
          if (selected.stock === 0) {
            return <span className="text-rose-600 font-semibold">Sold out</span>;
          }
          if (selected.stock <= (selected.low_stock_threshold || lowStockThreshold)) {
            return (
              <span className="text-amber-600 font-semibold">
                Only {selected.stock} left in stock
              </span>
            );
          }
          return <span className="text-emerald-600">In stock ({selected.stock} available)</span>;
        })()}
      </div>

      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Available sizes">
        {sortedVariants.map((variant) => {
          const isSelected = variant.id === selectedVariantId;
          const isSoldOut = variant.stock === 0;
          const isLowStock =
            variant.stock > 0 &&
            variant.stock <= (variant.low_stock_threshold || lowStockThreshold);

          return (
            <button
              key={variant.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={isSoldOut}
              onClick={() => onSelectVariant(variant)}
              data-testid={`size-button-${variant.size}`}
              className={`relative px-4 py-2.5 rounded-lg border font-medium text-sm transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${
                isSoldOut
                  ? 'border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed line-through'
                  : isSelected
                  ? 'border-primary-600 bg-primary-50 text-primary-700 shadow-sm ring-1 ring-primary-500'
                  : 'border-slate-200 bg-white text-slate-800 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <span>{variant.size}</span>
              {isSoldOut && (
                <span className="block text-[10px] uppercase tracking-wider font-semibold text-rose-500 mt-0.5">
                  Sold out
                </span>
              )}
              {isLowStock && !isSelected && (
                <span className="block text-[10px] font-medium text-amber-600 mt-0.5">
                  Only {variant.stock} left
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
