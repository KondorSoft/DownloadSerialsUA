import { CircleAlert } from 'lucide-react';

interface NoticeProps {
  message: string;
  type?: 'info' | 'error';
}

export function Notice({ message, type = 'info' }: NoticeProps) {
  if (!message) return null;
  return (
    <div
      className={`notice ${type === 'error' ? 'error' : ''}`}
      role={type === 'error' ? 'alert' : 'status'}
    >
      <CircleAlert size={18} />
      {message}
    </div>
  );
}
