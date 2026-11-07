import { Play } from 'lucide-react';
import type { Catalog } from '../../types';

interface CatalogHeadingProps {
  catalog: Catalog;
  isFilm: boolean;
}

export function CatalogHeading({ catalog, isFilm }: CatalogHeadingProps) {
  return (
    <section className="catalog-heading">
      <div>
        <span className="site-badge">{catalog.site}</span>
        <h2>{catalog.title}</h2>
        <p>
          {isFilm
            ? 'Фільм'
            : `${catalog.season ? `${catalog.season} сезон` : 'Серіал'} / ${catalog.episodes.length} ${
                catalog.episodes.length === 1 ? 'серія' : 'серій'
              }`}
        </p>
      </div>
      <div className="catalog-icon">
        <Play size={25} fill="currentColor" />
      </div>
    </section>
  );
}
