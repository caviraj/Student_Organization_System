import React, { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { shopApi } from '../../../api/shop';
import { Modal } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { useToast } from '../../../components/ui/Toast';
import { rupeesToPaise, paiseToRupees } from '../../../lib/formatINR';
import type { Product } from '../types';
import { productFormSchema } from '../schemas';
import { Sparkles } from 'lucide-react';

interface ProductModalProps {
  isOpen: boolean;
  onClose: () => void;
  product?: Product | null;
}

export function ProductModal({ isOpen, onClose, product }: ProductModalProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const isEditing = Boolean(product);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [basePriceRupees, setBasePriceRupees] = useState('');
  const [memberDiscountPct, setMemberDiscountPct] = useState('15');
  const [isActive, setIsActive] = useState(true);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (product) {
      setName(product.name);
      setDescription(product.description || '');
      setImageUrl(product.image_url || '');
      setBasePriceRupees(paiseToRupees(product.base_price).toString());
      setMemberDiscountPct(product.member_discount_pct.toString());
      setIsActive(product.is_active);
    } else {
      setName('');
      setDescription('');
      setImageUrl('');
      setBasePriceRupees('499');
      setMemberDiscountPct('15');
      setIsActive(true);
    }
    setFormErrors({});
  }, [product, isOpen]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      // Validate with zod
      const parsedRupees = parseFloat(basePriceRupees);
      const parsedDiscount = parseInt(memberDiscountPct, 10);

      const validation = productFormSchema.safeParse({
        name: name.trim(),
        description: description.trim(),
        image_url: imageUrl.trim() || undefined,
        base_price_rupees: isNaN(parsedRupees) ? undefined : parsedRupees,
        member_discount_pct: isNaN(parsedDiscount) ? undefined : parsedDiscount,
        is_active: isActive,
      });

      if (!validation.success) {
        const errors: Record<string, string> = {};
        for (const issue of validation.error.issues) {
          const field = issue.path[0] as string;
          errors[field] = issue.message;
        }
        setFormErrors(errors);
        throw new Error('Please correct the errors in the form.');
      }

      setFormErrors({});
      const paise = rupeesToPaise(validation.data.base_price_rupees);

      if (isEditing && product) {
        return shopApi.updateProduct(product.id, {
          name: validation.data.name,
          description: validation.data.description || null,
          image_url: validation.data.image_url || null,
          base_price: paise,
          member_discount_pct: validation.data.member_discount_pct,
          is_active: validation.data.is_active,
        });
      } else {
        return shopApi.createProduct({
          name: validation.data.name,
          description: validation.data.description || null,
          image_url: validation.data.image_url || null,
          base_price: paise,
          member_discount_pct: validation.data.member_discount_pct,
          is_active: validation.data.is_active,
        });
      }
    },
    onSuccess: () => {
      toast.show(
        isEditing ? 'Product updated successfully!' : 'Product created successfully!',
        'success'
      );
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['adminProducts'] });
      if (product) {
        queryClient.invalidateQueries({ queryKey: ['product', product.id] });
      }
      onClose();
    },
    onError: (err: any) => {
      toast.show(err.error?.message || err.message || 'Failed to save product.', 'error');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Merchandise Product' : 'Add New Merchandise Product'}
      description={
        isEditing
          ? 'Update pricing, member discounts, and product details.'
          : 'Define base product info. You can manage sizes and stock after creation.'
      }
      maxWidth="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Name */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
            Product Name *
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Official SSA Varsity Hoodie"
            error={formErrors.name}
            autoFocus
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Material composition, wash instructions, styling tips..."
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all resize-none"
          />
          {formErrors.description && (
            <p className="text-xs text-rose-500 mt-1">{formErrors.description}</p>
          )}
        </div>

        {/* Image URL + preview */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
            Product Image URL
          </label>
          <div className="flex gap-2">
            <div className="flex-1">
              <Input
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                placeholder="https://images.unsplash.com/..."
                error={formErrors.image_url}
              />
            </div>
            {imageUrl && (
              <div className="w-10 h-10 rounded-lg overflow-hidden border border-slate-200 shrink-0 bg-slate-50 flex items-center justify-center">
                <img
                  src={imageUrl}
                  alt="Preview"
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Pricing row: Base Price in ₹ & Member Discount % */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Base Price (₹) *
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-medium text-sm">
                ₹
              </span>
              <input
                type="number"
                min="0"
                step="1"
                value={basePriceRupees}
                onChange={(e) => setBasePriceRupees(e.target.value)}
                placeholder="499"
                className="w-full rounded-xl border border-slate-200 pl-8 pr-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all"
              />
            </div>
            {formErrors.base_price_rupees && (
              <p className="text-xs text-rose-500 mt-1">{formErrors.base_price_rupees}</p>
            )}
            <p className="text-xs text-slate-400 mt-1">Stored as integer paise</p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Member Discount (%) *
            </label>
            <div className="relative">
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={memberDiscountPct}
                onChange={(e) => setMemberDiscountPct(e.target.value)}
                placeholder="15"
                className="w-full rounded-xl border border-slate-200 pl-3 pr-8 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 font-medium text-sm">
                %
              </span>
            </div>
            {formErrors.member_discount_pct && (
              <p className="text-xs text-rose-500 mt-1">{formErrors.member_discount_pct}</p>
            )}
            <p className="text-xs text-emerald-600 mt-1 flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              Active club members save {memberDiscountPct || 0}%
            </p>
          </div>
        </div>

        {/* Active Toggle */}
        <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-100">
          <div>
            <p className="text-sm font-medium text-slate-900">Active in Catalog</p>
            <p className="text-xs text-slate-500">
              When disabled, guests and members cannot see or purchase this item.
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-slate-200 peer-focus:outline-hidden rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-600"></div>
          </label>
        </div>

        {/* Modal Actions */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            isLoading={saveMutation.isPending}
            className="bg-amber-600 hover:bg-amber-700 text-white"
          >
            {isEditing ? 'Save Changes' : 'Create Product'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
