import type { FormEvent } from 'react';
import { Link2, LoaderCircle, Search } from 'lucide-react';

interface SearchFormProps {
  url: string;
  onUrlChange: (url: string) => void;
  onSubmit: (event: FormEvent) => void;
  disabled: boolean;
  isScanning: boolean;
}

export function SearchForm({
  url,
  onUrlChange,
  onSubmit,
  disabled,
  isScanning,
}: SearchFormProps) {
  return (
    <form className="search-form" onSubmit={onSubmit}>
      <label htmlFor="source-url">Посилання на фільм, сезон або серію</label>
      <div className="search-line">
        <div className="url-field">
          <Link2 size={20} />
          <input
            id="source-url"
            value={url}
            onChange={(event) => onUrlChange(event.target.value)}
            placeholder="https://uakino.best/seriesss/..."
            type="url"
            required
          />
        </div>
        <button className="primary-button" type="submit" disabled={disabled}>
          {isScanning ? <LoaderCircle className="spin" size={19} /> : <Search size={19} />}{' '}
          Пошук
        </button>
      </div>
      <div className="source-tags">
        <span>UAKINO</span>
        <span>UAFLIX</span>
        <span>Роздільність кадру й розмір файлу</span>
      </div>
    </form>
  );
}
