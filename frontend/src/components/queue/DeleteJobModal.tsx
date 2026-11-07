import { useEffect, useState } from 'react';
import { AlertTriangle, Trash2, X } from 'lucide-react';
import type { DownloadJob } from '../../types';

interface DeleteJobModalProps {
  job: DownloadJob | null;
  onClose: () => void;
  onConfirm: (job: DownloadJob, deleteFiles: boolean) => void;
  busy?: boolean;
}

export function DeleteJobModal({
  job,
  onClose,
  onConfirm,
  busy = false,
}: DeleteJobModalProps) {
  const [deleteFiles, setDeleteFiles] = useState(false);

  useEffect(() => {
    setDeleteFiles(false);
  }, [job?.id]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !busy) {
        onClose();
      }
    }
    if (job) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [job, onClose, busy]);

  if (!job) return null;

  const hasFiles = job.episodes.some(
    (episode) => episode.status === 'complete' && episode.output_file
  );
  const isDownloading = ['queued', 'downloading'].includes(job.status);
  const filmJob = job.episodes.length === 1 && job.episodes[0].season === null;

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-job-title"
    >
      <div className="modal-window">
        <div className="modal-header">
          <div className="modal-icon danger">
            <Trash2 size={20} />
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            disabled={busy}
            aria-label="Закрити"
          >
            <X size={18} />
          </button>
        </div>

        <h3 id="delete-job-title" className="modal-title">
          Видалити картку завдання?
        </h3>

        <p className="modal-text">
          Ви збираєтеся видалити завдання <strong>«{job.title}»</strong> (
          {filmJob ? 'фільм' : `${job.episodes.length} серій`}) зі списку.
        </p>

        {isDownloading && (
          <div className="modal-warning">
            <AlertTriangle size={17} />
            <span>Завантаження ще триває. Його буде припинено.</span>
          </div>
        )}

        {hasFiles && (
          <label className="modal-checkbox">
            <input
              type="checkbox"
              checked={deleteFiles}
              onChange={(e) => setDeleteFiles(e.target.checked)}
              disabled={busy}
            />
            <span>Також видалити завантажені файли з диска</span>
          </label>
        )}

        <div className="modal-actions">
          <button
            type="button"
            className="button-secondary"
            onClick={onClose}
            disabled={busy}
          >
            Скасувати
          </button>
          <button
            type="button"
            className="button-danger"
            onClick={() => onConfirm(job, deleteFiles)}
            disabled={busy}
          >
            <Trash2 size={15} />
            {deleteFiles ? 'Видалити завдання та файли' : 'Видалити завдання'}
          </button>
        </div>
      </div>
    </div>
  );
}
