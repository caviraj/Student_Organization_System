import { apiClient } from './client';
import type {
  Product,
  ProductVariant,
  MerchCheckoutPayload,
  MerchCheckoutResponse,
  MerchOrder,
  FulfillmentStatus,
  StockSummaryResponse,
} from '../features/shop/types';
import type { PaginatedResponse } from '../types/api';

export const shopApi = {
  // Public product catalog
  getProducts: async (params?: { include_inactive?: boolean }) => {
    // /products answers with a page envelope, not a bare array. 100 is the API's max page_size.
    // shortcut: a catalog past 100 items needs real pagination, which the grid has no UI for yet.
    const page = await apiClient<PaginatedResponse<Product>>('/products', {
      params: {
        include_inactive: params?.include_inactive,
        page_size: 100,
      },
    });
    return page.items;
  },

  getProduct: (id: string) => {
    return apiClient<Product>(`/products/${id}`);
  },

  // Admin product management
  createProduct: (payload: {
    name: string;
    description?: string | null;
    image_url?: string | null;
    base_price: number;
    member_discount_pct: number;
    is_active?: boolean;
  }) => {
    return apiClient<Product>('/products', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  updateProduct: (
    id: string,
    payload: Partial<{
      name: string;
      description?: string | null;
      image_url?: string | null;
      base_price: number;
      member_discount_pct: number;
      is_active: boolean;
    }>
  ) => {
    return apiClient<Product>(`/products/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  // Admin variant management
  createVariant: (
    productId: string,
    payload: {
      size: string;
      color?: string | null;
      sku: string;
      stock: number;
      low_stock_threshold: number;
    }
  ) => {
    return apiClient<ProductVariant>(`/products/${productId}/variants`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Contract: PATCH /variants/{variant_id} takes size/color/sku/low_stock_threshold/is_active.
  // It has no stock field - stock only moves through stock-adjust.
  updateVariant: (
    variantId: string,
    payload: Partial<{
      size: string;
      color?: string | null;
      sku: string;
      low_stock_threshold: number;
      is_active: boolean;
    }>
  ) => {
    return apiClient<ProductVariant>(`/variants/${variantId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  adjustVariantStock: (
    variantId: string,
    payload: { delta: number; reason: 'restock' | 'adjustment'; note?: string | null }
  ) => {
    return apiClient<ProductVariant>(`/variants/${variantId}/stock-adjust`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Member checkout
  checkoutMerch: (payload: MerchCheckoutPayload) => {
    return apiClient<MerchCheckoutResponse>('/orders/merch/checkout', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // User orders
  getMyOrders: async (params?: { kind?: string }) => {
    // /orders/me answers with a page envelope, not a bare array. 100 is the API's max page_size.
    // shortcut: orders past the first 100 need real pagination, which no screen asks for yet.
    const page = await apiClient<PaginatedResponse<MerchOrder>>('/orders/me', {
      params: {
        kind: params?.kind,
        page_size: 100,
      },
    });
    return page.items;
  },

  // Admin merch order board
  getAdminMerchOrders: (params?: {
    fulfilment_status?: FulfillmentStatus;
    page?: number;
    page_size?: number;
  }) => {
    return apiClient<PaginatedResponse<MerchOrder>>('/admin/merch/orders', {
      params: {
        fulfilment_status: params?.fulfilment_status,
        page: params?.page,
        page_size: params?.page_size,
      },
    });
  },

  updateFulfillmentStatus: (orderId: string, status: FulfillmentStatus) => {
    return apiClient<MerchOrder>(`/admin/merch/orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ fulfilment_status: status }),
    });
  },

  // Admin stock summary
  getStockSummary: () => {
    return apiClient<StockSummaryResponse>('/admin/merch/stock-summary');
  },
};
