export interface Variant {
  label: string;
  width: number;
  height: number;
  bandwidth: number;
  duration_seconds: number;
  estimated_bytes: number;
}

export interface Episode {
  id: string;
  number: number;
  season: number | null;
  voice: string;
  source_url: string;
  variants: Variant[];
}

export interface Catalog {
  id: string;
  source_url: string;
  site: 'UAKINO' | 'UAFLIX';
  title: string;
  season: number | null;
  episodes: Episode[];
}

export interface ScanState {
  id: string;
  status: 'scanning' | 'complete' | 'failed';
  message: string;
  done: number;
  total: number;
  catalog: Catalog | null;
  error: string | null;
}

export interface EpisodeProgress {
  episode_id: string;
  number: number;
  season: number | null;
  voice: string;
  status: 'queued' | 'downloading' | 'complete' | 'failed' | 'cancelled' | 'deleted';
  percent: number;
  bytes_written: number;
  speed: string;
  output_file: string | null;
  error: string | null;
}

export interface DownloadJob {
  id: string;
  catalog_id: string;
  title: string;
  quality: string;
  resolution: string;
  output_dir: string;
  parallel_limit: number;
  status: 'queued' | 'downloading' | 'complete' | 'partial' | 'failed' | 'cancelled' | 'interrupted' | 'deleted' | 'mixed';
  episodes: EpisodeProgress[];
  estimated_bytes: number;
  created_at: string;
}
