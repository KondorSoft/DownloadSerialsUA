import React, { useEffect, useMemo, useState } from 'react';
import { api, connectEvents, token } from './api';
import {
  CatalogHeading,
  DownloadSettings,
  EpisodeList,
  Footer,
  Header,
  Intro,
  Notice,
  QueueSidebar,
  ScanStatus,
  SearchForm,
} from './components';
import type { DownloadJob, DownloadMode, Episode, QualityOption, ScanState } from './types';
import { formatFrame, updateJob } from './utils/format';

export default function App() {
  const [url, setUrl] = useState('');
  const [scan, setScan] = useState<ScanState | null>(null);
  const [jobs, setJobs] = useState<DownloadJob[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [voice, setVoice] = useState('');
  const [quality, setQuality] = useState('');
  const [folder, setFolder] = useState('');
  const [folderLoaded, setFolderLoaded] = useState(false);
  const [mode, setMode] = useState<DownloadMode>('parallel');
  const [parallel, setParallel] = useState(4);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const catalog = scan?.catalog || null;
  const isFilm = !!catalog && catalog.episodes.length === 1 && catalog.episodes[0].season === null;
  const voices = useMemo(() => [...new Set(catalog?.episodes.map((episode) => episode.voice) || [])], [catalog]);
  const visibleEpisodes = useMemo(() => (catalog?.episodes || []).filter((episode) => episode.voice === voice), [catalog, voice]);
  const selectedEpisodes = useMemo(() => visibleEpisodes.filter((episode) => selected.includes(episode.id)), [visibleEpisodes, selected]);

  const qualities: QualityOption[] = useMemo(() => {
    const labels = [...new Set(selectedEpisodes.flatMap((episode) => episode.variants.map((variant) => variant.label)))];
    return labels
      .sort((a, b) => parseInt(b, 10) - parseInt(a, 10))
      .map((label) => ({
        label,
        count: selectedEpisodes.filter((episode) => episode.variants.some((variant) => variant.label === label)).length,
        estimate: selectedEpisodes.reduce(
          (total, episode) => total + (episode.variants.find((variant) => variant.label === label)?.estimated_bytes || 0),
          0
        ),
        frames: [
          ...new Set(
            selectedEpisodes.flatMap((episode) =>
              episode.variants
                .filter((variant) => variant.label === label)
                .map((variant) => formatFrame(variant.width, variant.height, label))
            )
          ),
        ],
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
      socket.onclose = () => {
        timer = window.setTimeout(open, 2000);
      };
    };

    if (token) open();
    return () => {
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!folderLoaded) return;
    const timer = window.setTimeout(() => {
      api.saveFolder(folder).catch((error) => setMessage((error as Error).message));
    }, 300);
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
    setBusy(true);
    setMessage('');
    setScan(null);
    try {
      const created = await api.scan(url.trim());
      sessionStorage.setItem('kadr-scan', created.id);
      setScan(created);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function toggle(episode: Episode) {
    setSelected((current) =>
      current.includes(episode.id) ? current.filter((id) => id !== episode.id) : [...current, episode.id]
    );
  }

  async function start() {
    if (!catalog || !quality || !selected.length) return;
    setBusy(true);
    setMessage('');
    try {
      const created = await api.start({
        catalog_id: scan!.id,
        episode_ids: selected,
        quality,
        output_dir: folder.trim(),
        parallel_limit: mode === 'sequential' ? 1 : Math.min(parallel, selected.length, 35),
      });
      setJobs((current) => updateJob(current, created));
      setMessage('Завантаження розпочато. Вкладку можна закрити — локальна служба продовжить роботу.');
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function action(id: string, type: 'cancel' | 'retry') {
    try {
      const updated = await api[type](id);
      setJobs((current) => updateJob(current, updated));
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function deleteFile(job: DownloadJob, episodeId: string) {
    const episode = job.episodes.find((item) => item.episode_id === episodeId);
    if (!episode?.output_file || !window.confirm(`Видалити файл з диска?\n${episode.output_file}\n\nЦю дію не можна скасувати.`)) return;
    try {
      const updated = await api.deleteFile(job.id, episodeId);
      setJobs((current) => updateJob(current, updated));
      setMessage('Файл видалено з диска.');
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function handleBrowseFolder() {
    try {
      const result = await api.chooseFolder(folder);
      if (result.path) setFolder(result.path);
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  return (
    <div className="app-shell">
      <Header />

      <main className="layout">
        <section className="main-column">
          <Intro />

          <SearchForm
            url={url}
            onUrlChange={setUrl}
            onSubmit={search}
            disabled={busy || scan?.status === 'scanning'}
            isScanning={scan?.status === 'scanning'}
          />

          <Notice message={message} />
          <ScanStatus scan={scan} />

          {catalog && (
            <>
              <CatalogHeading catalog={catalog} isFilm={isFilm} />

              <EpisodeList
                catalog={catalog}
                isFilm={isFilm}
                voices={voices}
                voice={voice}
                onVoiceChange={setVoice}
                visibleEpisodes={visibleEpisodes}
                selected={selected}
                onToggleEpisode={toggle}
                onSelectAll={() => setSelected(visibleEpisodes.map((episode) => episode.id))}
                onSelectNone={() => setSelected([])}
              />

              <DownloadSettings
                isFilm={isFilm}
                qualities={qualities}
                quality={quality}
                onQualityChange={setQuality}
                selectedCount={selectedEpisodes.length}
                folder={folder}
                onFolderChange={setFolder}
                onBrowseFolder={handleBrowseFolder}
                mode={mode}
                onModeChange={setMode}
                parallel={parallel}
                onParallelChange={setParallel}
                chosenQuality={chosenQuality}
                onStartDownload={start}
                busy={busy}
              />
            </>
          )}
        </section>

        <QueueSidebar
          jobs={jobs}
          onCancel={(id) => action(id, 'cancel')}
          onRetry={(id) => action(id, 'retry')}
          onDeleteFile={deleteFile}
        />
      </main>

      <Footer />
    </div>
  );
}
