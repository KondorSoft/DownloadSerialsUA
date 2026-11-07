import type { DownloadJob } from '../types';

export function formatSize(bytes: number): string {
  if (!bytes) return '—';
  const unit = bytes >= 1024 ** 3 ? 'ГБ' : 'МБ';
  return `${(bytes / (unit === 'ГБ' ? 1024 ** 3 : 1024 ** 2)).toLocaleString('uk-UA', { maximumFractionDigits: 1 })} ${unit}`;
}

export function formatFrame(width: number, height: number, fallback: string): string {
  return width && height ? `${width} × ${height}` : fallback;
}

export function updateJob(jobs: DownloadJob[], incoming: DownloadJob): DownloadJob[] {
  return [incoming, ...jobs.filter((job) => job.id !== incoming.id)].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export const statusText: Record<string, string> = {
  queued: 'У черзі',
  downloading: 'Завантажується',
  complete: 'Готово',
  partial: 'Частково готово',
  failed: 'Помилка',
  cancelled: 'Скасовано',
  interrupted: 'Перервано',
  deleted: 'Видалено',
  mixed: 'Частину файлів видалено',
};
