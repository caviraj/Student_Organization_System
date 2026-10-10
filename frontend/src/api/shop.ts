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
  getProducts: (params?: { include_inactive?: boolean }) => {
    return apiClient<Product[]>('/products', {
      params: {
        include_inactive: params?.include_inactive,
      },
    });
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

  updateVariant: (
    productId: string,
    variantId: string,
    payload: Partial<{
      size: string;
      color?: string | null;
      sku: string;
      stock: number;
      low_stock_threshold: number;
    }>
  ) => {
    return apiClient<ProductVariant>(`/products/${productId}/variants/${variantId}`, {
      method: 'PATCH',
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
  getMyOrders: (params?: { kind?: string }) => {
    return apiClient<MerchOrder[]>('/orders/me', {
      params: {
        kind: params?.kind,
      },
    });
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
