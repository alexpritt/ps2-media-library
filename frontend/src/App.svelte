<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { MediaItem } from './types';

  type Stage = 'boot' | 'console' | 'library' | 'details';
  type Category = 'Games' | 'Music';

  type HistoryState = {
    stage: Stage;
    category: Category | null;
    console: string | null;
    itemId: number | null;
    page: number;
  };

  type AdminForm = {
    id: number | null;
    title: string;
    category: Category;
    platform: string;
    genre: string;
    release_date: string;
    year_released: string;
    players: string;
    artist: string;
    cover_image: string;
    notes: string;
  };

  type ConsoleOption = {
    name: string;
    shortName: string;
    logo: string;
    logoImage?: string;
  };

  const ZOOM_TRANSITION_MS = 900;

  const fallbackConsoles: ConsoleOption[] = [
    { name: 'PlayStation 2', shortName: 'PS2', logo: 'PS2',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg' },
    { name: 'PlayStation 3', shortName: 'PS3', logo: 'PS3',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg' },
    { name: 'PlayStation 4', shortName: 'PS4', logo: 'PS4',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg' },
    { name: 'Nintendo DS', shortName: 'NDS', logo: 'NDS',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg' },
    { name: 'GameBoy', shortName: 'GB', logo: 'GB',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg' },
  ];

  let stage: Stage = 'boot';
  let category: Category | null = null;
  let selectedConsole: string | null = null;
  let media: MediaItem[] = [];
  let allMedia: MediaItem[] = [];
  let selectedItem: MediaItem | null = null;

  let bootVideoRef: HTMLVideoElement | null = null;
  let bootMuted = true;  // true = muted until first user interaction
  let bootTextVisible = false;
  let bootError = false;
  let bootHover: Category = 'Games';
  let bootSoundIndicator = '';
  let bootSoundIndicatorVisible = false;
  let bootSoundIndicatorTimeout: ReturnType<typeof setTimeout> | null = null;
  let bootStartAt = 0;
  let bootStarted = false;
  let bootResumeAtSix = false;
  const BOOT_SKIP_TIME = 6;

  let transitionOverlay = false;
  let transitionOpacity = 0;
  let isTransitioning = false;
  let transitionToBlack = false;
  let bootAudioFadeInMs = 0;
  let launchConsoleName: string | null = null;
  let launchItemId: number | null = null;

  let hoveredConsole: string | null = null;
  let hoveredItemId: number | null = null;
  let brokenCoverIds = new Set<number>();

  let page = 0;
  let itemsPerPage = 15;
  let mediaLoadRequestId = 0;
  let libraryLoading = false;

  let adminToken = '';
  let adminOpen = false;
  let detailsEditMode = false;
  let adminEditingId: number | null = null;
  let adminPassword = '';
  let adminBusy = false;
  let adminError = '';
  let adminMessage = '';
  let adminForm: AdminForm = emptyAdminForm();
  let customSystems: string[] = [];
  let newSystemName = '';
  let systemError = '';
  let adminListPage = 0;
  let adminListItemsPerPage = 10;
  let adminSearchQuery = '';
  let adminSearchCategory: Category | 'All' = 'All';
  let adminSearchPlatform: string | 'All' = 'All';

  let librarySearch = '';
  let librarySearchOpen = false;
  let librarySearchInput: HTMLInputElement | null = null;
  let libraryPlayersFilter: number | null = null;
  let playersDropdownOpen = false;
  let detailsManualRotateY = 0;
  let detailsDragActive = false;
  let detailsDragStartX = 0;
  let detailsRotateStartY = 0;
  let detailsSpinPaused = false;
  let detailsDragVelocity = 0;
  let detailsLastDragX = 0;
  let detailsLastDragAt = 0;
  let detailsBoostVelocity = 0;
  let detailsInertiaFrame: number | null = null;
  let detailsSpinPauseTimeout: ReturnType<typeof setTimeout> | null = null;

  let confirmOpen = false;
  let confirmMode: 'edit' | 'delete' = 'delete';
  let confirmItem: MediaItem | null = null;

  $: isAdmin = adminToken.length > 0;
  $: availableConsoles = buildConsoleList();
  $: activeConsole = availableConsoles[0] ?? fallbackConsoles[0];
  $: consoleTitle = hoveredConsole ?? selectedConsole ?? 'Select a Console...';
  $: totalGameLibraryCount = allMedia.filter((item) => item.category === 'Games').length;
  $: consoleLibraryCountLabel = `${totalGameLibraryCount} ${totalGameLibraryCount === 1 ? 'Game' : 'Games'} in Library`;
  $: currentItems = pagedItems();
  $: totalPages = Math.ceil(media.length / itemsPerPage);
  $: libraryCountLabel = category === 'Music'
    ? `${media.length} ${media.length === 1 ? 'Album' : 'Albums'} in Library`
    : `${media.length} ${media.length === 1 ? 'Game' : 'Games'} in Library`;
  $: adminConsoleOptions = availableConsoles.map((item) => item.name);
  $: adminGenreOptions = buildAdminGenreOptions(adminForm.category, allMedia);
  $: adminPlayerOptions = [1, 2, 3, 4, 5, 6, 7, 8];
  $: adminFilteredMedia = allMedia.filter((item) => {
    if (adminSearchQuery.trim() && !item.title.toLowerCase().includes(adminSearchQuery.toLowerCase().trim())) return false;
    if (adminSearchCategory !== 'All' && item.category !== adminSearchCategory) return false;
    if (adminSearchPlatform !== 'All' && item.platform !== adminSearchPlatform) return false;
    return true;
  });
  $: adminListTotalPages = Math.ceil(Math.max(1, adminFilteredMedia.length) / adminListItemsPerPage);
  $: if (adminListPage >= adminListTotalPages) adminListPage = Math.max(0, adminListTotalPages - 1);
  $: adminPagedMedia = adminFilteredMedia.slice(
    adminListPage * adminListItemsPerPage,
    (adminListPage + 1) * adminListItemsPerPage
  );

  $: selectedLibraryConsole = availableConsoles.find((item) => item.name === (selectedConsole ?? activeConsole.name)) ?? activeConsole;
  $: libraryHeaderLeft = category === 'Music' ? 'Music Library' : selectedConsole ?? activeConsole.name;
  $: libraryHeaderRight = libraryCountLabel;
  $: libraryGridKey = `${category ?? ''}-${selectedConsole ?? ''}-${librarySearch.trim().toLowerCase()}-${libraryPlayersFilter ?? 'all'}-${page}`;
  $: showEmptyGamesState = category === 'Games' && !libraryLoading && media.length === 0;
  $: selectedCategory = { category: category ?? 'Games', platform: selectedConsole ?? activeConsole.name };
  $: filteredMedia = (() => {
    const q = librarySearch.trim().toLowerCase();
    let result = [...media].sort((a, b) => a.title.localeCompare(b.title));
    if (q) {
      result = result.filter((item) =>
        item.title.toLowerCase().includes(q) ||
        (item.genre ?? '').toLowerCase().includes(q) ||
        (item.year_released != null && String(item.year_released).includes(q))
      );
    }
    if (libraryPlayersFilter !== null) {
      result = result.filter((item) => (item.players ?? 0) >= libraryPlayersFilter!);
    }
    return result;
  })();
  $: filteredTotalPages = Math.ceil(Math.max(1, filteredMedia.length) / itemsPerPage);
  $: availablePlayerCounts = [...new Set(
    media.filter((i) => i.players != null).map((i) => i.players as number)
  )].sort((a, b) => a - b);
  $: if (stage !== 'library') {
    librarySearchOpen = false;
    playersDropdownOpen = false;
  }
  $: if (stage !== 'details') {
    detailsDragActive = false;
    detailsSpinPaused = false;
    detailsManualRotateY = 0;
    detailsDragVelocity = 0;
    detailsBoostVelocity = 0;
    if (detailsInertiaFrame !== null) {
      cancelAnimationFrame(detailsInertiaFrame);
      detailsInertiaFrame = null;
    }
    if (detailsSpinPauseTimeout) {
      clearTimeout(detailsSpinPauseTimeout);
      detailsSpinPauseTimeout = null;
    }
  }

  function startDetailsInertia() {
    if (detailsInertiaFrame !== null) {
      cancelAnimationFrame(detailsInertiaFrame);
      detailsInertiaFrame = null;
    }

    let lastAt = performance.now();
    const step = (now: number) => {
      const dt = Math.min(0.05, Math.max(0.001, (now - lastAt) / 1000));
      lastAt = now;

      detailsManualRotateY += detailsBoostVelocity * dt;

      const decel = 260;
      if (detailsBoostVelocity > 0) {
        detailsBoostVelocity = Math.max(0, detailsBoostVelocity - decel * dt);
      } else {
        detailsBoostVelocity = Math.min(0, detailsBoostVelocity + decel * dt);
      }

      if (Math.abs(detailsBoostVelocity) > 2) {
        detailsInertiaFrame = requestAnimationFrame(step);
      } else {
        detailsBoostVelocity = 0;
        detailsInertiaFrame = null;
      }
    };

    detailsInertiaFrame = requestAnimationFrame(step);
  }

  function scheduleDetailsSpinResume() {
    if (detailsSpinPauseTimeout) {
      clearTimeout(detailsSpinPauseTimeout);
    }
    detailsSpinPauseTimeout = setTimeout(() => {
      detailsSpinPaused = false;
      detailsSpinPauseTimeout = null;
    }, 850);
  }

  function beginDetailsRotate(event: PointerEvent) {
    if (event.button !== 0) return;
    const target = event.currentTarget as HTMLElement | null;
    target?.setPointerCapture(event.pointerId);

    if (detailsInertiaFrame !== null) {
      cancelAnimationFrame(detailsInertiaFrame);
      detailsInertiaFrame = null;
    }
    detailsBoostVelocity = 0;

    if (detailsSpinPauseTimeout) {
      clearTimeout(detailsSpinPauseTimeout);
      detailsSpinPauseTimeout = null;
    }

    detailsDragActive = true;
    detailsSpinPaused = true;
    detailsDragStartX = event.clientX;
    detailsRotateStartY = detailsManualRotateY;
    detailsLastDragX = event.clientX;
    detailsLastDragAt = performance.now();
    detailsDragVelocity = 0;
  }

  function trackDetailsRotate(event: PointerEvent) {
    if (!detailsDragActive) return;
    const deltaX = event.clientX - detailsDragStartX;
    detailsManualRotateY = detailsRotateStartY + (deltaX * 0.45);

    const now = performance.now();
    const dtMs = Math.max(1, now - detailsLastDragAt);
    const deltaSinceLast = event.clientX - detailsLastDragX;
    const velocityDegPerSec = (deltaSinceLast * 0.45) / (dtMs / 1000);
    detailsDragVelocity = detailsDragVelocity * 0.65 + velocityDegPerSec * 0.35;
    detailsLastDragX = event.clientX;
    detailsLastDragAt = now;
  }

  function endDetailsRotate(event: PointerEvent) {
    if (!detailsDragActive) return;
    detailsDragActive = false;

    const target = event.currentTarget as HTMLElement | null;
    if (target?.hasPointerCapture(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }

    const releaseVelocity = Math.max(-900, Math.min(900, detailsDragVelocity));
    if (Math.abs(releaseVelocity) > 24) {
      detailsSpinPaused = false;
      detailsBoostVelocity = releaseVelocity;
      startDetailsInertia();
    } else {
      scheduleDetailsSpinResume();
    }
  }

  function openEditConfirm(item: MediaItem, fromDetails = false) {
    if (fromDetails) {
      detailsEditMode = true;
      startEditItem(item);
      return;
    }
    confirmMode = 'edit';
    confirmItem = item;
    confirmOpen = true;
  }

  function openDeleteConfirm(item: MediaItem) {
    confirmMode = 'delete';
    confirmItem = item;
    confirmOpen = true;
  }

  function closeConfirm() {
    confirmOpen = false;
    confirmItem = null;
  }

  async function confirmAction() {
    if (!confirmItem) return;

    const item = confirmItem;
    const mode = confirmMode;
    closeConfirm();

    if (mode === 'edit') {
      startEditItem(item);
      return;
    }

    await deleteAdminItem(item);
  }

  async function toggleLibrarySearch() {
    if (librarySearchOpen && !librarySearch.trim()) {
      librarySearchOpen = false;
      return;
    }
    librarySearchOpen = true;
    await tick();
    librarySearchInput?.focus();
  }

  function collapseSearchIfEmpty() {
    if (!librarySearch.trim()) {
      librarySearchOpen = false;
    }
  }

  function showBootSoundIndicator(isMuted: boolean) {
    bootSoundIndicator = isMuted ? '🔇 Muted' : '🔊 Sound On';
    bootSoundIndicatorVisible = true;

    if (bootSoundIndicatorTimeout) {
      clearTimeout(bootSoundIndicatorTimeout);
    }

    bootSoundIndicatorTimeout = setTimeout(() => {
      bootSoundIndicatorVisible = false;
    }, 900);
  }

  function setBootMuted(isMuted: boolean, showIndicator = false) {
    bootMuted = isMuted;
    if (bootVideoRef) {
      bootVideoRef.defaultMuted = isMuted;
      bootVideoRef.muted = isMuted;
      if (!isMuted) {
        bootVideoRef.volume = 1;
      }
    }

    if (showIndicator) {
      showBootSoundIndicator(isMuted);
    }
  }

  function toggleBootMute() {
    setBootMuted(!bootMuted, true);
  }

  function handleBootScreenClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.boot-option')) return;
    toggleBootMute();
  }


  function emptyAdminForm(): AdminForm {
    return {
      id: null,
      title: '',
      category: 'Games',
      platform: 'PlayStation 2',
      genre: '',
      release_date: '',
      year_released: '',
      players: '',
      artist: '',
      cover_image: '',
      notes: '',
    };
  }

  function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function buildConsoleList() {
    const mediaNames = Array.from(
      new Set(
        allMedia
          .filter((item) => item.category === 'Games' && item.platform)
          .map((item) => item.platform as string),
      ),
    );
    const fallbackNames = fallbackConsoles.map((item) => item.name);
    const all = [...customSystems, ...mediaNames, ...fallbackNames];
    const source = Array.from(new Set(all));
    return source.map((name) => {
      const fallback = fallbackConsoles.find((item) => item.name === name);
      return {
        name,
        shortName: fallback?.shortName ?? name.slice(0, 3).toUpperCase(),
        logo: fallback?.logo ?? name.slice(0, 3).toUpperCase(),
        logoImage: fallback?.logoImage,
      };
    });
  }

  function pagedItems() {
    const start = page * itemsPerPage;
    return media.slice(start, start + itemsPerPage);
  }

  function setPage(nextPage: number) {
    page = Math.max(0, Math.min(totalPages - 1, nextPage));
    history.pushState(currentHistoryState(), '');
  }

  function handleIconMove(event: MouseEvent) {
    const target = event.currentTarget as HTMLElement | null;
    if (!target) return;
    const rect = target.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const nx = x / Math.max(rect.width, 1) - 0.5;
    const rotateY = Math.max(-25, Math.min(25, nx * 50));

    target.style.setProperty('--cursor-x', `${x}px`);
    target.style.setProperty('--cursor-y', `${y}px`);
    target.style.setProperty('--ry', `${rotateY}deg`);
    target.classList.add('cursor-following');
  }

  function clearIconFollow(event: MouseEvent) {
    const target = event.currentTarget as HTMLElement | null;
    if (!target) return;
    target.classList.remove('cursor-following');
    target.style.removeProperty('--ry');
  }

  function itemDelay(index: number) {
    const column = index % 5;
    const row = Math.floor(index / 5);
    return row * 150 + column * 80;
  }

  function consoleDelay(index: number) {
    const column = index % 5;
    const row = Math.floor(index / 5);
    return row * 150 + column * 85;
  }

  function iconInitials(title: string) {
    const pieces = title.split(' ').filter(Boolean).slice(0, 3);
    return pieces.map((piece) => piece[0]).join('').toUpperCase() || 'PS';
  }

  function releaseDate(item: MediaItem) {
    if (item.release_date) {
      const parts = item.release_date.split('-');
      if (parts.length === 3) {
        const [year, month, day] = parts;
        return `${month}/${day}/${year} 12:00:00 AM`;
      }
      return item.release_date;
    }
    if (item.year_released) return `01/01/${item.year_released} 12:00:00 AM`;
    return 'Unknown release date';
  }

  function detailText(item: MediaItem) {
    if (item.category === 'Music') {
      return `${item.genre} | ${item.notes?.trim() || 'No description available.'}`;
    }
    const players = item.players ? `${item.players} player${item.players === 1 ? '' : 's'}` : 'Players unknown';
    return `${item.genre} | ${players} | ${item.notes?.trim() || 'No description available.'}`;
  }

  function buildAdminGenreOptions(formCategory: Category, mediaItems: MediaItem[]) {
    const gameGenres = [
      'Action',
      'Action-Adventure',
      'Adventure',
      'Fighting',
      'Horror',
      'Platformer',
      'Puzzle',
      'Racing',
      'RPG',
      'Shooter',
      'Simulation',
      'Sports',
      'Strategy',
    ];
    const musicGenres = [
      'Electronic',
      'Hip-Hop',
      'Jazz',
      'Pop',
      'R&B',
      'Rock',
      'Soundtrack',
    ];
    const defaults = formCategory === 'Games' ? gameGenres : musicGenres;
    const existing = mediaItems
      .filter((item) => item.category === formCategory)
      .map((item) => item.genre)
      .filter(Boolean);
    return Array.from(new Set([...defaults, ...existing])).sort();
  }

  function mediaHeaders() {
    return {
      Authorization: `Bearer ${adminToken}`,
      'Content-Type': 'application/json',
    };
  }

  function buildAdminFilteredList() {
    let filtered = allMedia;

    if (adminSearchQuery.trim()) {
      const q = adminSearchQuery.toLowerCase();
      filtered = filtered.filter((item) => item.title.toLowerCase().includes(q));
    }

    if (adminSearchCategory !== 'All') {
      filtered = filtered.filter((item) => item.category === adminSearchCategory);
    }

    if (adminSearchPlatform !== 'All') {
      filtered = filtered.filter((item) => item.platform === adminSearchPlatform);
    }

    return filtered;
  }

  function getAdminListPage() {
    const start = adminListPage * adminListItemsPerPage;
    return adminFilteredMedia.slice(start, start + adminListItemsPerPage);
  }

  function currentHistoryState(): HistoryState {
    return {
      stage,
      category,
      console: selectedConsole,
      itemId: selectedItem?.id ?? null,
      page,
    };
  }

  async function fadeBootAudio(duration: number) {
    const video = bootVideoRef;
    if (!video || video.paused) return;
    const start = video.volume || 1;
    const steps = 16;
    for (let i = 0; i < steps; i += 1) {
      const progress = (i + 1) / steps;
      video.volume = Math.max(0, start * (1 - progress));
      await sleep(duration / steps);
    }
    video.volume = 0;
  }

  async function fadeInBootAudio(duration: number) {
    const video = bootVideoRef;
    if (!video || video.paused || video.muted) return;
    const start = Math.max(0, video.volume);
    const steps = 16;
    for (let i = 0; i < steps; i += 1) {
      const progress = (i + 1) / steps;
      video.volume = Math.min(1, start + ((1 - start) * progress));
      await sleep(duration / steps);
    }
    video.volume = 1;
  }

  async function returnToBootSmooth() {
    if (isTransitioning) return;

    isTransitioning = true;
    transitionToBlack = true;
    transitionOverlay = true;
    transitionOpacity = 0;

    await tick();
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    transitionOpacity = 1;
    await sleep(1000);

    stage = 'boot';
    category = null;
    selectedConsole = null;
    selectedItem = null;
    page = 0;
    bootStartAt = 0;
    bootResumeAtSix = true;
    bootTextVisible = false;
    bootStarted = false;
    bootAudioFadeInMs = 1000;

    const newState: HistoryState = { stage: 'boot', category: null, console: null, itemId: null, page: 0 };
    history.pushState(newState, '');

    await tick();
    transitionOverlay = false;
    transitionOpacity = 0;
    transitionToBlack = false;
    isTransitioning = false;

    void queueBootStart();
  }

  async function transitionTo(next: HistoryState, options: { fadeMs?: number; audioFadeMs?: number; zoomConsole?: string | null; zoomItemId?: number | null; replace?: boolean } = {}) {
    const fadeMs = options.fadeMs ?? ZOOM_TRANSITION_MS;
    const half = Math.max(120, Math.floor(fadeMs / 2));

    isTransitioning = true;
    transitionOverlay = true;
    transitionOpacity = 1;
    launchConsoleName = options.zoomConsole ?? null;
    launchItemId = options.zoomItemId ?? null;

    if (options.audioFadeMs && options.audioFadeMs > 0) {
      void fadeBootAudio(options.audioFadeMs);
    }

    await tick();
    await sleep(half);

    if (options.replace) {
      history.replaceState(next, '');
    } else {
      history.pushState(next, '');
    }

    stage = next.stage;
    category = next.category;
    selectedConsole = next.console;
    selectedItem = next.itemId ? allMedia.find((item) => item.id === next.itemId) ?? null : null;
    page = next.page;
    bootTextVisible = stage !== 'boot';

    await tick();
    await sleep(half);

    transitionOpacity = 0;
    await sleep(120);

    transitionOverlay = false;
    isTransitioning = false;
    launchConsoleName = null;
    launchItemId = null;
  }

  async function loadAllMedia() {
    const response = await fetch('/api/media');
    if (!response.ok) return;
    allMedia = await response.json();
  }

  async function loadMedia(nextCategory: Category | null = category, nextConsole: string | null = selectedConsole) {
    const requestId = ++mediaLoadRequestId;

    if (!nextCategory) {
      libraryLoading = false;
      media = [];
      return;
    }

    libraryLoading = true;

    // Clear stale library items immediately so the previous console does not flash.
    media = [];
    brokenCoverIds = new Set();

    const params = new URLSearchParams();
    params.set('category', nextCategory);
    if (nextCategory === 'Games' && nextConsole) {
      params.set('platform', nextConsole);
    }

    const response = await fetch(`/api/media?${params.toString()}`);
    if (requestId !== mediaLoadRequestId) return;

    if (!response.ok) {
      libraryLoading = false;
      media = [];
      return;
    }

    const data = await response.json();
    if (requestId !== mediaLoadRequestId) return;

    media = data;
    libraryLoading = false;
    page = 0;
    librarySearch = '';
    librarySearchOpen = false;
    libraryPlayersFilter = null;
    playersDropdownOpen = false;
  }

  function unlockBootAudio() {
    if (!bootVideoRef) return;
    setBootMuted(false);
    if (bootVideoRef.paused) {
      void bootVideoRef.play().catch(() => {
        // Ignore autoplay restrictions until the next user gesture.
      });
    }
  }

  async function startBoot() {
    if (!bootVideoRef || bootStarted) return;
    bootStarted = true;

    const video = bootVideoRef;
    try {
      bootError = false;
      if (video.readyState < 1) {
        await new Promise<void>((resolve) => {
          video.addEventListener('loadedmetadata', () => resolve(), { once: true });
        });
      }

      const startAt = Math.max(0, bootResumeAtSix ? BOOT_SKIP_TIME : bootStartAt);
      video.currentTime = Math.max(video.currentTime, startAt);
      const shouldFadeAudioIn = bootAudioFadeInMs > 0;
      video.volume = shouldFadeAudioIn ? 0 : 1;

      // Start muted by default. First click unmutes.
      setBootMuted(true);
      try {
        await video.play();
      } catch {
        setBootMuted(true);
        await video.play();
      }

      if (shouldFadeAudioIn && !video.muted) {
        void fadeInBootAudio(bootAudioFadeInMs);
      }

      bootAudioFadeInMs = 0;

      bootResumeAtSix = false;
    } catch {
      bootError = true;
      bootTextVisible = true;
      bootStarted = false;
    }
  }

  function skipBootIntro() {
    if (stage !== 'boot' || bootTextVisible) return;

    unlockBootAudio();
    bootResumeAtSix = true;
    bootStartAt = BOOT_SKIP_TIME;

    if (!bootVideoRef) {
      bootTextVisible = true;
      return;
    }

    bootVideoRef.currentTime = BOOT_SKIP_TIME;
    bootTextVisible = true;

    if (bootVideoRef.paused) {
      void bootVideoRef.play().catch(() => {
        bootError = true;
        bootTextVisible = true;
      });
    }
  }

  async function queueBootStart() {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await tick();
      if (bootVideoRef) {
        await startBoot();
        return;
      }
      await sleep(25);
    }
  }

  async function handleBootPick(categoryName: Category) {
    bootHover = categoryName;
    unlockBootAudio();

    if (categoryName === 'Games') {
      await transitionTo({ stage: 'console', category: 'Games', console: null, itemId: null, page: 0 }, { fadeMs: ZOOM_TRANSITION_MS, audioFadeMs: ZOOM_TRANSITION_MS });
      bootStartAt = 0;
      return;
    }

    media = [];
    void loadMedia('Music', null);
    await transitionTo({ stage: 'library', category: 'Music', console: null, itemId: null, page: 0 }, { fadeMs: ZOOM_TRANSITION_MS, audioFadeMs: ZOOM_TRANSITION_MS });
    bootStartAt = 0;
  }

  function onConsoleSelect(consoleName: string) {
    launchConsoleName = consoleName;

    // Start loading next console's library during transition.
    void loadMedia('Games', consoleName);

    void transitionTo(
      { stage: 'library', category: 'Games', console: consoleName, itemId: null, page: 0 },
      { fadeMs: 1050, audioFadeMs: 700, zoomConsole: consoleName },
    );
  }

  function openItem(item: MediaItem) {
    launchItemId = item.id;
    void transitionTo(
      { stage: 'details', category, console: selectedConsole, itemId: item.id, page },
      { fadeMs: 900, zoomItemId: item.id },
    );
  }

  function closeDetails() {
    closeConfirm();
    if (detailsInertiaFrame !== null) {
      cancelAnimationFrame(detailsInertiaFrame);
      detailsInertiaFrame = null;
    }
    detailsBoostVelocity = 0;
    if (detailsSpinPauseTimeout) {
      clearTimeout(detailsSpinPauseTimeout);
      detailsSpinPauseTimeout = null;
    }
    backAction();
  }

  function backAction() {
    if (stage === 'console') {
      void returnToBootSmooth();
      return;
    }

    if (stage === 'library' && category === 'Music') {
      void returnToBootSmooth();
      return;
    }

    if (stage === 'library' && category === 'Games') {
      // Go directly back to console select, skipping any pagination history entries
      void transitionTo(
        { stage: 'console', category: 'Games', console: null, itemId: null, page: 0 },
        { fadeMs: ZOOM_TRANSITION_MS },
      );
      return;
    }

    if (stage === 'details') {
      // Go back to the library page for this console
      void transitionTo(
        { stage: 'library', category, console: selectedConsole, itemId: null, page },
        { fadeMs: ZOOM_TRANSITION_MS, replace: true },
      );
      return;
    }

    history.back();
  }

  function resetAdminForm() {
    adminEditingId = null;
    adminForm = emptyAdminForm();
  }

  function persistCustomSystems() {
    localStorage.setItem('ps2-owned-systems', JSON.stringify(customSystems));
  }

  function addCustomSystem() {
    systemError = '';
    const name = newSystemName.trim();
    if (!name) {
      systemError = 'System name is required.';
      return;
    }
    const exists = customSystems.some((item) => item.toLowerCase() === name.toLowerCase());
    if (exists) {
      systemError = 'System already exists.';
      return;
    }
    customSystems = [...customSystems, name];
    persistCustomSystems();
    newSystemName = '';
  }

  function removeCustomSystem(systemName: string) {
    customSystems = customSystems.filter((item) => item !== systemName);
    persistCustomSystems();
    if (selectedConsole === systemName) {
      selectedConsole = null;
    }
  }

  function startAddItem() {
    adminOpen = true;
    detailsEditMode = false;
    resetAdminForm();
  }

  function toggleAdminPanel() {
    if (!adminOpen && category) {
      adminSearchCategory = category as Category;
      adminSearchPlatform = (category === 'Games' && selectedConsole) ? selectedConsole : 'All';
      adminListPage = 0;
    }
    adminOpen = !adminOpen;
  }

  function startEditItem(item: MediaItem) {
    adminOpen = true;
    adminEditingId = item.id;
    adminForm = {
      id: item.id,
      title: item.title,
      category: item.category === 'Music' ? 'Music' : 'Games',
      platform: item.platform ?? '',
      genre: item.genre,
      release_date: item.release_date ?? (item.year_released ? `${item.year_released}-01-01` : ''),
      year_released: item.year_released ? String(item.year_released) : '',
      players: item.players ? String(item.players) : '',
      artist: item.artist ?? '',
      cover_image: item.cover_image ?? '',
      notes: item.notes ?? '',
    };
  }

  async function adminLogin() {
    adminBusy = true;
    adminError = '';
    adminMessage = '';
    try {
      const response = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: adminPassword }),
      });
      if (!response.ok) {
        adminError = 'Incorrect password.';
        return;
      }
      const data = await response.json();
      adminToken = data.token;
      localStorage.setItem('ps2-admin-token', adminToken);
      adminPassword = '';
      adminMessage = 'Admin mode enabled.';
      await loadAllMedia();
    } catch {
      adminError = 'Admin login failed.';
    } finally {
      adminBusy = false;
    }
  }

  async function adminLogout() {
    try {
      await fetch('/api/admin/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${adminToken}` },
      });
    } catch {
      // ignore
    }
    adminToken = '';
    localStorage.removeItem('ps2-admin-token');
    adminOpen = false;
    adminMessage = '';
    adminError = '';
    resetAdminForm();
  }

  async function saveAdminItem() {
    adminError = '';
    adminMessage = '';
    if (!adminToken) {
      adminError = 'Login required.';
      return;
    }
    if (!adminForm.title.trim() || !adminForm.genre.trim()) {
      adminError = 'Title and genre are required.';
      return;
    }

    adminBusy = true;
    const releaseDate = adminForm.release_date ? adminForm.release_date.trim() : '';
    const releaseYear = releaseDate ? Number(releaseDate.slice(0, 4)) : (adminForm.year_released ? Number(adminForm.year_released) : null);
    const payload = {
      title: adminForm.title.trim(),
      category: adminForm.category,
      platform: adminForm.platform.trim() || null,
      genre: adminForm.genre.trim(),
      release_date: releaseDate || null,
      year_released: releaseYear,
      players: adminForm.category === 'Games' && adminForm.players ? Number(adminForm.players) : null,
      artist: adminForm.category === 'Music' ? adminForm.artist.trim() || null : null,
      publisher: null,
      format: null,
      region: null,
      cover_image: adminForm.cover_image.trim() || null,
      tags: null,
      notes: adminForm.notes.trim() || null,
    };

    try {
      const response = await fetch(adminForm.id ? `/api/media/${adminForm.id}` : '/api/media', {
        method: adminForm.id ? 'PUT' : 'POST',
        headers: mediaHeaders(),
        body: JSON.stringify(payload),
      });
      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        adminError = 'Session expired. Log in again.';
        return;
      }
      if (!response.ok) {
        adminError = 'Could not save item.';
        return;
      }
      adminMessage = adminForm.id ? 'Item updated.' : 'Item added.';
      const wasDetailsEdit = detailsEditMode;
      const savedId = adminForm.id;
      resetAdminForm();
      detailsEditMode = false;
      await Promise.all([loadAllMedia(), loadMedia()]);
      if (wasDetailsEdit) {
        adminOpen = false;
        if (savedId !== null) {
          selectedItem = allMedia.find((i) => i.id === savedId) ?? selectedItem;
        }
      }
    } catch {
      adminError = 'Could not save item.';
    } finally {
      adminBusy = false;
    }
  }

  async function deleteAdminItem(item: MediaItem) {
    adminError = '';
    adminMessage = '';
    adminBusy = true;
    try {
      const response = await fetch(`/api/media/${item.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${adminToken}` },
      });
      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        adminError = 'Session expired. Log in again.';
        return;
      }
      if (!response.ok) {
        adminError = 'Could not delete item.';
        return;
      }
      if (selectedItem?.id === item.id) {
        selectedItem = null;
      }
      adminMessage = 'Item deleted.';
      await Promise.all([loadAllMedia(), loadMedia()]);
    } catch {
      adminError = 'Could not delete item.';
    } finally {
      adminBusy = false;
    }
  }

  function hideLogoOnError(e: Event) {
    const img = e.currentTarget as HTMLImageElement;
    if (img) img.hidden = true;
  }

  function markCoverBroken(itemId: number) {
    const next = new Set(brokenCoverIds);
    next.add(itemId);
    brokenCoverIds = next;
  }

  function handleGlobalBootKeydown(event: KeyboardEvent) {
    if (event.code !== 'Space') return;
    if (stage !== 'boot' || bootTextVisible) return;
    event.preventDefault();
    unlockBootAudio();
    skipBootIntro();
  }

  onMount(async () => {
    const savedToken = localStorage.getItem('ps2-admin-token');
    if (savedToken) {
      adminToken = savedToken;
    }
    const savedSystems = localStorage.getItem('ps2-owned-systems');
    if (savedSystems) {
      try {
        const parsed = JSON.parse(savedSystems);
        if (Array.isArray(parsed)) {
          customSystems = parsed.filter((item) => typeof item === 'string' && item.trim());
        }
      } catch {
        customSystems = [];
      }
    }

    await loadAllMedia();
    history.replaceState(currentHistoryState(), '');
    window.addEventListener('popstate', handlePopState);
    window.addEventListener('keydown', handleGlobalBootKeydown);
    void queueBootStart();

    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('keydown', handleGlobalBootKeydown);
      if (bootSoundIndicatorTimeout) {
        clearTimeout(bootSoundIndicatorTimeout);
      }
      if (detailsInertiaFrame !== null) {
        cancelAnimationFrame(detailsInertiaFrame);
      }
      if (detailsSpinPauseTimeout) {
        clearTimeout(detailsSpinPauseTimeout);
      }
    };
  });

  function handlePopState(event: PopStateEvent) {
    const state = event.state as HistoryState | null;
    if (!state) return;

    const previousStage = stage;
    stage = state.stage;
    category = state.category;
    selectedConsole = state.console;
    selectedItem = state.itemId ? allMedia.find((item) => item.id === state.itemId) ?? null : null;
    page = state.page;

    transitionOverlay = false;
    transitionOpacity = 0;
    isTransitioning = false;
    transitionToBlack = false;
    launchConsoleName = null;
    launchItemId = null;
    bootTextVisible = stage !== 'boot';

    if (stage === 'library') {
      void loadMedia();
    }

    if (stage === 'boot') {
      bootStarted = false;
      bootStartAt = previousStage === 'boot' ? 0 : BOOT_SKIP_TIME;
      bootResumeAtSix = previousStage !== 'boot';
      bootTextVisible = false;
      void queueBootStart();
    }
  }
</script>

{#if stage === 'boot'}
  <div
    class="boot-screen"
    role="button"
    tabindex="0"
    aria-label="Toggle boot audio mute"
    on:click={handleBootScreenClick}
    on:keydown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleBootMute();
      }
    }}
  >
    {#if !bootError}
      <video
        bind:this={bootVideoRef}
        class="boot-video"
        src="/suggestions/ps2-intro.mp4"
        preload="auto"
        playsinline
        on:loadedmetadata={() => {
          if (bootVideoRef) {
            bootVideoRef.currentTime = Math.max(0, bootResumeAtSix ? BOOT_SKIP_TIME : bootStartAt);
          }
        }}
        on:timeupdate={() => {
          if (!bootVideoRef) return;
          if (bootResumeAtSix) {
            if (bootVideoRef.currentTime >= BOOT_SKIP_TIME) {
              bootTextVisible = true;
            }
          } else {
            if (bootVideoRef.currentTime >= 9) {
              bootTextVisible = true;
            }
          }
        }}
        on:ended={() => (bootTextVisible = true)}
        on:error={() => {
          bootError = true;
          bootTextVisible = true;
        }}
      />
    {/if}

    <div class="boot-vignette"></div>
    {#if transitionOverlay}
      <div class="transition-overlay" class:to-black={transitionToBlack} style="opacity: {transitionOpacity};" aria-hidden="true"></div>
    {/if}

    {#if bootSoundIndicatorVisible}
      <div class="boot-sound-indicator" transition:fade={{ duration: 260 }}>{bootSoundIndicator}</div>
    {/if}

    {#if !bootTextVisible}
      <div class="boot-skip-hint" transition:fade={{ duration: 600 }}>
        <div>Press spacebar to skip intro</div>
        <div class="boot-mute-hint">{bootMuted ? 'Click to enable audio' : 'Click to mute'}</div>
      </div>
    {/if}

    {#if bootTextVisible}
      <div class="boot-options" transition:fade={{ duration: 500 }}>
        <button type="button" class="boot-option" on:mouseenter={() => (bootHover = 'Games')} on:click={() => handleBootPick('Games')}>
          <span class="boot-option-main">Games</span>
        </button>
        <button type="button" class="boot-option" on:mouseenter={() => (bootHover = 'Music')} on:click={() => handleBootPick('Music')}>
          <span class="boot-option-main">Music</span>
        </button>
      </div>
    {/if}

    <div class="footer">
      <p>&copy; 2026 ALEX PRITT</p>
    </div>
  </div>
{:else}
  <div class="ps2-screen" class:transitioning={isTransitioning}>
    <div class="screen-fog"></div>
    {#if transitionOverlay}
      <div class="transition-overlay" class:to-black={transitionToBlack} style="opacity: {transitionOpacity};" aria-hidden="true"></div>
    {/if}

    {#if stage === 'console'}
      <section class="console-screen">
        <div class="hud-left">{consoleTitle}</div>
        <div class="hud-subheader">{consoleLibraryCountLabel}</div>
        <div class="console-grid">
          {#each availableConsoles as console, index}
            <button
              type="button"
              class="console-card"
              class:launching={launchConsoleName === console.name}
              style="--delay: {consoleDelay(index)}ms;"
              on:pointerenter={() => (hoveredConsole = console.name)}
              on:mousemove={handleIconMove}
              on:pointerleave={(event) => {
                hoveredConsole = null;
                clearIconFollow(event);
              }}
              on:click={() => onConsoleSelect(console.name)}
              aria-label={`Select ${console.name}`}
            >
              <span class="hover-burst"></span>
              {#if console.logoImage}
                <img
                  src={console.logoImage}
                  alt={console.name}
                  class="console-logo-img"
                  draggable="false"
                  on:error={hideLogoOnError}
                />
              {:else}
                <span class="console-icon">{console.logo}</span>
                <span class="console-name">{console.shortName}</span>
              {/if}
              <span class="console-title">{console.name}</span>
            </button>
          {/each}
        </div>
      </section>
    {/if}

    {#if stage === 'library' || stage === 'details'}
      <section class="library-screen">
        <div class="library-hud">
          <div class="library-hud-left">
            {#if category === 'Games' && selectedLibraryConsole?.logoImage}
              <img
                src={selectedLibraryConsole.logoImage}
                alt={libraryHeaderLeft}
                class="library-console-logo"
                draggable="false"
              />
            {:else}
              <div>{libraryHeaderLeft}</div>
            {/if}
          </div>

          {#if stage === 'library'}
            <div class="library-toolbar">
              <div class="library-search-shell" class:is-open={librarySearchOpen}>
                <button
                  type="button"
                  class="library-search-toggle"
                  on:click={toggleLibrarySearch}
                  aria-label="Toggle search"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" stroke-width="2"></circle>
                    <line x1="15.5" y1="15.5" x2="21" y2="21" stroke="currentColor" stroke-width="2" stroke-linecap="round"></line>
                  </svg>
                </button>
                <input
                  bind:this={librarySearchInput}
                  type="search"
                  class="library-search"
                  class:is-open={librarySearchOpen}
                  placeholder="Search title, genre, year..."
                  bind:value={librarySearch}
                  on:input={() => (page = 0)}
                  on:blur={collapseSearchIfEmpty}
                  on:keydown={(event) => {
                    if (event.key === 'Escape') {
                      if (!librarySearch.trim()) librarySearchOpen = false;
                      playersDropdownOpen = false;
                    }
                  }}
                  autocomplete="off"
                  spellcheck="false"
                />
              </div>
              {#if category === 'Games'}
                <div class="players-filter">
                  <button
                    type="button"
                    class="players-filter-btn"
                    class:is-active={libraryPlayersFilter !== null}
                    on:click={() => (playersDropdownOpen = !playersDropdownOpen)}
                    aria-label="Filter by number of players"
                  >
                    <span class="players-filter-inner">
                      {#if libraryPlayersFilter !== null}
                        <span class="players-filter-num">{libraryPlayersFilter}</span>
                      {/if}
                      <img
                        src="/controller-icon.svg"
                        alt="Players"
                        class="controller-icon"
                        draggable="false"
                      />
                    </span>
                    <span class="players-filter-caret">▾</span>
                  </button>
                  {#if playersDropdownOpen}
                    <button
                      class="players-dropdown-backdrop"
                      type="button"
                      aria-label="Close dropdown"
                      on:click={() => (playersDropdownOpen = false)}
                    ></button>
                    <div class="players-dropdown" role="menu">
                      <button type="button" role="menuitem"
                        class:selected={libraryPlayersFilter === null}
                        on:click={() => { libraryPlayersFilter = null; playersDropdownOpen = false; page = 0; }}
                      >All</button>
                      {#each availablePlayerCounts as n}
                        <button type="button" role="menuitem"
                          class:selected={libraryPlayersFilter === n}
                          on:click={() => { libraryPlayersFilter = n; playersDropdownOpen = false; page = 0; }}
                        >{n}P</button>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}

          {#if libraryHeaderRight}
            <div class="library-hud-right">{libraryHeaderRight}</div>
          {/if}
        </div>

        <div class="library-grid">
          {#key libraryGridKey}
            {#if showEmptyGamesState}
              <div class="library-empty-state" aria-live="polite">
                <div class="memory-card-wrap" aria-hidden="true">
                  <img src="/memory-card-logo.svg" alt="" class="memory-card-logo" draggable="false" />
                  <span class="memory-card-question">?</span>
                </div>
                <p class="library-empty-text">No games found on memory card...</p>
              </div>
            {:else}
              {#each filteredMedia.slice(page * itemsPerPage, page * itemsPerPage + itemsPerPage) as item, index}
                <button
                  type="button"
                  class="library-card"
                  class:launching={launchItemId === item.id}
                  class:library-card--game={item.category === 'Games'}
                  class:library-card--music={item.category === 'Music'}
                  style="--delay: {itemDelay(index)}ms;"
                  on:mouseenter={() => (hoveredItemId = item.id)}
                  on:mousemove={handleIconMove}
                  on:mouseleave={(event) => {
                    hoveredItemId = null;
                    clearIconFollow(event);
                  }}
                  on:click={() => openItem(item)}
                  aria-label={`Open ${item.title}`}
                >
                  <span class="hover-burst"></span>
                  {#if item.category === 'Music'}
                    <span class="vinyl-wrap" aria-hidden="true">
                      <span class="vinyl-record"></span>
                      <span class="vinyl-sleeve">
                        {#if item.cover_image && !brokenCoverIds.has(item.id)}
                          <img src={item.cover_image} alt={item.title} class="library-art" loading="lazy" on:error={() => markCoverBroken(item.id)} />
                        {:else}
                          <span class="library-fallback">{iconInitials(item.title)}</span>
                        {/if}
                      </span>
                    </span>
                  {:else}
                    <span class="disc-case" aria-hidden="true">
                      <span class="disc-case-spine"></span>
                      <span class="disc-case-front">
                        {#if item.cover_image && !brokenCoverIds.has(item.id)}
                          <img src={item.cover_image} alt={item.title} class="library-art" loading="lazy" on:error={() => markCoverBroken(item.id)} />
                        {:else}
                          <span class="library-fallback">{iconInitials(item.title)}</span>
                        {/if}
                      </span>
                      <span class="disc-case-disc"></span>
                    </span>
                  {/if}
                  <span class="library-title">{item.title}</span>
                </button>
              {/each}
            {/if}
          {/key}
        </div>

        {#if filteredTotalPages > 1}
          <div class="pager">
            <button type="button" on:click={() => setPage(page - 1)} disabled={page === 0}>Back</button>
            <div class="pager-info">Page {page + 1} / {filteredTotalPages}</div>
            <button type="button" on:click={() => setPage(page + 1)} disabled={page >= filteredTotalPages - 1}>Next</button>
          </div>
        {/if}
      </section>
    {/if}

    {#if stage === 'details' && selectedItem}
      <button
        type="button"
        class="details-overlay"
        aria-label="Close details"
        on:click={closeDetails}
      ></button>

      <section class="details-screen">
        <div class="details-left">
          <div class="details-rotator-control" style="--details-manual-ry: {detailsManualRotateY}deg;">
            <button
              type="button"
              class="details-rotator"
              class:spin-paused={detailsSpinPaused || detailsDragActive}
              aria-label="Rotate selected icon"
              on:dragstart|preventDefault
              on:pointerdown={beginDetailsRotate}
              on:pointermove={trackDetailsRotate}
              on:pointerup={endDetailsRotate}
              on:pointercancel={endDetailsRotate}
              on:keydown={(event) => {
                if (event.key === 'ArrowLeft') {
                  event.preventDefault();
                  detailsSpinPaused = true;
                  detailsManualRotateY -= 12;
                  scheduleDetailsSpinResume();
                } else if (event.key === 'ArrowRight') {
                  event.preventDefault();
                  detailsSpinPaused = true;
                  detailsManualRotateY += 12;
                  scheduleDetailsSpinResume();
                }
              }}
            >
              {#if selectedItem.category === 'Games'}
                <div class="details-game-disc">
                  {#if selectedItem.cover_image}
                    <img src={selectedItem.cover_image} alt={selectedItem.title} class="details-game-disc-art" draggable="false" />
                  {:else}
                    <div class="details-game-disc-fallback">{iconInitials(selectedItem.title)}</div>
                  {/if}
                  <span class="details-game-disc-hole"></span>
                  <span class="details-game-disc-shine"></span>
                </div>
              {:else}
                <span class="vinyl-wrap details-vinyl" aria-hidden="true">
                  <span class="vinyl-record"></span>
                  <span class="vinyl-sleeve">
                    {#if selectedItem.cover_image}
                      <img src={selectedItem.cover_image} alt={selectedItem.title} class="library-art" draggable="false" />
                    {:else}
                      <span class="library-fallback">{iconInitials(selectedItem.title)}</span>
                    {/if}
                  </span>
                </span>
              {/if}
            </button>
          </div>
        </div>

        <div class="details-right">
          <p class="details-line-1">{selectedItem.category === 'Music' ? (selectedItem.artist ?? 'Music') : (selectedConsole ?? '')}</p>
          <p class="details-line-2">{selectedItem.title}</p>
          <p class="details-line-3">{releaseDate(selectedItem)}</p>
          <p class="details-line-4">{detailText(selectedItem)}</p>
        </div>

        <div class="details-actions">
          <button type="button" class="details-back" on:click={closeDetails}>Back</button>
          {#if isAdmin}
            <div class="details-admin-actions">
              <button type="button" on:click={() => openEditConfirm(selectedItem, true)}>Edit</button>
              <button type="button" class="danger" on:click={() => openDeleteConfirm(selectedItem)}>Delete</button>
            </div>
          {/if}
        </div>
      </section>
    {/if}

    {#if confirmOpen && confirmItem}
      <div class="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <button type="button" class="confirm-backdrop" aria-label="Close confirmation" on:click={closeConfirm}></button>
        <div class="confirm-panel">
          <h3 id="confirm-title">{confirmMode === 'delete' ? 'Delete Item?' : 'Edit Item?'}</h3>
          <p>
            {#if confirmMode === 'delete'}
              Delete "{confirmItem.title}" from the library? This cannot be undone.
            {:else}
              Open "{confirmItem.title}" in the editor?
            {/if}
          </p>
          <div class="confirm-actions">
            <button type="button" class="ghost" on:click={closeConfirm}>Cancel</button>
            <button type="button" class:danger={confirmMode === 'delete'} on:click={confirmAction}>
              {confirmMode === 'delete' ? 'Delete' : 'Edit'}
            </button>
          </div>
        </div>
      </div>
    {/if}

    {#if stage !== 'details'}
      <button type="button" class="back-button" on:click={backAction}>Back</button>
    {/if}

    <button type="button" class="admin-launch" on:click={toggleAdminPanel}>{adminOpen ? 'Close' : 'Admin'}</button>

    {#if isAdmin}
      <div class="admin-toolbar">
        {#if stage === 'console'}
          <button type="button" on:click={() => (adminOpen = true)}>Add System</button>
        {/if}
        {#if stage === 'library'}
          <button type="button" on:click={startAddItem}>Add {category === 'Music' ? 'Album' : 'Game'}</button>
        {/if}
      </div>
    {/if}

    {#if adminOpen}
      <div class="admin-overlay" role="dialog" aria-modal="true">
        <button type="button" class="admin-backdrop" aria-label="Close admin panel" on:click={() => (adminOpen = false)}></button>
        <div class="admin-panel">
          <div class="admin-header">
            <h2>Admin Library Manager</h2>
            <button type="button" class="ghost" on:click={() => (adminOpen = false)}>Close</button>
          </div>

          {#if !isAdmin}
            <div class="admin-login">
              <label for="admin-password">Password</label>
              <input id="admin-password" type="password" bind:value={adminPassword} placeholder="Enter password..." />
              <button type="button" disabled={adminBusy} on:click={adminLogin}>Log In</button>
            </div>
          {:else}
            <div class="admin-actions">
              <button type="button" on:click={resetAdminForm}>New Item</button>
              <button type="button" class="ghost" on:click={adminLogout}>Log Out</button>
            </div>

            {#if stage === 'console'}
              <div class="systems-manager">
                <h3>Owned Systems</h3>
                <div class="systems-add-row">
                  <input type="text" bind:value={newSystemName} placeholder="Add system name" />
                  <button type="button" on:click={addCustomSystem}>Add System</button>
                </div>
                {#if systemError}
                  <p class="admin-error">{systemError}</p>
                {/if}
                <div class="systems-list">
                  {#each customSystems as systemName}
                    <div class="systems-row">
                      <span>{systemName}</span>
                      <button type="button" class="danger" on:click={() => removeCustomSystem(systemName)}>Remove</button>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            <form class="admin-form" on:submit|preventDefault={saveAdminItem}>
              <input type="text" bind:value={adminForm.title} placeholder="Title" required />
              <select bind:value={adminForm.category} on:change={() => (adminForm.genre = '')}>
                <option value="Games">Games</option>
                <option value="Music">Music</option>
              </select>
              {#if adminForm.category !== 'Music'}
                <select bind:value={adminForm.platform}>
                  <option value="">No console</option>
                  {#each adminConsoleOptions as consoleName}
                    <option value={consoleName}>{consoleName}</option>
                  {/each}
                </select>
              {/if}
              <select bind:value={adminForm.genre} required>
                <option value="" disabled>Select genre</option>
                {#each adminGenreOptions as genreName}
                  <option value={genreName}>{genreName}</option>
                {/each}
              </select>
              <input type="date" bind:value={adminForm.release_date} placeholder="Release date" />
              {#if adminForm.category === 'Games'}
                <select bind:value={adminForm.players}>
                  <option value="">Number of players</option>
                  {#each adminPlayerOptions as playerCount}
                    <option value={String(playerCount)}>{playerCount}</option>
                  {/each}
                </select>
              {/if}
              {#if adminForm.category === 'Music'}
                <input type="text" bind:value={adminForm.artist} placeholder="Artist" />
              {/if}
              <input type="text" bind:value={adminForm.cover_image} placeholder="Cover image URL" />
              <textarea bind:value={adminForm.notes} rows="3" placeholder="Short description"></textarea>
              <button type="submit" disabled={adminBusy}>{adminEditingId ? 'Save Changes' : 'Create Item'}</button>
            </form>

            <div class="admin-list-filters">
              <input type="text" bind:value={adminSearchQuery} placeholder="Search by title..." />
              <select bind:value={adminSearchCategory} on:change={() => (adminListPage = 0)}>
                <option value="All">All Categories</option>
                <option value="Games">Games</option>
                <option value="Music">Music</option>
              </select>
              {#if adminSearchCategory === 'Games'}
                <select bind:value={adminSearchPlatform} on:change={() => (adminListPage = 0)}>
                  <option value="All">All Platforms</option>
                  {#each adminConsoleOptions as platform}
                    <option value={platform}>{platform}</option>
                  {/each}
                </select>
              {/if}
            </div>

            <div class="admin-list">
              {#each adminPagedMedia as item}
                <div class="admin-row">
                  <div>
                    <strong>{item.title}</strong>
                    <small>{item.category} | {item.platform ?? item.format ?? 'Unknown'}</small>
                  </div>
                  <div class="admin-row-actions">
                    <button type="button" on:click={() => openEditConfirm(item)}>Edit</button>
                    <button type="button" class="danger" on:click={() => openDeleteConfirm(item)}>Delete</button>
                  </div>
                </div>
              {/each}
            </div>

            {#if adminListTotalPages > 1}
              <div class="admin-list-pager">
                <button type="button" on:click={() => (adminListPage = Math.max(0, adminListPage - 1))} disabled={adminListPage === 0}>Back</button>
                <div class="admin-pager-info">Page {adminListPage + 1} / {adminListTotalPages}</div>
                <button type="button" on:click={() => (adminListPage = Math.min(adminListTotalPages - 1, adminListPage + 1))} disabled={adminListPage >= adminListTotalPages - 1}>Next</button>
              </div>
            {/if}
          {/if}

          {#if adminError}
            <p class="admin-error">{adminError}</p>
          {/if}
          {#if adminMessage}
            <p class="admin-status">{adminMessage}</p>
          {/if}
        </div>
      </div>
    {/if}

    <div class="footer">
      <p>&copy; 2026 ALEX PRITT</p>
    </div>
  </div>
{/if}
