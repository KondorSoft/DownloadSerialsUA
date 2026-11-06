import { ArrowDownToLine } from 'lucide-react';

export function QueueEmpty() {
  return (
    <div className="queue-empty">
      <div className="empty-symbol">
        <ArrowDownToLine size={28} />
      </div>
      <strong>Поки що порожньо</strong>
      <p>Знайдіть фільм або серії та натисніть «Завантажити». Тут з’явиться прогрес.</p>
    </div>
  );
}
