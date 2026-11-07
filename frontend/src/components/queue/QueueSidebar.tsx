import type { DownloadJob } from '../../types';
import { JobCard } from './JobCard';
import { QueueEmpty } from './QueueEmpty';

interface QueueSidebarProps {
  jobs: DownloadJob[];
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  onDeleteFile: (job: DownloadJob, episodeId: string) => void;
  onDeleteJob: (job: DownloadJob) => void;
}

export function QueueSidebar({
  jobs,
  onCancel,
  onRetry,
  onDeleteFile,
  onDeleteJob,
}: QueueSidebarProps) {
  const activeJobs = jobs.filter((job) =>
    ['queued', 'downloading', 'partial', 'failed', 'interrupted'].includes(job.status)
  );

  return (
    <aside className="queue-column">
      <div className="queue-heading">
        <div>
          <h2>Завантаження</h2>
          <p>
            {activeJobs.length
              ? `${activeJobs.length} активних завдань`
              : 'Історія завантажень'}
          </p>
        </div>
        <span className="queue-count">{jobs.length}</span>
      </div>

      {!jobs.length ? (
        <QueueEmpty />
      ) : (
        <div className="job-list">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onCancel={onCancel}
              onRetry={onRetry}
              onDeleteFile={onDeleteFile}
              onDeleteJob={onDeleteJob}
            />
          ))}
        </div>
      )}
    </aside>
  );
}
