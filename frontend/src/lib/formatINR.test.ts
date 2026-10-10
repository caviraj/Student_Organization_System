import { describe, it, expect } from 'vitest';
import { formatINR } from './formatINR';

describe('formatINR', () => {
  it('formats zero paise correctly', () => {
    const formatted = formatINR(0).replace(/\u00a0/g, ' ');
    expect(formatted).toBe('₹0');
  });

  it('formats whole rupee amounts without decimal places', () => {
    const formatted = formatINR(50000).replace(/\u00a0/g, ' ');
    expect(formatted).toBe('₹500');
  });

  it('formats amounts with fractional paise correctly', () => {
    const formatted = formatINR(150050).replace(/\u00a0/g, ' ');
    expect(formatted).toBe('₹1,500.50');
  });

  it('formats small amounts less than 1 rupee correctly', () => {
    const formatted = formatINR(75).replace(/\u00a0/g, ' ');
    expect(formatted).toBe('₹0.75');
  });

  it('handles invalid input gracefully by returning ₹0', () => {
    expect(formatINR(NaN).replace(/\u00a0/g, ' ')).toBe('₹0');
    // @ts-expect-error testing invalid type
    expect(formatINR(null).replace(/\u00a0/g, ' ')).toBe('₹0');
  });
});
