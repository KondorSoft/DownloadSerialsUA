import { Check, CircleAlert, LoaderCircle, Trash2 } from 'lucide-react';
import type { EpisodeProgress } from '../../types';
import { statusText } from '../../utils/format';

interface JobEpisodeRowProps {
  episode: EpisodeProgress;
  isFilm: boolean;
  canDelete: boolean;
  onDeleteFile: (episodeId: string) => void;
}

export function JobEpisodeRow({
  episode,
  isFilm,
  canDelete,
  onDeleteFile,
}: JobEpisodeRowProps) {
  return (
    <div className="job-episode">
      <span className="job-episode-icon">
        {episode.status === 'complete' ? (
          <Check size={14} />
        ) : episode.status === 'downloading' ? (
          <LoaderCircle className="spin" size={14} />
        ) : episode.status === 'failed' ? (
          <CircleAlert size={14} />
        ) : (
          <span />
        )}
      </span>
      <span>{isFilm ? 'Фільм' : `Серія ${episode.number}`}</span>
      <small>
        {episode.status === 'downloading'
          ? `${episode.percent.toFixed(0)}% ${episode.speed}`
          : statusText[episode.status]}
      </small>
      {episode.error && <em title={episode.error}>!</em>}
      {canDelete && episode.status === 'complete' && episode.output_file && (
        <button
          className="file-delete"
          type="button"
          title="Видалити файл з диска"
          aria-label={`Видалити ${isFilm ? 'фільм' : `серію ${episode.number}`} з диска`}
          onClick={() => onDeleteFile(episode.episode_id)}
        >
          <Trash2 size={15} />
        </button>
      )}
    </div>
  );
}
