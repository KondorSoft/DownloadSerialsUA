import type { DownloadJob, ScanState } from './types';

const url = new URL(window.location.href);
const incomingToken = url.searchParams.get('token');
if (incomingToken) {
  sessionStorage.setItem('kadr-token', incomingToken);
  url.searchParams.delete('token');
  window.history.replaceState({}, '', url.toString());
}

export const token = sessionStorage.getItem('kadr-token') || '';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-App-Token': token, ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Помилка запиту (${response.status})`);
  }
  return response.json();
}

export const api = {
  scan: (url: string) => request<ScanState>('/api/scans', { method: 'POST', body: JSON.stringify({ url }) }),
  getScan: (id: string) => request<ScanState>(`/api/scans/${id}`),
  jobs: () => request<DownloadJob[]>('/api/jobs'),
  start: (body: { catalog_id: string; episode_ids: string[]; quality: string; output_dir: string; parallel_limit: number }) =>
    request<DownloadJob>('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
  cancel: (id: string) => request<DownloadJob>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  retry: (id: string) => request<DownloadJob>(`/api/jobs/${id}/retry`, { method: 'POST' }),
  deleteFile: (id: string, episodeId: string) => request<DownloadJob>(`/api/jobs/${id}/delete-file`, { method: 'POST', body: JSON.stringify({ episode_id: episodeId }) }),
  getFolder: () => request<{ path: string }>('/api/folder'),
  saveFolder: (path: string) => request<{ path: string }>('/api/folder', { method: 'PUT', body: JSON.stringify({ path }) }),
  chooseFolder: (path: string) => request<{ path: string }>('/api/folder/select', { method: 'POST', body: JSON.stringify({ path }) }),
};

export function connectEvents(onEvent: (event: { type: 'scan' | 'job'; scan?: ScanState; job?: DownloadJob }) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${window.location.host}/api/events?token=${encodeURIComponent(token)}`);
  socket.onmessage = (message) => onEvent(JSON.parse(message.data));
  return socket;
}
