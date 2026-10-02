/** Date rendering for review items, shared by the list and the detail screen. */

export function formatDue(iso: string): string {
  const due = new Date(iso);
  const now = new Date();
  const days = Math.round((due.getTime() - now.getTime()) / 86_400_000);
  if (days <= 0) return "今天到期";
  if (days === 1) return "明天到期";
  return `${days} 天后`;
}

export function formatDateTime(iso: string): string {
  const value = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}
