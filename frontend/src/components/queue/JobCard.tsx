import { RotateCcw, Square } from 'lucide-react';
import type { DownloadJob } from '../../types';
import { statusText } from '../../utils/format';
import { JobEpisodeRow } from './JobEpisodeRow';

interface JobCardProps {
  job: DownloadJob;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  onDeleteFile: (job: DownloadJob, episodeId: string) => void;
}

export function JobCard({ job, onCancel, onRetry, onDeleteFile }: JobCardProps) {
  const complete = job.episodes.filter((episode) => episode.status === 'complete').length;
  const progress = Math.round(
    job.episodes.reduce((sum, episode) => sum + episode.percent, 0) / job.episodes.length
  );
  const filmJob = job.episodes.length === 1 && job.episodes[0].season === null;
  const canDelete = !['queued', 'downloading'].includes(job.status);
  const canRetry = job.episodes.some((episode) => ['failed', 'cancelled'].includes(episode.status));

  return (
    <article className="job-card">
      <div className="job-top">
        <div>
          <strong>{job.title}</strong>
          <span>
            {filmJob ? 'Фільм' : `${job.episodes.length} серій`} ·{' '}
            {job.resolution ? `${job.resolution} (${job.quality})` : job.quality}
          </span>
        </div>
        <span className={`job-status ${job.status}`}>{statusText[job.status]}</span>
      </div>
      <div className="job-progress">
        <div style={{ width: `${progress}%` }} />
      </div>
      <div className="job-summary">
        <span>{complete}/{job.episodes.length} готово</span>
        <span>{progress}%</span>
      </div>
      <div className="job-episodes">
        {job.episodes.map((episode) => (
          <JobEpisodeRow
            key={episode.episode_id}
            episode={episode}
            isFilm={filmJob}
            canDelete={canDelete}
            onDeleteFile={(episodeId) => onDeleteFile(job, episodeId)}
          />
        ))}
      </div>
      <div className="job-actions">
        {['queued', 'downloading'].includes(job.status) && (
          <button type="button" onClick={() => onCancel(job.id)}>
            <Square size={14} /> Скасувати
          </button>
        )}
        {canRetry && canDelete && (
          <button type="button" onClick={() => onRetry(job.id)}>
            <RotateCcw size={14} /> Повторити невдалі
          </button>
        )}
      </div>
    </article>
  );
}
