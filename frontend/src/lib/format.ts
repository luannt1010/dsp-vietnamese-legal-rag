export const formatNumber = (value: number) => new Intl.NumberFormat('vi-VN').format(value);

export function formatDuration(milliseconds: number) {
  const seconds = Math.round(milliseconds / 1000);
  return seconds < 60 ? `${seconds} giây` : `${Math.floor(seconds / 60)} phút ${seconds % 60} giây`;
}

export function safeExternalUrl(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
