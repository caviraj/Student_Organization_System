import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { shopApi } from '../../../api/shop';
import { ProductCard } from '../components/ProductCard';
import { useCart } from '../context/CartContext';
import { useAuth } from '../../../context/AuthContext';
import { Skeleton } from '../../../components/ui/Skeleton';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ErrorState } from '../../../components/ui/ErrorState';

export const ShopCatalog: React.FC = () => {
  const { user } = useAuth();
  const { totalItems, setIsCartOpen } = useCart();
  const [searchQuery, setSearchQuery] = useState('');

  const {
    data: products = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['products'],
    queryFn: () => shopApi.getProducts(),
  });

  const isMember = user?.role === 'member' || user?.role === 'volunteer' || user?.role === 'organizer' || user?.role === 'treasurer' || user?.role === 'admin';

  // Filter products
  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      if (!p.is_active) return false;
      const matchesSearch =
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.description || '').toLowerCase().includes(searchQuery.toLowerCase());
      return matchesSearch;
    });
  }, [products, searchQuery]);

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Hero Header */}
      <div className="relative overflow-hidden bg-gradient-to-br from-primary-900 via-primary-800 to-indigo-900 py-12 px-4 sm:px-6 lg:px-8 text-white shadow-sm">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:16px_16px]" />
        
        <div className="relative mx-auto max-w-7xl flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-primary-200 backdrop-blur-md">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Official Club Store
            </span>
            <h1 className="mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl text-white">
              SSA Club Merchandise
            </h1>
            <p className="mt-2 text-base text-primary-100/90 leading-relaxed">
              Wear the colors with pride. High-quality hoodies, tees, and event memorabilia created for students, by students.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsCartOpen(true)}
              data-testid="open-cart-button"
              className="relative inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-primary-950 shadow-md hover:bg-slate-100 transition-all hover:scale-[1.02]"
            >
              <svg className="h-5 w-5 text-primary-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
              </svg>
              <span>View Cart</span>
              {totalItems > 0 && (
                <span className="ml-1 rounded-full bg-primary-600 px-2 py-0.5 text-xs font-bold text-white">
                  {totalItems}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-8">
        {/* Guest / Non-member Discount Callout Banner */}
        {!isMember && (
          <div className="mb-8 overflow-hidden rounded-2xl border border-emerald-200 bg-gradient-to-r from-emerald-50 via-teal-50 to-emerald-50/50 p-5 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start sm:items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500 text-white shadow-sm">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-emerald-950">
                    Get up to 20% off on all merchandise
                  </h3>
                  <p className="text-xs text-emerald-800">
                    SSA Members unlock discounted prices and exclusive checkout access for apparel and accessories.
                  </p>
                </div>
              </div>
              <Link
                to="/join"
                className="inline-flex shrink-0 items-center justify-center rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition-colors"
              >
                Join SSA Membership →
              </Link>
            </div>
          </div>
        )}

        {/* Filters and Search Bar */}
        <div className="mb-8 flex flex-col sm:flex-row gap-4 items-stretch sm:items-center justify-between">
          <div className="text-sm font-semibold text-slate-600">
            Showing {filteredProducts.length} {filteredProducts.length === 1 ? 'product' : 'products'}
          </div>

          {/* Search input */}
          <div className="relative min-w-[260px] sm:w-80">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search hoodie, tee..."
              className="w-full rounded-xl border border-slate-200 bg-white pl-10 pr-10 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
            <svg
              className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-slate-600"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Product Grid / States */}
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <div key={n} className="rounded-2xl border border-slate-200 bg-white p-4 space-y-4">
                <Skeleton className="aspect-square w-full rounded-xl" />
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-3 w-1/2 rounded" />
                <div className="flex justify-between pt-2">
                  <Skeleton className="h-6 w-1/3 rounded" />
                  <Skeleton className="h-6 w-1/4 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <ErrorState
            title="Failed to load products"
            message="We encountered an issue fetching the merchandise catalog. Please try again."
            onRetry={() => refetch()}
          />
        ) : filteredProducts.length === 0 ? (
          <EmptyState
            title="No merchandise found"
            description={
              searchQuery
                ? "Try adjusting your search criteria to discover available items."
                : "No products are currently available in the shop. Check back soon!"
            }
            actionLabel={searchQuery ? 'Clear Search' : undefined}
            onAction={searchQuery ? () => setSearchQuery('') : undefined}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {filteredProducts.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
