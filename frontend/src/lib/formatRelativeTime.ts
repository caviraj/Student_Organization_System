import { formatDate } from './formatDate';

/**
 * Converts an ISO date string into a friendly relative time (e.g., "Just now", "2 hours ago", "Yesterday").
 * Accepts an optional baseDate for deterministic unit testing.
 */
export function formatRelativeTime(
  dateString: string | null | undefined,
  baseDate: Date = new Date()
): string {
  if (!dateString) return '—';

  const d = new Date(dateString);
  if (isNaN(d.getTime())) return '—';

  const diffMs = baseDate.getTime() - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  // If in the future or within 45 seconds
  if (diffSec < 45) {
    return 'Just now';
  }

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) {
    return diffMin === 1 ? '1 minute ago' : `${diffMin} minutes ago`;
  }

  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) {
    return diffHours === 1 ? '1 hour ago' : `${diffHours} hours ago`;
  }

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) {
    return 'Yesterday';
  }
  if (diffDays < 7) {
    return `${diffDays} days ago`;
  }

  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 4) {
    return diffWeeks === 1 ? '1 week ago' : `${diffWeeks} weeks ago`;
  }

  return formatDate(dateString);
}
