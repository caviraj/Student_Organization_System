import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import type { CartItem } from '../types';
import { useAuth } from '../../../context/AuthContext';
import { shopApi } from '../../../api/shop';

interface CartContextType {
  items: CartItem[];
  addToCart: (item: Omit<CartItem, 'quantity' | 'qty'>, quantity?: number) => void;
  updateQuantity: (variantId: string, quantity: number) => void;
  removeFromCart: (variantId: string) => void;
  clearCart: () => void;
  totalItems: number;
  itemCount: number;
  subtotalPaise: number;
  isCartOpen: boolean;
  setIsCartOpen: (open: boolean) => void;
  revalidateCart: () => Promise<{ changed: boolean; messages: string[] }>;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const storageKey = useMemo(() => `ssa_cart_${user?.id || 'guest'}`, [user?.id]);

  const [items, setItems] = useState<CartItem[]>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const [isCartOpen, setIsCartOpen] = useState(false);

  // Sync with localStorage whenever items change or user switches
  useEffect(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        setItems(JSON.parse(stored));
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      // storage unavailable
    }
  }, [items, storageKey]);

  const addToCart = useCallback(
    (itemToAdd: Omit<CartItem, 'quantity' | 'qty'>, quantity = 1) => {
      setItems((prev) => {
        const targetVariantId = itemToAdd.variantId || itemToAdd.variant_id;
        const existingIdx = prev.findIndex((i) => (i.variantId || i.variant_id) === targetVariantId);
        const maxStock = itemToAdd.maxStock ?? itemToAdd.stock ?? 999;

        if (existingIdx !== -1) {
          const existing = prev[existingIdx];
          const currentQty = existing.quantity ?? existing.qty ?? 0;
          const newQty = Math.min(currentQty + quantity, maxStock);
          const next = [...prev];
          next[existingIdx] = {
            ...existing,
            quantity: newQty,
            qty: newQty,
            maxStock,
            stock: maxStock,
          };
          return next;
        }

        const initialQty = Math.min(quantity, maxStock);
        if (initialQty <= 0) return prev;

        const completeItem: CartItem = {
          product_id: itemToAdd.product_id || itemToAdd.productId,
          productId: itemToAdd.productId || itemToAdd.product_id,
          product_name: itemToAdd.product_name || itemToAdd.productName,
          productName: itemToAdd.productName || itemToAdd.product_name,
          variant_id: itemToAdd.variant_id || itemToAdd.variantId,
          variantId: itemToAdd.variantId || itemToAdd.variant_id,
          size: itemToAdd.size,
          color: itemToAdd.color,
          unit_price: itemToAdd.unit_price ?? itemToAdd.unitPrice,
          unitPrice: itemToAdd.unitPrice ?? itemToAdd.unit_price,
          base_price: itemToAdd.base_price,
          member_discount_pct: itemToAdd.member_discount_pct,
          stock: maxStock,
          maxStock,
          image_url: itemToAdd.image_url ?? itemToAdd.imageUrl,
          imageUrl: itemToAdd.imageUrl ?? itemToAdd.image_url,
          quantity: initialQty,
          qty: initialQty,
        };

        return [...prev, completeItem];
      });
      setIsCartOpen(true);
    },
    []
  );

  const updateQuantity = useCallback((variantId: string, quantity: number) => {
    setItems((prev) => {
      if (quantity <= 0) {
        return prev.filter((i) => i.variantId !== variantId && i.variant_id !== variantId);
      }
      return prev.map((item) => {
        if (item.variantId === variantId || item.variant_id === variantId) {
          const maxStock = item.maxStock ?? item.stock ?? 999;
          const clamped = Math.min(quantity, maxStock);
          return { ...item, quantity: clamped, qty: clamped };
        }
        return item;
      });
    });
  }, []);

  const removeFromCart = useCallback((variantId: string) => {
    setItems((prev) => prev.filter((i) => i.variantId !== variantId && i.variant_id !== variantId));
  }, []);

  const clearCart = useCallback(() => {
    setItems([]);
  }, []);

  const revalidateCart = useCallback(async () => {
    try {
      const products = await shopApi.getProducts();
      let changed = false;
      const messages: string[] = [];

      setItems((prev) => {
        const next: CartItem[] = [];

        for (const item of prev) {
          const prodId = item.productId || item.product_id;
          const varId = item.variantId || item.variant_id;
          const product = products.find((p) => p.id === prodId);

          if (!product || !product.is_active) {
            changed = true;
            messages.push(`"${item.productName || item.product_name}" is no longer available.`);
            continue;
          }

          const variant = product.variants?.find((v) => v.id === varId);
          if (!variant) {
            changed = true;
            messages.push(`"${item.productName || item.product_name}" (${item.size}) is no longer available.`);
            continue;
          }

          const currentQty = item.quantity ?? item.qty ?? 1;

          if (variant.stock <= 0) {
            changed = true;
            messages.push(`"${item.productName || item.product_name}" (${item.size}) is now sold out.`);
            continue;
          } else if (currentQty > variant.stock) {
            changed = true;
            messages.push(
              `"${item.productName || item.product_name}" (${item.size}) stock reduced to ${variant.stock}. Quantity updated.`
            );
            next.push({
              ...item,
              quantity: variant.stock,
              qty: variant.stock,
              maxStock: variant.stock,
              stock: variant.stock,
            });
          } else {
            next.push({
              ...item,
              maxStock: variant.stock,
              stock: variant.stock,
            });
          }
        }

        return next;
      });

      return { changed, messages };
    } catch {
      return { changed: false, messages: [] };
    }
  }, []);

  const totalItems = useMemo(
    () => items.reduce((sum, item) => sum + (item.quantity ?? item.qty ?? 0), 0),
    [items]
  );

  const subtotalPaise = useMemo(
    () => items.reduce((sum, item) => sum + (item.unitPrice ?? item.unit_price ?? 0) * (item.quantity ?? item.qty ?? 0), 0),
    [items]
  );

  return (
    <CartContext.Provider
      value={{
        items,
        addToCart,
        updateQuantity,
        removeFromCart,
        clearCart,
        totalItems,
        itemCount: totalItems,
        subtotalPaise,
        isCartOpen,
        setIsCartOpen,
        revalidateCart,
      }}
    >
      {children}
    </CartContext.Provider>
  );
};

export const useCart = () => {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
};
