import { describe, it, expect } from 'vitest';
import { sortVariantsByCanonicalSize } from './components/SizeSelector';
import { CANONICAL_SIZES, type ProductVariant } from './types';
import { productFormSchema, variantFormSchema, checkoutFormSchema } from './schemas';
import { formatINR } from '../../lib/formatINR';

describe('Shop - Canonical Size Ordering', () => {
  it('correctly defines canonical sizes in ascending order', () => {
    expect(CANONICAL_SIZES).toEqual(['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']);
  });

  it('sorts variants in canonical size order regardless of backend order', () => {
    const rawVariants: ProductVariant[] = [
      { id: '1', product_id: 'p1', size: 'XXL', sku: 'SKU-XXL', stock: 5, low_stock_threshold: 2 },
      { id: '2', product_id: 'p1', size: 'XS', sku: 'SKU-XS', stock: 10, low_stock_threshold: 2 },
      { id: '3', product_id: 'p1', size: 'L', sku: 'SKU-L', stock: 0, low_stock_threshold: 2 },
      { id: '4', product_id: 'p1', size: 'M', sku: 'SKU-M', stock: 15, low_stock_threshold: 2 },
      { id: '5', product_id: 'p1', size: 'S', sku: 'SKU-S', stock: 8, low_stock_threshold: 2 },
      { id: '6', product_id: 'p1', size: 'XL', sku: 'SKU-XL', stock: 12, low_stock_threshold: 2 },
    ];

    const sorted = sortVariantsByCanonicalSize(rawVariants);
    const sizeOrder = sorted.map((v) => v.size);
    expect(sizeOrder).toEqual(['XS', 'S', 'M', 'L', 'XL', 'XXL']);
  });

  it('handles unknown/custom sizes gracefully at the end', () => {
    const rawVariants: ProductVariant[] = [
      { id: '1', product_id: 'p1', size: 'OneSize', sku: 'SKU-OS', stock: 5, low_stock_threshold: 2 },
      { id: '2', product_id: 'p1', size: 'M', sku: 'SKU-M', stock: 10, low_stock_threshold: 2 },
      { id: '3', product_id: 'p1', size: 'FreeSize', sku: 'SKU-FS', stock: 8, low_stock_threshold: 2 },
    ];

    const sorted = sortVariantsByCanonicalSize(rawVariants);
    expect(sorted[0].size).toBe('M');
  });
});

describe('Shop - Money & Price Calculations', () => {
  it('formats merchandise prices in integer paise', () => {
    expect(formatINR(49900)).toBe('₹499');
    expect(formatINR(0)).toBe('₹0');
    expect(formatINR(125050)).toBe('₹1,250.50');
  });

  it('computes member discounted prices correctly', () => {
    const basePrice = 50000; // ₹500
    const memberDiscountPct = 15; // 15%
    const discountedPrice = Math.round(basePrice * (1 - memberDiscountPct / 100));
    expect(discountedPrice).toBe(42500); // ₹425
    expect(formatINR(discountedPrice)).toBe('₹425');
  });
});

describe('Shop - Validation Schemas', () => {
  it('validates productFormSchema correctly', () => {
    const valid = productFormSchema.safeParse({
      name: 'Club Hoodie 2026',
      description: 'Official oversized club hoodie',
      base_price_rupees: 899,
      member_discount_pct: 10,
      is_active: true,
    });
    expect(valid.success).toBe(true);

    const invalid = productFormSchema.safeParse({
      name: 'H',
      base_price_rupees: -10,
      member_discount_pct: 150,
    });
    expect(invalid.success).toBe(false);
  });

  it('validates variantFormSchema correctly with non-negative stock and threshold', () => {
    const valid = variantFormSchema.safeParse({
      size: 'XL',
      color: 'Navy Blue',
      sku: 'SSA-HOODIE-XL',
      stock: 25,
      low_stock_threshold: 5,
    });
    expect(valid.success).toBe(true);

    const negativeStock = variantFormSchema.safeParse({
      size: 'XL',
      sku: 'SSA-HOODIE-XL',
      stock: -1,
      low_stock_threshold: 5,
    });
    expect(negativeStock.success).toBe(false);
  });

  it('validates checkoutFormSchema requiring address for delivery', () => {
    const pickupValid = checkoutFormSchema.safeParse({
      fulfillment_type: 'pickup',
      special_instructions: 'Will collect during lunch',
    });
    expect(pickupValid.success).toBe(true);

    const deliveryMissingAddress = checkoutFormSchema.safeParse({
      fulfillment_type: 'delivery',
      address: '',
    });
    expect(deliveryMissingAddress.success).toBe(false);

    const deliveryValid = checkoutFormSchema.safeParse({
      fulfillment_type: 'delivery',
      address: 'Hostel 4, Room 204, Campus Road',
    });
    expect(deliveryValid.success).toBe(true);
  });
});
