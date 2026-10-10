import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { shopApi } from '../../../api/shop';
import { Card } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { SkeletonCard } from '../../../components/ui/Skeleton';
import { ErrorState } from '../../../components/ui/ErrorState';
import { EmptyState } from '../../../components/ui/EmptyState';
import { useToast } from '../../../components/ui/Toast';
import { formatINR } from '../../../lib/formatINR';
import type { Product } from '../types';
import { CANONICAL_SIZES } from '../types';
import { ProductModal } from '../components/ProductModal';
import { VariantManagerModal } from '../components/VariantManagerModal';
import {
  ShoppingBag,
  Plus,
  Edit2,
  Package,
  Search,
  AlertTriangle,
  XCircle,
  Eye,
  EyeOff,
} from 'lucide-react';

export function AdminProducts() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [searchTerm, setSearchTerm] = useState('');
  const [includeInactive, setIncludeInactive] = useState(true);

  // Modal states
  const [productModalOpen, setProductModalOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  const [variantModalOpen, setVariantModalOpen] = useState(false);
  const [variantProduct, setVariantProduct] = useState<Product | null>(null);

  const {
    data: products,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['adminProducts', includeInactive],
    queryFn: () => shopApi.getProducts({ include_inactive: includeInactive }),
  });

  // Toggle active status mutation
  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      shopApi.updateProduct(id, { is_active }),
    onSuccess: (_, variables) => {
      toast.show(
        `Product marked as ${variables.is_active ? 'active' : 'inactive'}.`,
        'success'
      );
      queryClient.invalidateQueries({ queryKey: ['adminProducts'] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
    onError: (err: any) => {
      toast.show(err.error?.message || err.message || 'Failed to update product status.', 'error');
    },
  });

  // Computed metrics
  const allProducts = products || [];
  const filteredProducts = allProducts.filter((p) => {
    const term = searchTerm.toLowerCase();
    return (
      p.name.toLowerCase().includes(term) ||
      (p.description && p.description.toLowerCase().includes(term))
    );
  });

  const totalVariants = allProducts.reduce(
    (acc, p) => acc + (p.variants?.length || 0),
    0
  );
  const totalStockUnits = allProducts.reduce(
    (acc, p) =>
      acc + (p.variants?.reduce((sum, v) => sum + v.stock, 0) || 0),
    0
  );
  const lowStockCount = allProducts.reduce((acc, p) => {
    return (
      acc +
      (p.variants?.filter((v) => v.stock > 0 && v.stock <= v.low_stock_threshold)
        .length || 0)
    );
  }, 0);
  const soldOutCount = allProducts.reduce((acc, p) => {
    return acc + (p.variants?.filter((v) => v.stock === 0).length || 0);
  }, 0);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2.5">
            <ShoppingBag className="w-6 h-6 text-amber-600" />
            Merchandise Catalog & Inventory
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage club merchandise, size variants, stock thresholds, and member pricing.
          </p>
        </div>
        <Button
          onClick={() => {
            setSelectedProduct(null);
            setProductModalOpen(true);
          }}
          className="bg-amber-600 hover:bg-amber-700 text-white shrink-0"
        >
          <Plus className="w-4 h-4 mr-1.5" />
          Add Product
        </Button>
      </div>

      {/* Metrics Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Total Products
          </p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{allProducts.length}</p>
        </div>
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Total SKUs / Variants
          </p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{totalVariants}</p>
        </div>
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Units in Stock
          </p>
          <p className="text-2xl font-bold text-slate-900 mt-1 text-emerald-600">
            {totalStockUnits}
          </p>
        </div>
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Stock Alerts
          </p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-2xl font-bold text-amber-600">{lowStockCount} low</span>
            <span className="text-xs text-slate-400">/</span>
            <span className="text-sm font-semibold text-rose-600">{soldOutCount} out</span>
          </div>
        </div>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3.5 rounded-xl border border-slate-200">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search merchandise by title..."
            className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-hidden focus:ring-2 focus:ring-amber-500"
          />
        </div>

        <label className="flex items-center gap-2 text-xs font-medium text-slate-600 cursor-pointer select-none self-start sm:self-auto">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            className="rounded-sm border-slate-300 text-amber-600 focus:ring-amber-500 w-4 h-4"
          />
          Show inactive / archived items
        </label>
      </div>

      {/* Product List */}
      {isLoading ? (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Could not load merchandise"
          message={(error as Error).message}
          onRetry={() => refetch()}
        />
      ) : filteredProducts.length === 0 ? (
        <EmptyState
          title="No merchandise products found"
          description={
            searchTerm
              ? `No products matched "${searchTerm}".`
              : 'Add your first hoodie or tee to begin selling club merchandise.'
          }
          actionLabel="Add First Product"
          onAction={() => {
            setSelectedProduct(null);
            setProductModalOpen(true);
          }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredProducts.map((product) => {
            const memberPrice = Math.round(
              product.base_price * (1 - product.member_discount_pct / 100)
            );
            const variants = product.variants || [];
            const sortedVariants = [...variants].sort((a, b) => {
              const idxA = CANONICAL_SIZES.indexOf(a.size as any);
              const idxB = CANONICAL_SIZES.indexOf(b.size as any);
              if (idxA !== -1 && idxB !== -1) return idxA - idxB;
              if (idxA !== -1) return -1;
              if (idxB !== -1) return 1;
              return a.size.localeCompare(b.size);
            });

            const totalProductStock = variants.reduce((sum, v) => sum + v.stock, 0);
            const hasLowStock = variants.some(
              (v) => v.stock > 0 && v.stock <= v.low_stock_threshold
            );
            const hasSoldOut = variants.some((v) => v.stock === 0);

            return (
              <Card
                key={product.id}
                className={`overflow-hidden transition-all border ${
                  product.is_active ? 'border-slate-200' : 'border-slate-200/60 opacity-75 bg-slate-50/40'
                }`}
              >
                <div className="p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                  {/* Left: Thumbnail & Info */}
                  <div className="flex items-start gap-4 flex-1">
                    <div className="w-16 h-16 rounded-xl overflow-hidden bg-slate-100 border border-slate-200 shrink-0 flex items-center justify-center">
                      {product.image_url ? (
                        <img
                          src={product.image_url}
                          alt={product.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <ShoppingBag className="w-7 h-7 text-slate-300" />
                      )}
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-bold text-slate-900 text-base">
                          {product.name}
                        </h3>
                        {product.is_active ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                            Inactive
                          </span>
                        )}
                        {hasLowStock && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            Low Stock
                          </span>
                        )}
                        {hasSoldOut && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-bold bg-rose-50 text-rose-700 border border-rose-200">
                            <XCircle className="w-2.5 h-2.5" />
                            Some Out
                          </span>
                        )}
                      </div>

                      {product.description && (
                        <p className="text-xs text-slate-500 line-clamp-1 max-w-xl">
                          {product.description}
                        </p>
                      )}

                      {/* Pricing Info */}
                      <div className="flex items-center gap-3 pt-1 text-xs">
                        <div>
                          <span className="text-slate-400">Regular: </span>
                          <span className="font-semibold text-slate-800">
                            {formatINR(product.base_price)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400">Member: </span>
                          <span className="font-bold text-emerald-700">
                            {formatINR(memberPrice)}
                          </span>
                          <span className="text-2xs font-bold bg-emerald-100 text-emerald-800 px-1.5 py-0.2 rounded-sm">
                            -{product.member_discount_pct}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Middle: Variant Stock Badges */}
                  <div className="flex flex-col sm:items-end w-full md:w-auto">
                    <p className="text-2xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                      Sizes & Stock ({totalProductStock} total units)
                    </p>
                    {sortedVariants.length === 0 ? (
                      <span className="text-xs text-amber-600 font-medium bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200">
                        No sizes added yet
                      </span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5 max-w-xs md:justify-end">
                        {sortedVariants.map((v) => {
                          const isZero = v.stock === 0;
                          const isLow = v.stock > 0 && v.stock <= v.low_stock_threshold;
                          return (
                            <span
                              key={v.id}
                              title={`SKU: ${v.sku} - Stock: ${v.stock}`}
                              className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold border ${
                                isZero
                                  ? 'bg-rose-50 text-rose-600 border-rose-200 line-through opacity-75'
                                  : isLow
                                  ? 'bg-amber-50 text-amber-800 border-amber-200'
                                  : 'bg-slate-50 text-slate-700 border-slate-200'
                              }`}
                            >
                              <span>{v.size}</span>
                              <span
                                className={`text-2xs font-bold ${
                                  isZero
                                    ? 'text-rose-500'
                                    : isLow
                                    ? 'text-amber-600'
                                    : 'text-slate-400'
                                }`}
                              >
                                {v.stock}
                              </span>
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Right: Actions */}
                  <div className="flex items-center gap-2 pt-2 md:pt-0 border-t md:border-t-0 border-slate-100 w-full md:w-auto justify-end">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setVariantProduct(product);
                        setVariantModalOpen(true);
                      }}
                      className="text-xs h-8 text-amber-700 border-amber-200 hover:bg-amber-50"
                    >
                      <Package className="w-3.5 h-3.5 mr-1" />
                      Manage Sizes
                    </Button>

                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setSelectedProduct(product);
                        setProductModalOpen(true);
                      }}
                      className="text-xs h-8"
                    >
                      <Edit2 className="w-3.5 h-3.5 mr-1" />
                      Edit
                    </Button>

                    <button
                      onClick={() =>
                        toggleActiveMutation.mutate({
                          id: product.id,
                          is_active: !product.is_active,
                        })
                      }
                      title={product.is_active ? 'Deactivate product' : 'Activate product'}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                    >
                      {product.is_active ? (
                        <Eye className="w-4 h-4" />
                      ) : (
                        <EyeOff className="w-4 h-4 text-slate-300" />
                      )}
                    </button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Product Edit / Create Modal */}
      <ProductModal
        isOpen={productModalOpen}
        onClose={() => {
          setProductModalOpen(false);
          setSelectedProduct(null);
        }}
        product={selectedProduct}
      />

      {/* Variant & Stock Manager Modal */}
      <VariantManagerModal
        isOpen={variantModalOpen}
        onClose={() => {
          setVariantModalOpen(false);
          setVariantProduct(null);
        }}
        product={variantProduct}
      />
    </div>
  );
}
