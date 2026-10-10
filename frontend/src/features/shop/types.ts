/**
 * Strictly typed definitions for Feature 4: Merchandise.
 * Conforms to docs/DESIGN.md §3 and §5.
 * Golden Rule 1: Never rename or remove fields silently.
 * Golden Rule 3: Money is integer paise.
 */

export const CANONICAL_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'] as const;
export type CanonicalSize = (typeof CANONICAL_SIZES)[number] | string;

export interface ProductVariant {
  id: string;
  product_id: string;
  size: string;
  color?: string | null;
  sku: string;
  stock: number;
  low_stock_threshold: number;
  created_at?: string;
  updated_at?: string;
}

export interface Product {
  id: string;
  name: string;
  description?: string | null;
  image_url?: string | null;
  base_price: number; // in integer paise!
  member_discount_pct: number; // 0 to 100
  is_active: boolean;
  variants: ProductVariant[];
  created_at?: string;
  updated_at?: string;
}

export interface CartItem {
  product_id: string;
  product_name: string;
  variant_id: string;
  size: string;
  color?: string | null;
  qty: number;
  unit_price: number; // in integer paise
  base_price?: number; // in integer paise
  member_discount_pct?: number;
  image_url?: string | null;
  stock: number;
  low_stock_threshold?: number;

  // Aliases for UI components
  productId: string;
  productName: string;
  variantId: string;
  quantity: number;
  unitPrice: number;
  imageUrl?: string | null;
  maxStock: number;
}

export interface MerchCheckoutItemPayload {
  variant_id: string;
  qty: number;
}

export interface MerchCheckoutPayload {
  items: MerchCheckoutItemPayload[];
  delivery_note: string;
}

export interface MerchCheckoutResponse {
  order_id: string;
  payment_id: string;
  amount: number; // in integer paise
  provider: string;
  status: string;
  delivery_note?: string;
  merch_items?: {
    variant_id: string;
    product_name: string;
    size: string;
    color?: string | null;
    qty: number;
    unit_price: number; // in integer paise
  }[];
}

export type FulfillmentStatus = 'paid' | 'packed' | 'handed_over';

export interface MerchOrderItem {
  id?: string;
  variant_id: string;
  product_name: string;
  size: string;
  color?: string | null;
  qty: number;
  unit_price: number; // in integer paise
}

export interface MerchOrder {
  id: string;
  user_id: string;
  user_name?: string;
  user_email?: string;
  kind: 'merch';
  amount: number; // in integer paise
  status: 'pending' | 'paid' | 'failed' | 'cancelled' | 'refunded';
  fulfilment_status: FulfillmentStatus;
  delivery_note: string;
  items: MerchOrderItem[];
  created_at: string;
  updated_at?: string;
}

export interface StockSummaryVariant {
  variant_id: string;
  size: string;
  color?: string | null;
  sku: string;
  remaining: number;
  low_stock: boolean;
  demand: number;
}

export interface ProductStockSummary {
  product_id: string;
  product_name: string;
  variants: StockSummaryVariant[];
}

export interface StockSummaryResponse {
  products: ProductStockSummary[];
  total_demand_per_size: Record<string, number>;
  total_units_remaining: number;
  total_units_ordered: number;
}
