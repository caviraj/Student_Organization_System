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

/**
 * Converts whole or decimal rupees entered by admin users into integer paise.
 * E.g., 500 -> 50000, 1500.50 -> 150050.
 */
export function rupeesToPaise(rupees: number | string): number {
  const num = typeof rupees === 'string' ? parseFloat(rupees) : rupees;
  if (isNaN(num) || num < 0) return 0;
  return Math.round(num * 100);
}

/**
 * Converts integer paise into rupees for display or form pre-filling.
 */
export function paiseToRupees(paise: number): number {
  if (isNaN(paise) || paise < 0) return 0;
  return paise / 100;
}
