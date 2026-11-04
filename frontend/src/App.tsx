import { useEffect, useMemo, useState } from 'react';
import { ArrowDownToLine, Check, CircleAlert, Clapperboard, FolderOpen, Link2, LoaderCircle, Play, RotateCcw, Search, Square, Trash2, Zap } from 'lucide-react';
import { api, connectEvents, token } from './api';
import type { DownloadJob, Episode, ScanState } from './types';

function size(bytes: number): string {
  if (!bytes) return '—';
  const unit = bytes >= 1024 ** 3 ? 'ГБ' : 'МБ';
  return `${(bytes / (unit === 'ГБ' ? 1024 ** 3 : 1024 ** 2)).toLocaleString('uk-UA', { maximumFractionDigits: 1 })} ${unit}`;
}

function frame(width: number, height: number, fallback: string): string {
  return width && height ? `${width} × ${height}` : fallback;
}

function updateJob(jobs: DownloadJob[], incoming: DownloadJob): DownloadJob[] {
  return [incoming, ...jobs.filter((job) => job.id !== incoming.id)].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

const statusText: Record<string, string> = {
  queued: 'У черзі', downloading: 'Завантажується', complete: 'Готово', partial: 'Частково готово',
  failed: 'Помилка', cancelled: 'Скасовано', interrupted: 'Перервано', deleted: 'Видалено', mixed: 'Частину файлів видалено',
};

export default function App() {
  const [url, setUrl] = useState('');
  const [scan, setScan] = useState<ScanState | null>(null);
  const [jobs, setJobs] = useState<DownloadJob[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [voice, setVoice] = useState('');
  const [quality, setQuality] = useState('');
  const [folder, setFolder] = useState('');
  const [folderLoaded, setFolderLoaded] = useState(false);
  const [mode, setMode] = useState<'sequential' | 'parallel'>('parallel');
  const [parallel, setParallel] = useState(4);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const catalog = scan?.catalog || null;
  const isFilm = !!catalog && catalog.episodes.length === 1 && catalog.episodes[0].season === null;
  const voices = useMemo(() => [...new Set(catalog?.episodes.map((episode) => episode.voice) || [])], [catalog]);
  const visibleEpisodes = useMemo(() => (catalog?.episodes || []).filter((episode) => episode.voice === voice), [catalog, voice]);
  const selectedEpisodes = useMemo(() => visibleEpisodes.filter((episode) => selected.includes(episode.id)), [visibleEpisodes, selected]);
  const qualities = useMemo(() => {
    const labels = [...new Set(selectedEpisodes.flatMap((episode) => episode.variants.map((variant) => variant.label)))];
    return labels.sort((a, b) => parseInt(b) - parseInt(a)).map((label) => ({
      label,
      count: selectedEpisodes.filter((episode) => episode.variants.some((variant) => variant.label === label)).length,
      estimate: selectedEpisodes.reduce((total, episode) => total + (episode.variants.find((variant) => variant.label === label)?.estimated_bytes || 0), 0),
      frames: [...new Set(selectedEpisodes.flatMap((episode) => episode.variants.filter((variant) => variant.label === label).map((variant) => frame(variant.width, variant.height, label))))],
    }));
  }, [selectedEpisodes]);
  const chosenQuality = qualities.find((item) => item.label === quality);

  useEffect(() => {
    api.jobs().then(setJobs).catch(() => undefined);
    api.getFolder().then((result) => setFolder(result.path)).catch((error) => setMessage((error as Error).message)).finally(() => setFolderLoaded(true));
    const savedScan = sessionStorage.getItem('kadr-scan');
    if (savedScan) api.getScan(savedScan).then(setScan).catch(() => undefined);
    let socket: WebSocket | null = null;
    let timer: number;
    const open = () => {
      socket = connectEvents((event) => {
        if (event.type === 'job' && event.job) setJobs((current) => updateJob(current, event.job!));
        if (event.type === 'scan' && event.scan) setScan(event.scan);
      });
      socket.onclose = () => { timer = window.setTimeout(open, 2000); };
    };
    if (token) open();
    return () => { if (socket) { socket.onclose = null; socket.close(); } window.clearTimeout(timer); };
  }, []);

  useEffect(() => {
    if (!folderLoaded) return;
    const timer = window.setTimeout(() => { api.saveFolder(folder).catch((error) => setMessage((error as Error).message)); }, 300);
    return () => window.clearTimeout(timer);
  }, [folder, folderLoaded]);

  useEffect(() => {
    if (!scan || scan.status !== 'scanning') return;
    const timer = window.setInterval(() => api.getScan(scan.id).then(setScan).catch(() => undefined), 1500);
    return () => window.clearInterval(timer);
  }, [scan?.id, scan?.status]);

  useEffect(() => {
    if (!catalog) return;
    const nextVoice = voices.includes(voice) ? voice : voices[0] || '';
    if (nextVoice !== voice) setVoice(nextVoice);
  }, [catalog?.id, voices, voice]);

  useEffect(() => {
    if (!catalog || !voice) return;
    setSelected(catalog.episodes.filter((episode) => episode.voice === voice).map((episode) => episode.id));
  }, [catalog?.id, voice]);

  useEffect(() => {
    if (!qualities.some((item) => item.label === quality && item.count === selectedEpisodes.length)) {
      setQuality(qualities.find((item) => item.count === selectedEpisodes.length)?.label || '');
    }
  }, [qualities, quality, selectedEpisodes.length]);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setMessage(''); setScan(null);
    try {
      const created = await api.scan(url.trim());
      sessionStorage.setItem('kadr-scan', created.id);
      setScan(created);
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }

  function toggle(episode: Episode) {
    setSelected((current) => current.includes(episode.id) ? current.filter((id) => id !== episode.id) : [...current, episode.id]);
  }

  async function start() {
    if (!catalog || !quality || !selected.length) return;
    setBusy(true); setMessage('');
    try {
      const created = await api.start({ catalog_id: scan!.id, episode_ids: selected, quality,
        output_dir: folder.trim(), parallel_limit: mode === 'sequential' ? 1 : Math.min(parallel, selected.length, 35) });
      setJobs((current) => updateJob(current, created));
      setMessage('Завантаження розпочато. Вкладку можна закрити — локальна служба продовжить роботу.');
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }

  async function action(id: string, type: 'cancel' | 'retry') {
    try {
      const updated = await api[type](id);
      setJobs((current) => updateJob(current, updated));
    } catch (error) { setMessage((error as Error).message); }
  }

  async function deleteFile(job: DownloadJob, episodeId: string) {
    const episode = job.episodes.find((item) => item.episode_id === episodeId);
    if (!episode?.output_file || !window.confirm(`Видалити файл з диска?\n${episode.output_file}\n\nЦю дію не можна скасувати.`)) return;
    try {
      const updated = await api.deleteFile(job.id, episodeId);
      setJobs((current) => updateJob(current, updated));
      setMessage('Файл видалено з диска.');
    } catch (error) { setMessage((error as Error).message); }
  }

  const activeJobs = jobs.filter((job) => ['queued', 'downloading', 'partial', 'failed', 'interrupted'].includes(job.status));

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><Clapperboard size={22} strokeWidth={2.2} /></span><span>Кадр</span></div>
      <span className="topbar-note"><span className="connection-dot" /> Локальний застосунок</span>
    </header>

    <main className="layout">
      <section className="main-column">
        <div className="intro">
          <p className="intro-kicker">Відео зберігається на вашому комп’ютері</p>
          <h1>Збережіть фільм.<br />Серію або весь сезон.</h1>
          <p className="intro-copy">Вставте посилання з UAKINO або UAFLIX. Оберіть якість, папку та спосіб завантаження.</p>
        </div>

        <form className="search-form" onSubmit={search}>
          <label htmlFor="source-url">Посилання на фільм, сезон або серію</label>
          <div className="search-line"><div className="url-field"><Link2 size={20} /><input id="source-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://uakino.best/seriesss/..." type="url" required /></div><button className="primary-button" type="submit" disabled={busy || scan?.status === 'scanning'}>{scan?.status === 'scanning' ? <LoaderCircle className="spin" size={19} /> : <Search size={19} />} Пошук</button></div>
          <div className="source-tags"><span>UAKINO</span><span>UAFLIX</span><span>Роздільність кадру й розмір файлу</span></div>
        </form>

        {message && <div className="notice" role="status"><CircleAlert size={18} />{message}</div>}
        {scan?.status === 'scanning' && <section className="scan-state"><LoaderCircle className="spin" size={22} /><div><strong>{scan.message}</strong><span>{scan.total ? `${scan.done} із ${scan.total} серій` : 'Список серій з’явиться тут'}</span></div></section>}
        {scan?.status === 'failed' && <div className="notice error" role="alert"><CircleAlert size={18} />{scan.error}</div>}

        {catalog && <>
          <section className="catalog-heading">
            <div><span className="site-badge">{catalog.site}</span><h2>{catalog.title}</h2><p>{isFilm ? 'Фільм' : `${catalog.season ? `${catalog.season} сезон` : 'Серіал'} / ${catalog.episodes.length} ${catalog.episodes.length === 1 ? 'серія' : 'серій'}`}</p></div>
            <div className="catalog-icon"><Play size={25} fill="currentColor" /></div>
          </section>

          <section className="content-block">
            <div className="block-title"><div><h3>{isFilm ? 'Фільм' : 'Серії'}</h3><p>{isFilm ? 'Доступний для завантаження' : 'Виберіть потрібні епізоди'}</p></div>{!isFilm && <div className="selection-actions"><button type="button" onClick={() => setSelected(visibleEpisodes.map((episode) => episode.id))}>Усі</button><button type="button" onClick={() => setSelected([])}>Жодної</button></div>}</div>
            {voices.length > 1 && <div className="voice-tabs" role="tablist" aria-label="Озвучення">{voices.map((item) => <button type="button" role="tab" aria-selected={item === voice} className={item === voice ? 'active' : ''} onClick={() => setVoice(item)} key={item}>{item}</button>)}</div>}
            <div className="episode-list">{visibleEpisodes.map((episode) => <label className={`episode-row ${selected.includes(episode.id) ? 'selected' : ''}`} key={episode.id}><input type="checkbox" checked={selected.includes(episode.id)} onChange={() => toggle(episode)} /><span className="custom-check">{selected.includes(episode.id) && <Check size={14} strokeWidth={3} />}</span><span className="episode-number">{episode.season ? `S${String(episode.season).padStart(2, '0')}E${String(episode.number).padStart(2, '0')}` : 'Фільм'}</span><span className="episode-name">{episode.season ? `Серія ${episode.number}` : catalog.title}<small>{episode.voice}</small></span><span className="episode-variants">{episode.variants.length ? episode.variants.map((variant) => frame(variant.width, variant.height, variant.label)).join(' / ') : 'Недоступно'}</span></label>)}</div>
          </section>

          <section className="content-block settings-block">
            <div className="block-title"><div><h3>Параметри</h3><p>Якість і місце збереження</p></div></div>
            <label className="field-label">Якість</label>
            <div className="quality-grid">{qualities.map((option) => <button type="button" key={option.label} className={`quality-option ${quality === option.label ? 'active' : ''}`} disabled={option.count !== selectedEpisodes.length} onClick={() => setQuality(option.label)}><span className="quality-head"><strong>{option.frames.length === 1 ? option.frames[0] : 'Різна роздільність'}</strong>{quality === option.label && <Check size={18} />}</span><span>≈ {size(option.estimate)}</span><small>{option.label} · {isFilm ? 'доступно' : `${option.count}/${selectedEpisodes.length} серій`}</small></button>)}</div>
            <label className="field-label" htmlFor="output-folder">Папка для збереження</label>
            <div className="folder-line"><input id="output-folder" value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="Папка «Завантаження»" /><button type="button" onClick={async () => { try { const result = await api.chooseFolder(folder); if (result.path) setFolder(result.path); } catch (error) { setMessage((error as Error).message); } }}><FolderOpen size={18} /> Огляд</button></div>
            {selectedEpisodes.length > 1 && <><label className="field-label">Режим завантаження</label>
            <div className="mode-grid"><button type="button" className={mode === 'sequential' ? 'mode active' : 'mode'} onClick={() => setMode('sequential')}><span><ArrowDownToLine size={19} /> По черзі</span><small>Одна серія за раз</small></button><button type="button" className={mode === 'parallel' ? 'mode active' : 'mode'} onClick={() => setMode('parallel')}><span><Zap size={19} /> Паралельно</span><small>Кілька серій одночасно</small></button></div>
            {mode === 'parallel' && <div className="parallel-line"><label htmlFor="parallel-count">Одночасних серій</label><input id="parallel-count" type="number" min={1} max={Math.min(35, selected.length || 1)} value={parallel} onChange={(event) => setParallel(Number(event.target.value))} /><button type="button" onClick={() => setParallel(Math.min(35, selected.length))}>Усі паралельно</button></div>}</>}
            <div className="download-footer"><div><strong>{isFilm ? 'Фільм' : `${selected.length} ${selected.length === 1 ? 'серія' : 'серій'}`}</strong><span>≈ {size(chosenQuality?.estimate || 0)} до завантаження</span></div><button className="primary-button download-button" type="button" disabled={busy || !selected.length || !quality || !folder.trim()} onClick={start}><ArrowDownToLine size={20} /> Завантажити</button></div>
          </section>
        </>}
      </section>

      <aside className="queue-column">
        <div className="queue-heading"><div><h2>Завантаження</h2><p>{activeJobs.length ? `${activeJobs.length} активних завдань` : 'Історія завантажень'}</p></div><span className="queue-count">{jobs.length}</span></div>
        {!jobs.length ? <div className="queue-empty"><div className="empty-symbol"><ArrowDownToLine size={28} /></div><strong>Поки що порожньо</strong><p>Знайдіть фільм або серії та натисніть «Завантажити». Тут з’явиться прогрес.</p></div> :
          <div className="job-list">{jobs.map((job) => {
            const complete = job.episodes.filter((episode) => episode.status === 'complete').length;
            const progress = Math.round(job.episodes.reduce((sum, episode) => sum + episode.percent, 0) / job.episodes.length);
            const filmJob = job.episodes.length === 1 && job.episodes[0].season === null;
            const canDelete = !['queued', 'downloading'].includes(job.status);
            const canRetry = job.episodes.some((episode) => ['failed', 'cancelled'].includes(episode.status));
            return <article className="job-card" key={job.id}>
              <div className="job-top"><div><strong>{job.title}</strong><span>{filmJob ? 'Фільм' : `${job.episodes.length} серій`} · {job.resolution ? `${job.resolution} (${job.quality})` : job.quality}</span></div><span className={`job-status ${job.status}`}>{statusText[job.status]}</span></div>
              <div className="job-progress"><div style={{ width: `${progress}%` }} /></div>
              <div className="job-summary"><span>{complete}/{job.episodes.length} готово</span><span>{progress}%</span></div>
              <div className="job-episodes">{job.episodes.map((episode) => <div className="job-episode" key={episode.episode_id}>
                <span className="job-episode-icon">{episode.status === 'complete' ? <Check size={14} /> : episode.status === 'downloading' ? <LoaderCircle className="spin" size={14} /> : episode.status === 'failed' ? <CircleAlert size={14} /> : <span />}</span>
                <span>{filmJob ? 'Фільм' : `Серія ${episode.number}`}</span>
                <small>{episode.status === 'downloading' ? `${episode.percent.toFixed(0)}% ${episode.speed}` : statusText[episode.status]}</small>
                {episode.error && <em title={episode.error}>!</em>}
                {canDelete && episode.status === 'complete' && episode.output_file && <button className="file-delete" type="button" title="Видалити файл з диска" aria-label={`Видалити ${filmJob ? 'фільм' : `серію ${episode.number}`} з диска`} onClick={() => deleteFile(job, episode.episode_id)}><Trash2 size={15} /></button>}
              </div>)}</div>
              <div className="job-actions">{['queued', 'downloading'].includes(job.status) && <button type="button" onClick={() => action(job.id, 'cancel')}><Square size={14} /> Скасувати</button>}{canRetry && canDelete && <button type="button" onClick={() => action(job.id, 'retry')}><RotateCcw size={14} /> Повторити невдалі</button>}</div>
            </article>;
          })}</div>}
      </aside>
    </main>
    <footer className="site-footer">Кадр працює лише на вашому комп’ютері. Підтримуються доступні потоки UAKINO та UAFLIX.</footer>
  </div>;
}
