import { z } from 'zod';

export const productFormSchema = z.object({
  name: z
    .string()
    .min(2, 'Product name must be at least 2 characters')
    .max(100, 'Product name must not exceed 100 characters'),
  description: z.string().max(1000, 'Description must not exceed 1000 characters').optional().default(''),
  image_url: z
    .string()
    .url('Please provide a valid image URL (e.g. https://...)')
    .or(z.literal(''))
    .optional(),
  base_price_rupees: z
    .number()
    .min(0, 'Price cannot be negative'),
  member_discount_pct: z
    .number()
    .min(0, 'Discount cannot be negative')
    .max(100, 'Discount cannot exceed 100%'),
  is_active: z.boolean().default(true),
});

export type ProductFormValues = z.infer<typeof productFormSchema>;

export const variantFormSchema = z.object({
  size: z
    .string()
    .min(1, 'Size is required')
    .refine((val) => val.trim().length > 0, 'Size is required'),
  color: z.string().max(50, 'Color must be under 50 characters').optional().default(''),
  sku: z
    .string()
    .min(2, 'SKU must be at least 2 characters')
    .max(50, 'SKU must not exceed 50 characters')
    .regex(/^[A-Za-z0-9-_]+$/, 'SKU must contain only letters, numbers, hyphens, and underscores'),
  stock: z
    .number()
    .int('Stock must be an integer')
    .min(0, 'Stock cannot be negative'),
  low_stock_threshold: z
    .number()
    .int('Threshold must be an integer')
    .min(0, 'Threshold cannot be negative')
    .default(3),
});

export type VariantFormValues = z.infer<typeof variantFormSchema>;

export const checkoutFormSchema = z
  .object({
    fulfillment_type: z.enum(['pickup', 'delivery']),
    address: z.string().optional().default(''),
    special_instructions: z.string().max(250, 'Max 250 characters').optional().default(''),
  })
  .refine(
    (data) => {
      if (data.fulfillment_type === 'delivery') {
        return Boolean(data.address && data.address.trim().length >= 10);
      }
      return true;
    },
    {
      message: 'Please provide a full delivery address (minimum 10 characters)',
      path: ['address'],
    }
  );

export type CheckoutFormValues = z.infer<typeof checkoutFormSchema>;
