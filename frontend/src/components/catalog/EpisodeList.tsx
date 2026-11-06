import { Check } from 'lucide-react';
import type { Catalog, Episode } from '../../types';
import { formatFrame } from '../../utils/format';

interface EpisodeListProps {
  catalog: Catalog;
  isFilm: boolean;
  voices: string[];
  voice: string;
  onVoiceChange: (voice: string) => void;
  visibleEpisodes: Episode[];
  selected: string[];
  onToggleEpisode: (episode: Episode) => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
}

export function EpisodeList({
  catalog,
  isFilm,
  voices,
  voice,
  onVoiceChange,
  visibleEpisodes,
  selected,
  onToggleEpisode,
  onSelectAll,
  onSelectNone,
}: EpisodeListProps) {
  return (
    <section className="content-block">
      <div className="block-title">
        <div>
          <h3>{isFilm ? 'Фільм' : 'Серії'}</h3>
          <p>{isFilm ? 'Доступний для завантаження' : 'Виберіть потрібні епізоди'}</p>
        </div>
        {!isFilm && (
          <div className="selection-actions">
            <button type="button" onClick={onSelectAll}>
              Усі
            </button>
            <button type="button" onClick={onSelectNone}>
              Жодної
            </button>
          </div>
        )}
      </div>

      {voices.length > 1 && (
        <div className="voice-tabs" role="tablist" aria-label="Озвучення">
          {voices.map((item) => (
            <button
              type="button"
              role="tab"
              aria-selected={item === voice}
              className={item === voice ? 'active' : ''}
              onClick={() => onVoiceChange(item)}
              key={item}
            >
              {item}
            </button>
          ))}
        </div>
      )}

      <div className="episode-list">
        {visibleEpisodes.map((episode) => {
          const isSelected = selected.includes(episode.id);
          return (
            <label
              className={`episode-row ${isSelected ? 'selected' : ''}`}
              key={episode.id}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleEpisode(episode)}
              />
              <span className="custom-check">
                {isSelected && <Check size={14} strokeWidth={3} />}
              </span>
              <span className="episode-number">
                {episode.season
                  ? `S${String(episode.season).padStart(2, '0')}E${String(episode.number).padStart(2, '0')}`
                  : 'Фільм'}
              </span>
              <span className="episode-name">
                {episode.season ? `Серія ${episode.number}` : catalog.title}
                <small>{episode.voice}</small>
              </span>
              <span className="episode-variants">
                {episode.variants.length
                  ? episode.variants
                      .map((variant) => formatFrame(variant.width, variant.height, variant.label))
                      .join(' / ')
                  : 'Недоступно'}
              </span>
            </label>
          );
        })}
      </div>
    </section>
  );
}
