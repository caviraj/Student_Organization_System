import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminPortalApi, type CompanyProduct } from '../../api/adminPortal';
import { useCart } from '../../features/shop/context/CartContext';
import { useToast } from '../ui/Toast';
import {
  ShoppingBag,
  Building2,
  Info,
  Package,
} from 'lucide-react';
import { Button } from '../ui/Button';

export function CompanyProductsSection() {
  const { addToCart, setIsCartOpen } = useCart();
  const { success: showToastSuccess } = useToast();
  const [buyingId, setBuyingId] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['studentCompanyProducts'],
    queryFn: adminPortalApi.getCompanyProducts,
    staleTime: 1000 * 60 * 3, // 3 minutes
  });

  const products = data?.products || [];

  const handleBuy = (product: CompanyProduct) => {
    setBuyingId(product.id);
    const variantId = product.variant_id || product.id;
    addToCart(
      {
        product_id: product.id,
        productId: product.id,
        product_name: product.name,
        productName: product.name,
        variant_id: variantId,
        variantId: variantId,
        size: 'Standard',
        unit_price: product.base_price_paise,
        unitPrice: product.base_price_paise,
        base_price: product.base_price_paise,
        stock: product.stock,
        maxStock: product.stock,
        image_url: product.image_url || undefined,
        imageUrl: product.image_url || undefined,
      },
      1
    );

    showToastSuccess(`Added "${product.name}" to your cart. Complete checkout when you wish.`);
    setIsCartOpen(true);
    setTimeout(() => setBuyingId(null), 500);
  };

  return (
    <div className="w-full mt-10 pt-8 border-t border-slate-200">
      {/* Header with Title and Optional Disclaimer */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 mb-2">
            <Building2 className="w-3.5 h-3.5" />
            Company Products for Student Needs
          </div>
          <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            Recommended Products
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
              Optional
            </span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Curated educational equipment, kits, and tools added by the administration.
          </p>
        </div>

        {/* Clear Notice: Not Compulsory to Buy */}
        <div className="max-w-md bg-amber-50/80 border border-amber-200 rounded-2xl p-3 flex items-start gap-2.5 text-xs text-amber-900 shadow-xs">
          <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <p className="font-semibold text-amber-950">
              Notice: Buying is NOT Compulsory
            </p>
            <p className="text-[11px] text-amber-800 leading-relaxed">
              These company products are strictly optional. If you need them for your coursework or projects, you can purchase them. Otherwise, you do not need to buy anything.
            </p>
          </div>
        </div>
      </div>

      {/* Content State */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-64 rounded-3xl bg-slate-100 animate-pulse border border-slate-200" />
          ))}
        </div>
      ) : error ? (
        <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 text-center text-xs text-slate-500">
          Unable to load company products right now.
        </div>
      ) : products.length === 0 ? (
        <div className="p-8 rounded-3xl bg-white border border-dashed border-slate-200 text-center space-y-2">
          <Package className="w-10 h-10 text-slate-300 mx-auto" />
          <p className="text-sm font-semibold text-slate-700">No Company Products Listed</p>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            The administration has not added any specific company products at the moment.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {products.map((p) => {
            const hasStock = p.stock > 0;
            return (
              <div
                key={p.id}
                className="group bg-white rounded-3xl border border-slate-200/90 hover:border-slate-300 shadow-sm hover:shadow-md transition-all overflow-hidden flex flex-col justify-between"
              >
                <div>
                  {/* Image banner */}
                  <div className="relative h-44 w-full bg-slate-100 overflow-hidden flex items-center justify-center">
                    {p.image_url ? (
                      <img
                        src={p.image_url}
                        alt={p.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src =
                            'https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=600&q=80';
                        }}
                      />
                    ) : (
                      <div className="flex flex-col items-center justify-center text-slate-400 gap-1">
                        <Package className="w-12 h-12 text-slate-300" />
                        <span className="text-[11px] font-medium">Student Equipment</span>
                      </div>
                    )}

                    <div className="absolute top-3 left-3">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/90 backdrop-blur-md text-slate-800 shadow-xs border border-slate-200">
                        Optional
                      </span>
                    </div>

                    <div className="absolute top-3 right-3">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full border shadow-xs ${
                          hasStock
                            ? 'bg-emerald-500/90 text-white border-emerald-400'
                            : 'bg-rose-500/90 text-white border-rose-400'
                        }`}
                      >
                        {hasStock ? `${p.stock} in stock` : 'Out of stock'}
                      </span>
                    </div>
                  </div>

                  {/* Body Content */}
                  <div className="p-5">
                    <h3 className="font-bold text-slate-900 text-base leading-snug line-clamp-1 group-hover:text-indigo-600 transition-colors">
                      {p.name}
                    </h3>
                    <p className="text-xs text-slate-500 mt-1.5 line-clamp-2 leading-relaxed">
                      {p.description || 'Verified product for college coursework, lab kits, or project tools.'}
                    </p>

                    <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                      <div>
                        <span className="text-[11px] text-slate-400 font-medium block">Student Price</span>
                        <span className="text-lg font-black text-slate-900">
                          ₹{p.price_inr.toLocaleString('en-IN')}
                        </span>
                      </div>

                      <div className="text-right">
                        <span className="text-[10px] text-emerald-600 font-semibold block">Verified by Admin</span>
                        <span className="text-[10px] text-slate-400">Not compulsory</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Footer Action */}
                <div className="p-5 pt-0">
                  <Button
                    variant={hasStock ? 'primary' : 'outline'}
                    size="sm"
                    className="w-full justify-center"
                    disabled={!hasStock || buyingId === p.id}
                    onClick={() => handleBuy(p)}
                  >
                    <ShoppingBag className="w-3.5 h-3.5 mr-1.5" />
                    {hasStock ? 'Buy if Needed' : 'Currently Unavailable'}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
