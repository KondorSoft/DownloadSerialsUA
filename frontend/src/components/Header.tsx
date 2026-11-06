import { Clapperboard } from 'lucide-react';

export function Header() {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">
          <Clapperboard size={22} strokeWidth={2.2} />
        </span>
        <span>Кадр</span>
      </div>
      <span className="topbar-note">
        <span className="connection-dot" /> Локальний застосунок
      </span>
    </header>
  );
}
