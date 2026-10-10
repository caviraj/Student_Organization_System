/**
 * Formats integer paise into Indian Rupee string (e.g. 50000 -> ₹500, 150050 -> ₹1,500.50).
 * Golden Rule 3: Money is ALWAYS integer paise. Never floats.
 */
export function formatINR(paise: number): string {
  if (typeof paise !== 'number' || isNaN(paise)) {
    return '₹0';
  }
  const rupees = paise / 100;
  const hasDecimals = paise % 100 !== 0;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: hasDecimals ? 2 : 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(rupees);
}
