import { ArrowDownToLine, Check, FolderOpen, Sparkles, Zap } from 'lucide-react';
import type { DownloadMode, QualityOption } from '../../types';
import { formatSize } from '../../utils/format';

interface DownloadSettingsProps {
  isFilm: boolean;
  qualities: QualityOption[];
  quality: string;
  onQualityChange: (quality: string) => void;
  selectedCount: number;
  folder: string;
  onFolderChange: (folder: string) => void;
  onBrowseFolder: () => void;
  mode: DownloadMode;
  onModeChange: (mode: DownloadMode) => void;
  parallel: number;
  onParallelChange: (parallel: number) => void;
  chosenQuality?: QualityOption;
  onStartDownload: () => void;
  busy: boolean;
}

export function DownloadSettings({
  isFilm,
  qualities,
  quality,
  onQualityChange,
  selectedCount,
  folder,
  onFolderChange,
  onBrowseFolder,
  mode,
  onModeChange,
  parallel,
  onParallelChange,
  chosenQuality,
  onStartDownload,
  busy,
}: DownloadSettingsProps) {
  return (
    <section className="content-block settings-block">
      <div className="block-title">
        <div>
          <h3>Параметри</h3>
          <p>Якість і місце збереження</p>
        </div>
      </div>

      <div className="quality-header">
        <label className="field-label" style={{ margin: 0 }}>Якість</label>
        <button
          type="button"
          className="max-quality-shortcut"
          onClick={() => onQualityChange('max')}
          title="Вибрати максимальну якість для всіх вибраних серій"
        >
          <Sparkles size={14} /> Максимальна якість для всіх
        </button>
      </div>

      <div className="quality-grid">
        {qualities.map((option) => (
          <button
            type="button"
            key={option.label}
            className={`quality-option ${option.isMax ? 'is-max' : ''} ${quality === option.label ? 'active' : ''}`}
            disabled={option.count !== selectedCount}
            onClick={() => onQualityChange(option.label)}
          >
            <span className="quality-head">
              <strong>
                {option.isMax
                  ? 'Максимальна'
                  : option.frames.length === 1
                  ? option.frames[0]
                  : 'Різна роздільність'}
              </strong>
              {quality === option.label && <Check size={18} />}
            </span>
            <span>≈ {formatSize(option.estimate)}</span>
            <small>
              {option.isMax
                ? (option.frames.length === 1
                    ? `Найвища · ${option.frames[0]}`
                    : `Найвища для кожної із ${selectedCount} серій`)
                : `${option.label} · ${isFilm ? 'доступно' : `${option.count}/${selectedCount} серій`}`}
            </small>
          </button>
        ))}
      </div>

      <label className="field-label" htmlFor="output-folder">
        Папка для збереження
      </label>
      <div className="folder-line">
        <input
          id="output-folder"
          value={folder}
          onChange={(event) => onFolderChange(event.target.value)}
          placeholder="Папка «Завантаження»"
        />
        <button type="button" onClick={onBrowseFolder}>
          <FolderOpen size={18} /> Огляд
        </button>
      </div>

      {selectedCount > 1 && (
        <>
          <label className="field-label">Режим завантаження</label>
          <div className="mode-grid">
            <button
              type="button"
              className={mode === 'sequential' ? 'mode active' : 'mode'}
              onClick={() => onModeChange('sequential')}
            >
              <span><ArrowDownToLine size={19} /> По черзі</span>
              <small>Одна серія за раз</small>
            </button>
            <button
              type="button"
              className={mode === 'parallel' ? 'mode active' : 'mode'}
              onClick={() => onModeChange('parallel')}
            >
              <span><Zap size={19} /> Паралельно</span>
              <small>Кілька серій одночасно</small>
            </button>
          </div>

          {mode === 'parallel' && (
            <div className="parallel-line">
              <label htmlFor="parallel-count">Одночасних серій</label>
              <input
                id="parallel-count"
                type="number"
                min={1}
                max={Math.min(35, selectedCount || 1)}
                value={parallel}
                onChange={(event) => onParallelChange(Number(event.target.value))}
              />
              <button
                type="button"
                onClick={() => onParallelChange(Math.min(35, selectedCount))}
              >
                Усі паралельно
              </button>
            </div>
          )}
        </>
      )}

      <div className="download-footer">
        <div>
          <strong>
            {isFilm ? 'Фільм' : `${selectedCount} ${selectedCount === 1 ? 'серія' : 'серій'}`}
          </strong>
          <span>
            {chosenQuality?.isMax ? 'Максимальна якість · ' : ''}≈ {formatSize(chosenQuality?.estimate || 0)} до завантаження
          </span>
        </div>
        <button
          className="primary-button download-button"
          type="button"
          disabled={busy || !selectedCount || !quality || !folder.trim()}
          onClick={onStartDownload}
        >
          <ArrowDownToLine size={20} /> Завантажити
        </button>
      </div>
    </section>
  );
}
