import { CircleAlert, LoaderCircle } from 'lucide-react';
import type { ScanState } from '../types';

interface ScanStatusProps {
  scan: ScanState | null;
}

export function ScanStatus({ scan }: ScanStatusProps) {
  if (!scan) return null;

  if (scan.status === 'scanning') {
    return (
      <section className="scan-state">
        <LoaderCircle className="spin" size={22} />
        <div>
          <strong>{scan.message}</strong>
          <span>
            {scan.total ? `${scan.done} із ${scan.total} серій` : 'Список серій з’явиться тут'}
          </span>
        </div>
      </section>
    );
  }

  if (scan.status === 'failed') {
    return (
      <div className="notice error" role="alert">
        <CircleAlert size={18} />
        {scan.error}
      </div>
    );
  }

  return null;
}
