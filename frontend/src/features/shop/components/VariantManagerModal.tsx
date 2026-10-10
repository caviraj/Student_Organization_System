import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { shopApi } from '../../../api/shop';
import { Modal } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { useToast } from '../../../components/ui/Toast';
import type { Product, ProductVariant } from '../types';
import { CANONICAL_SIZES } from '../types';
import { variantFormSchema } from '../schemas';
import {
  Package,
  Plus,
  Save,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

interface VariantManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  product: Product | null;
}

export function VariantManagerModal({
  isOpen,
  onClose,
  product,
}: VariantManagerModalProps) {
  const queryClient = useQueryClient();
  const toast = useToast();

  // Local state for adding a new variant
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSize, setNewSize] = useState('M');
  const [newColor, setNewColor] = useState('');
  const [newSku, setNewSku] = useState('');
  const [newStock, setNewStock] = useState('10');
  const [newThreshold, setNewThreshold] = useState('3');
  const [addErrors, setAddErrors] = useState<Record<string, string>>({});

  // Local state for editing existing variant stocks
  const [editingStock, setEditingStock] = useState<Record<string, { stock: string; threshold: string }>>({});

  // Canonical sorting of variants
  const sortedVariants = product
    ? [...(product.variants || [])].sort((a, b) => {
        const idxA = CANONICAL_SIZES.indexOf(a.size as any);
        const idxB = CANONICAL_SIZES.indexOf(b.size as any);
        if (idxA !== -1 && idxB !== -1) return idxA - idxB;
        if (idxA !== -1) return -1;
        if (idxB !== -1) return 1;
        return a.size.localeCompare(b.size);
      })
    : [];

  const getStockValues = (variant: ProductVariant) => {
    const current = editingStock[variant.id];
    if (current) return current;
    return {
      stock: variant.stock.toString(),
      threshold: variant.low_stock_threshold.toString(),
    };
  };

  const handleStockChange = (variantId: string, field: 'stock' | 'threshold', val: string) => {
    setEditingStock((prev) => {
      const existing = prev[variantId] || {
        stock: product?.variants?.find((v) => v.id === variantId)?.stock.toString() || '0',
        threshold: product?.variants?.find((v) => v.id === variantId)?.low_stock_threshold.toString() || '3',
      };
      return {
        ...prev,
        [variantId]: {
          ...existing,
          [field]: val,
        },
      };
    });
  };

  const updateVariantMutation = useMutation({
    mutationFn: async ({
      variantId,
      stock,
      threshold,
    }: {
      variantId: string;
      stock: number;
      threshold: number;
    }) => {
      if (!product) throw new Error('Product not selected');
      return shopApi.updateVariant(product.id, variantId, {
        stock,
        low_stock_threshold: threshold,
      });
    },
    onSuccess: (_, variables) => {
      toast.show('Variant stock updated!', 'success');
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['adminProducts'] });
      if (product) {
        queryClient.invalidateQueries({ queryKey: ['product', product.id] });
      }
      queryClient.invalidateQueries({ queryKey: ['adminStockSummary'] });

      // Clean up edited state for this variant
      setEditingStock((prev) => {
        const copy = { ...prev };
        delete copy[variables.variantId];
        return copy;
      });
    },
    onError: (err: any) => {
      toast.show(err.error?.message || err.message || 'Failed to update stock.', 'error');
    },
  });

  const handleSaveVariant = (variant: ProductVariant) => {
    const vals = getStockValues(variant);
    const parsedStock = parseInt(vals.stock, 10);
    const parsedThreshold = parseInt(vals.threshold, 10);

    if (isNaN(parsedStock) || parsedStock < 0) {
      toast.show('Stock must be a non-negative integer.', 'error');
      return;
    }
    if (isNaN(parsedThreshold) || parsedThreshold < 0) {
      toast.show('Low stock threshold must be a non-negative integer.', 'error');
      return;
    }

    updateVariantMutation.mutate({
      variantId: variant.id,
      stock: parsedStock,
      threshold: parsedThreshold,
    });
  };

  const createVariantMutation = useMutation({
    mutationFn: async () => {
      if (!product) throw new Error('Product not selected');
      const parsedStock = parseInt(newStock, 10);
      const parsedThreshold = parseInt(newThreshold, 10);

      const validation = variantFormSchema.safeParse({
        size: newSize.trim(),
        color: newColor.trim() || undefined,
        sku: newSku.trim(),
        stock: isNaN(parsedStock) ? undefined : parsedStock,
        low_stock_threshold: isNaN(parsedThreshold) ? undefined : parsedThreshold,
      });

      if (!validation.success) {
        const errors: Record<string, string> = {};
        for (const issue of validation.error.issues) {
          const field = issue.path[0] as string;
          errors[field] = issue.message;
        }
        setAddErrors(errors);
        throw new Error('Please fix the errors.');
      }

      setAddErrors({});
      return shopApi.createVariant(product.id, {
        size: validation.data.size,
        color: validation.data.color || null,
        sku: validation.data.sku,
        stock: validation.data.stock,
        low_stock_threshold: validation.data.low_stock_threshold,
      });
    },
    onSuccess: () => {
      toast.show('New size variant added!', 'success');
      setShowAddForm(false);
      setNewSku('');
      setNewColor('');
      setNewStock('10');
      setNewThreshold('3');
      setAddErrors({});
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['adminProducts'] });
      if (product) {
        queryClient.invalidateQueries({ queryKey: ['product', product.id] });
      }
      queryClient.invalidateQueries({ queryKey: ['adminStockSummary'] });
    },
    onError: (err: any) => {
      toast.show(err.error?.message || err.message || 'Failed to add variant.', 'error');
    },
  });

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createVariantMutation.mutate();
  };

  const autoGenerateSku = (size: string) => {
    const slug = (product?.name || '')
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '')
      .slice(0, 4);
    return `${slug}-${size}`;
  };

  if (!product) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Manage Sizes & Stock: ${product.name}`}
      description="Monitor real-time inventory levels, adjust stock counts, and add new size variants."
      maxWidth="xl"
    >
      <div className="space-y-6">
        {/* Existing Variants Table */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <Package className="w-3.5 h-3.5 text-amber-600" />
              Active Variants ({sortedVariants.length})
            </h4>
            {!showAddForm && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setNewSku(autoGenerateSku(newSize));
                  setShowAddForm(true);
                }}
                className="text-xs h-8 text-amber-700 border-amber-200 hover:bg-amber-50"
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                Add Size Variant
              </Button>
            )}
          </div>

          {sortedVariants.length === 0 ? (
            <div className="p-8 text-center bg-slate-50 rounded-xl border border-dashed border-slate-200">
              <Package className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-700">No variants created yet</p>
              <p className="text-xs text-slate-500 mt-1">
                Add size variants like S, M, L to make this product purchasable in the shop.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600">
                    <th className="py-2.5 px-3">Size</th>
                    <th className="py-2.5 px-3">SKU</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3 w-28">Stock</th>
                    <th className="py-2.5 px-3 w-28">Alert Below</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sortedVariants.map((variant) => {
                    const vals = getStockValues(variant);
                    const isDirty =
                      vals.stock !== variant.stock.toString() ||
                      vals.threshold !== variant.low_stock_threshold.toString();

                    const isSoldOut = variant.stock === 0;
                    const isLowStock =
                      variant.stock > 0 && variant.stock <= variant.low_stock_threshold;

                    return (
                      <tr key={variant.id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="py-2.5 px-3 font-semibold text-slate-900">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 text-xs font-bold">
                            {variant.size}
                          </span>
                          {variant.color && (
                            <span className="text-xs text-slate-500 ml-1.5">
                              ({variant.color})
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-xs text-slate-600">
                          {variant.sku}
                        </td>
                        <td className="py-2.5 px-3">
                          {isSoldOut ? (
                            <span className="inline-flex items-center gap-1 text-xs font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md">
                              <XCircle className="w-3 h-3" />
                              Sold out
                            </span>
                          ) : isLowStock ? (
                            <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md">
                              <AlertTriangle className="w-3 h-3" />
                              Low ({variant.stock})
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md">
                              <CheckCircle2 className="w-3 h-3" />
                              In stock
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3">
                          <input
                            type="number"
                            min="0"
                            value={vals.stock}
                            onChange={(e) => handleStockChange(variant.id, 'stock', e.target.value)}
                            className="w-20 rounded-lg border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-900 focus:outline-hidden focus:ring-1 focus:ring-amber-500"
                          />
                        </td>
                        <td className="py-2.5 px-3">
                          <input
                            type="number"
                            min="0"
                            value={vals.threshold}
                            onChange={(e) => handleStockChange(variant.id, 'threshold', e.target.value)}
                            className="w-20 rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 focus:outline-hidden focus:ring-1 focus:ring-amber-500"
                          />
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <Button
                            size="sm"
                            disabled={!isDirty || updateVariantMutation.isPending}
                            onClick={() => handleSaveVariant(variant)}
                            className={`text-xs h-7 px-2.5 ${
                              isDirty
                                ? 'bg-amber-600 hover:bg-amber-700 text-white'
                                : 'opacity-40 pointer-events-none'
                            }`}
                          >
                            <Save className="w-3 h-3 mr-1" />
                            Update
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Add Variant Sub-Form */}
        {showAddForm && (
          <form
            onSubmit={handleAddSubmit}
            className="p-4 rounded-xl bg-amber-50/60 border border-amber-200 space-y-3 animate-in fade-in"
          >
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wider flex items-center gap-1.5">
                <Plus className="w-3.5 h-3.5" />
                Add New Size Variant
              </h4>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="text-xs text-amber-700 hover:underline"
              >
                Cancel
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Size */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Size *
                </label>
                <select
                  value={newSize}
                  onChange={(e) => {
                    setNewSize(e.target.value);
                    setNewSku(autoGenerateSku(e.target.value));
                  }}
                  className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                >
                  {CANONICAL_SIZES.map((sz) => (
                    <option key={sz} value={sz}>
                      {sz}
                    </option>
                  ))}
                  <option value="One Size">One Size</option>
                  <option value="Free">Free Size</option>
                </select>
                {addErrors.size && (
                  <p className="text-xs text-rose-500 mt-0.5">{addErrors.size}</p>
                )}
              </div>

              {/* SKU */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  SKU *
                </label>
                <input
                  type="text"
                  value={newSku}
                  onChange={(e) => setNewSku(e.target.value.toUpperCase())}
                  placeholder="HOOD-M"
                  className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-amber-500 font-mono"
                />
                {addErrors.sku && (
                  <p className="text-xs text-rose-500 mt-0.5">{addErrors.sku}</p>
                )}
              </div>

              {/* Stock */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Initial Stock *
                </label>
                <input
                  type="number"
                  min="0"
                  value={newStock}
                  onChange={(e) => setNewStock(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                />
                {addErrors.stock && (
                  <p className="text-xs text-rose-500 mt-0.5">{addErrors.stock}</p>
                )}
              </div>

              {/* Threshold */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Low Stock Alert
                </label>
                <input
                  type="number"
                  min="0"
                  value={newThreshold}
                  onChange={(e) => setNewThreshold(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                />
                {addErrors.low_stock_threshold && (
                  <p className="text-xs text-rose-500 mt-0.5">
                    {addErrors.low_stock_threshold}
                  </p>
                )}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                type="submit"
                size="sm"
                isLoading={createVariantMutation.isPending}
                className="bg-amber-600 hover:bg-amber-700 text-white text-xs h-8 px-4"
              >
                Save Variant
              </Button>
            </div>
          </form>
        )}

        {/* Footer */}
        <div className="flex justify-end pt-3 border-t border-slate-100">
          <Button variant="outline" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </Modal>
  );
}
