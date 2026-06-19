<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { MediaItem, EditableSystem } from './types';

  type Stage = 'boot' | 'console' | 'library' | 'details';
  type Category = 'Games' | 'Music';
  type GameRating = 'RP' | 'E' | 'E10+' | 'T' | 'M' | 'AO';

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
    rating: GameRating;
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
    { name: 'Nintendo 3DS', shortName: '3DS', logo: '3DS',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg' },
    { name: 'GameBoy', shortName: 'GB', logo: 'GB',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg' },
    { name: 'GameCube', shortName: 'GC', logo: 'GC',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg' },
    { name: 'Wii', shortName: 'Wii', logo: 'Wii',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg' },
    { name: 'Xbox', shortName: 'XBX', logo: 'XBX',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg' },
    { name: 'Xbox 360', shortName: '360', logo: '360',
      logoImage: 'https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg' },
  ];

  const gameRatingOptions: GameRating[] = ['RP', 'E', 'E10+', 'T', 'M', 'AO'];

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
  let hoveredConsoleFadeVisible = false;
  let hoveredConsoleFadeTimeout: ReturnType<typeof setTimeout> | null = null;

  let page = 0;
  let itemsPerPage = 15;
  let mediaLoadRequestId = 0;
  let libraryLoading = false;

  let adminToken = '';
  let adminOpen = false;
    let adminMode: 'hub' | 'systems' | 'library' = 'hub';
    let libraryAdminTab: 'games' | 'music' = 'games';
    let adminContextItem: MediaItem | null = null;
  let detailsEditMode = false;
  let adminEditingId: number | null = null;
  let adminPassword = '';
  let adminBusy = false;
  let adminError = '';
  let adminMessage = '';
  let adminForm: AdminForm = emptyAdminForm();
  let editableSystems: EditableSystem[] = [];
  let editingSystemId: string | null = null;
  let editingSystemName = '';
  let editingSystemIcon = '';
  let newSystemName = '';
  let newSystemIcon = '';
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
  $: availableConsoles = buildConsoleList(allMedia, editableSystems);
  $: activeConsole = availableConsoles[0] ?? fallbackConsoles[0];
  $: consoleHeaderOption = availableConsoles.find((item) => item.name === hoveredConsole) ?? null;
  $: if (hoveredConsole) {
    hoveredConsoleFadeVisible = true;
    if (hoveredConsoleFadeTimeout) clearTimeout(hoveredConsoleFadeTimeout);
    hoveredConsoleFadeTimeout = setTimeout(() => {
      hoveredConsole = null;
    }, 4000);
  }
  $: if (!hoveredConsole) {
    hoveredConsoleFadeVisible = false;
    if (hoveredConsoleFadeTimeout) {
      clearTimeout(hoveredConsoleFadeTimeout);
      hoveredConsoleFadeTimeout = null;
    }
  }
  $: totalGameLibraryCount = allMedia.filter((item) => item.category === 'Games').length;
  $: consoleLibraryCountLabel = `${totalGameLibraryCount} ${totalGameLibraryCount === 1 ? 'Game' : 'Games'} in Library`;
  $: hoveredConsoleGameCount = hoveredConsole
    ? allMedia.filter((item) => item.category === 'Games' && item.platform === hoveredConsole).length
    : null;
  $: consoleSubheaderLabel = hoveredConsole && hoveredConsoleGameCount !== null
    ? `${hoveredConsoleGameCount} ${hoveredConsoleGameCount === 1 ? 'Game' : 'Games'} in ${hoveredConsole} Library`
    : consoleLibraryCountLabel;
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
      rating: 'RP',
      players: '',
      artist: '',
      cover_image: '',
      notes: '',
    };
  }

  function normalizeConsoleKey(platform: string | null | undefined) {
    const value = (platform ?? '').toLowerCase();
    if (value === 'playstation 2') return 'ps2';
    if (value === 'playstation 3') return 'ps3';
    if (value === 'playstation 4') return 'ps4';
    if (value === 'nintendo ds') return 'nds';
    if (value === 'nintendo 3ds') return '3ds';
    if (value === 'gameboy') return 'gb';
    if (value === 'gamecube') return 'gamecube';
    if (value === 'wii') return 'wii';
    if (value === 'xbox') return 'xbox';
    if (value === 'xbox 360') return 'xbox360';
    return '';
  }

  function normalizeGameRating(rating: string | null | undefined): GameRating {
    const value = (rating ?? 'RP').toUpperCase().trim();
    const compact = value.replace(/\s+/g, ' ').trim();
    if (value === 'E') return 'E';
    if (value === 'E10' || value === 'E10+' || compact === 'EVERYONE 10+' || compact === 'EVERYONE10+') return 'E10+';
    if (compact === 'EVERYONE') return 'E';
    if (value === 'T') return 'T';
    if (compact === 'TEEN') return 'T';
    if (value === 'M') return 'M';
    if (compact === 'MATURE' || compact === 'MATURE 17+' || compact === 'MATURE17+') return 'M';
    if (value === 'AO') return 'AO';
    if (compact === 'ADULTS ONLY' || compact === 'ADULTS ONLY 18+' || compact === 'ADULTSONLY' || compact === 'ADULTSONLY18+') return 'AO';
    if (compact === 'RP' || compact === 'RATING PENDING' || compact === 'RATINGPENDING') return 'RP';
    return 'RP';
  }

  function isCartridgePlatform(platform: string | null | undefined) {
    const key = normalizeConsoleKey(platform);
    return key === 'nds' || key === '3ds' || key === 'gb';
  }

  function isSquareLibraryPlatform(platform: string | null | undefined) {
    const key = normalizeConsoleKey(platform);
    return key === 'nds' || key === '3ds' || key === 'gb';
  }

  function caseOverlayUrl(item: MediaItem) {
    const key = normalizeConsoleKey(item.platform);
    if (key === 'ps2') return '/suggestions/disc-case-overlays/ps2-case-overlay.svg';
    if (key === 'ps3') return '/suggestions/disc-case-overlays/ps3-case-overlay.png';
    if (key === 'ps4') return '/suggestions/disc-case-overlays/ps4-case-overlay.png';
    if (key === 'nds') return '/suggestions/disc-case-overlays/ds-case-overlay.png';
    if (key === '3ds') return '/suggestions/disc-case-overlays/3ds-case-overlay.png';
    if (key === 'gb') return '/suggestions/disc-case-overlays/gameboy-case-overlay.png';
    if (key === 'gamecube') return '/suggestions/disc-case-overlays/gamecube-case-overlay.svg';
    if (key === 'wii') return '/suggestions/disc-case-overlays/wii-case-overlay.svg';
    if (key === 'xbox') return '/suggestions/disc-case-overlays/xbox-case-overlay.svg';
    if (key === 'xbox360') return '/suggestions/disc-case-overlays/xbox360-case-overlay.svg';
    return null;
  }

  function discOverlayUrl(item: MediaItem) {
    const key = normalizeConsoleKey(item.platform);
    if (key === 'ps2') return '/suggestions/disc-overlays/ps2-disc-overlay.png';
    if (key === 'ps3') return '/suggestions/disc-overlays/ps3-disc-overlay.png';
    if (key === 'ps4') return '/suggestions/disc-overlays/ps4-disc-overlay.png';
    if (key === 'nds') return '/suggestions/disc-overlays/ds-cartridge-overlay.jpg';
    if (key === '3ds') return '/suggestions/disc-overlays/3ds-cartridge-overlay.png';
    if (key === 'gb') return '/suggestions/disc-overlays/gameboy-overlay.png';
    if (key === 'gamecube') return '/suggestions/disc-overlays/gamecube-disc-overlay.svg';
    if (key === 'wii') return '/suggestions/disc-overlays/wii-disc-overlay.svg';
    if (key === 'xbox') return '/suggestions/disc-overlays/xbox-disc-overlay.svg';
    if (key === 'xbox360') return '/suggestions/disc-overlays/xbox360-disc-overlay.svg';
    return null;
  }

  function cartridgeBackUrl(item: MediaItem) {
    const key = normalizeConsoleKey(item.platform);
    if (key === 'nds') return '/suggestions/disc-overlays/ds-cartridge-back.svg';
    if (key === '3ds') return '/suggestions/disc-overlays/3ds-cartridge-back.svg';
    if (key === 'gb') return '/suggestions/disc-overlays/gameboy-cartridge-back.svg';
    return '/suggestions/disc-overlays/generic-cartridge-back.svg';
  }

  function discBackUrl(item: MediaItem) {
    const key = normalizeConsoleKey(item.platform);
    if (key === 'ps2') return '/suggestions/disc-overlays/ps2-disc-back.svg';
    if (key === 'ps3') return '/suggestions/disc-overlays/ps3-disc-back.svg';
    if (key === 'ps4') return '/suggestions/disc-overlays/ps4-disc-back.svg';
    if (key === 'gamecube') return '/suggestions/disc-overlays/gamecube-disc-back.svg';
    if (key === 'wii') return '/suggestions/disc-overlays/wii-disc-back.svg';
    if (key === 'xbox') return '/suggestions/disc-overlays/xbox-disc-back.svg';
    if (key === 'xbox360') return '/suggestions/disc-overlays/xbox360-disc-back.svg';
    return '/suggestions/disc-overlays/realistic-disc-back.svg';
  }

  function libraryDiscImageUrl(item: MediaItem) {
    return item.cover_image ?? discOverlayUrl(item);
  }

  function detailBackImageUrl(item: MediaItem) {
    return isCartridgePlatform(item.platform) ? cartridgeBackUrl(item) : discBackUrl(item);
  }

  function discBackingClass(item: MediaItem) {
    const key = normalizeConsoleKey(item.platform);
    if (key === 'ps2') return 'disc-shell--ps2';
    if (key === 'ps3') return 'disc-shell--ps3';
    if (key === 'ps4') return 'disc-shell--ps4';
    if (key === 'gamecube') return 'disc-shell--gamecube';
    if (key === 'wii') return 'disc-shell--wii';
    if (key === 'xbox') return 'disc-shell--xbox';
    if (key === 'xbox360') return 'disc-shell--xbox360';
    if (key === 'nds') return 'disc-shell--nds';
    if (key === '3ds') return 'disc-shell--3ds';
    if (key === 'gb') return 'disc-shell--gb';
    return 'disc-shell--default';
  }

  function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function buildConsoleList(mediaItems: MediaItem[], systems: EditableSystem[]) {
    const mediaNames = Array.from(
      new Set(
        mediaItems
          .filter((item) => item.category === 'Games' && item.platform)
          .map((item) => item.platform as string),
      ),
    );
    const systemNames = systems.map((system) => system.name);
    const all = [...systemNames, ...mediaNames];
    const source = Array.from(new Set(all));
    return source.map((name) => {
      const system = systems.find((item) => item.name === name);
      if (system) {
        return {
          name: system.name,
          shortName: system.shortName,
          logo: system.logo,
          logoImage: system.logoImage,
        };
      }
      return {
        name,
        shortName: name.slice(0, 3).toUpperCase(),
        logo: name.slice(0, 3).toUpperCase(),
        logoImage: null,
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
    const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    if (item.release_date) {
      const parts = item.release_date.split('-');
      if (parts.length === 3) {
        const [year, month, day] = parts;
        const monthName = MONTHS[parseInt(month, 10) - 1] ?? month;
        return `Release Date: ${monthName} ${parseInt(day, 10)}, ${year}`;
      }
    }
    if (item.year_released) return `Release Date: ${item.year_released}`;
    return 'Release Date: Unknown';
  }

  function detailText(item: MediaItem) {
    if (item.category === 'Music') {
      return item.genre;
    }
    const players = item.players ? `${item.players} player${item.players === 1 ? '' : 's'}` : 'Players unknown';
    const rating = normalizeGameRating(item.rating);
    return `${item.genre} | ${players} | Rated ${rating}`;
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

  function loadSystemsFromStorage() {
    const stored = localStorage.getItem('ps2-editable-systems');
    if (stored) {
      try {
        editableSystems = JSON.parse(stored) as EditableSystem[];
      } catch {
        editableSystems = initializeDefaultSystems();
      }
    } else {
      editableSystems = initializeDefaultSystems();
    }
  }

  function initializeDefaultSystems(): EditableSystem[] {
    return [
      { id: 'ps2', name: 'PlayStation 2', shortName: 'PS2', logo: 'PS2',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg' },
      { id: 'ps3', name: 'PlayStation 3', shortName: 'PS3', logo: 'PS3',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg' },
      { id: 'ps4', name: 'PlayStation 4', shortName: 'PS4', logo: 'PS4',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg' },
      { id: 'nds', name: 'Nintendo DS', shortName: 'NDS', logo: 'NDS',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg' },
      { id: '3ds', name: 'Nintendo 3DS', shortName: '3DS', logo: '3DS',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg' },
      { id: 'gb', name: 'GameBoy', shortName: 'GB', logo: 'GB',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg' },
      { id: 'gc', name: 'GameCube', shortName: 'GC', logo: 'GC',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg' },
      { id: 'wii', name: 'Wii', shortName: 'Wii', logo: 'Wii',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg' },
      { id: 'xbox', name: 'Xbox', shortName: 'XBX', logo: 'XBX',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg' },
      { id: 'xbox360', name: 'Xbox 360', shortName: '360', logo: '360',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg' },
    ];
  }

  function persistSystems() {
    localStorage.setItem('ps2-editable-systems', JSON.stringify(editableSystems));
  }

  function addSystem() {
    systemError = '';
    const name = newSystemName.trim();
    if (!name) {
      systemError = 'System name is required.';
      return;
    }
    const exists = editableSystems.some((item) => item.name.toLowerCase() === name.toLowerCase());
    if (exists) {
      systemError = 'System already exists.';
      return;
    }
    const id = name.toLowerCase().replace(/\s+/g, '-');
    const newSystem: EditableSystem = {
      id,
      name,
      shortName: name.slice(0, 3).toUpperCase(),
      logo: name.slice(0, 3).toUpperCase(),
      logoImage: newSystemIcon.trim() || null,
    };
    editableSystems = [...editableSystems, newSystem];
    persistSystems();
    newSystemName = '';
    newSystemIcon = '';
  }

  function removeSystem(systemId: string) {
    editableSystems = editableSystems.filter((item) => item.id !== systemId);
    persistSystems();
    const removedSystem = editableSystems.find((s) => s.id === systemId);
    if (removedSystem && selectedConsole === removedSystem.name) {
      selectedConsole = null;
    }
  }

  function updateSystem(systemId: string, updates: Partial<EditableSystem>) {
    editableSystems = editableSystems.map((system) =>
      system.id === systemId ? { ...system, ...updates } : system,
    );
    persistSystems();
  }

  function startEditSystem(systemId: string) {
    const system = editableSystems.find((s) => s.id === systemId);
    if (system) {
      editingSystemId = systemId;
      editingSystemName = system.name;
      editingSystemIcon = system.logoImage || '';
    }
  }

  function cancelEditSystem() {
    editingSystemId = null;
    editingSystemName = '';
    editingSystemIcon = '';
  }

  function saveEditSystem() {
    if (!editingSystemId) return;
    const name = editingSystemName.trim();
    if (!name) {
      systemError = 'System name is required.';
      return;
    }
    const isDuplicate = editableSystems.some(
      (s) => s.id !== editingSystemId && s.name.toLowerCase() === name.toLowerCase(),
    );
    if (isDuplicate) {
      systemError = 'System name already in use.';
      return;
    }
    updateSystem(editingSystemId, {
      name,
      logoImage: editingSystemIcon.trim() || null,
    });
    cancelEditSystem();
    systemError = '';
  }

  function startAddItem() {
    adminOpen = true;
    adminMode = 'library';
    detailsEditMode = false;
    adminContextItem = null;
    libraryAdminTab = category === 'Music' ? 'music' : 'games';
    adminSearchCategory = category === 'Music' ? 'Music' : 'Games';
    adminSearchPlatform = category === 'Games' ? (selectedConsole ?? 'All') : 'All';
    adminListPage = 0;
    resetAdminForm();
    // Pre-populate form with current library context
    if (category === 'Music') {
      adminForm.category = 'Music';
      adminForm.platform = '';
    } else {
      adminForm.category = 'Games';
      adminForm.platform = selectedConsole ?? 'PlayStation 2';
    }
    // Open directly in create mode so adding can start immediately.
    adminEditingId = -1;
  }

  function toggleAdminPanel() {
    if (!adminOpen && category) {
      adminSearchCategory = category as Category;
      adminSearchPlatform = (category === 'Games' && selectedConsole) ? selectedConsole : 'All';
      adminListPage = 0;
    }
      adminMode = 'hub';
      adminContextItem = null;
    adminOpen = !adminOpen;
  }

  function openAdminMode(mode: 'systems' | 'library', tab?: 'games' | 'music', contextItem?: MediaItem) {
    adminOpen = true;
    adminMode = mode;
    if (tab) libraryAdminTab = tab;

    if (mode === 'library' && contextItem) {
      startEditItem(contextItem);
      return;
    }

    adminContextItem = null;
    resetAdminForm();
  }

    function backToAdminHub() {
      adminMode = 'hub';
      adminContextItem = null;
      adminEditingId = null;
    }

  function startEditItem(item: MediaItem) {
    adminOpen = true;
    adminMode = 'library';
    libraryAdminTab = item.category === 'Music' ? 'music' : 'games';
    adminContextItem = item;
    adminSearchCategory = item.category === 'Music' ? 'Music' : 'Games';
    adminSearchPlatform = item.category === 'Games' ? (item.platform ?? 'All') : 'All';
    adminListPage = 0;
    adminEditingId = item.id;
    adminForm = {
      id: item.id,
      title: item.title,
      category: item.category === 'Music' ? 'Music' : 'Games',
      platform: item.platform ?? '',
      genre: item.genre,
      release_date: item.release_date ?? (item.year_released ? `${item.year_released}-01-01` : ''),
      year_released: item.year_released ? String(item.year_released) : '',
      rating: normalizeGameRating(item.rating),
      players: item.players ? String(item.players) : '',
      artist: item.artist ?? '',
      format: item.format ?? '',
      region: item.region ?? '',
      cover_image: item.cover_image ?? '',
      tags: item.tags ?? '',
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
      rating: adminForm.category === 'Games' ? normalizeGameRating(adminForm.rating) : null,
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
    loadSystemsFromStorage();

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
        <div class="console-hud">
          <div class="hud-left console-header-shell">
            {#if consoleHeaderOption?.logoImage && hoveredConsoleFadeVisible}
              <img
                src={consoleHeaderOption.logoImage}
                alt={consoleHeaderOption.name}
                class="console-header-logo"
                draggable="false"
              />
            {:else}
              <span class="console-header-copy">Console Library</span>
            {/if}
          </div>
          <div class="hud-right console-header-count">{hoveredConsole ? consoleSubheaderLabel : consoleLibraryCountLabel}</div>
        </div>
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
                    <span class={`disc-case${isSquareLibraryPlatform(item.platform) ? ' disc-case--square' : ''}`} aria-hidden="true">
                      <span class="disc-case-spine"></span>
                      <span class="disc-case-front">
                        {#if item.cover_image && !brokenCoverIds.has(item.id)}
                          <img src={item.cover_image} alt={item.title} class="library-art" loading="lazy" on:error={() => markCoverBroken(item.id)} />
                        {:else}
                          <span class="library-fallback">{iconInitials(item.title)}</span>
                        {/if}
                        {#if caseOverlayUrl(item)}
                          <img src={caseOverlayUrl(item) ?? ''} alt="" class="game-overlay game-overlay--case" aria-hidden="true" draggable="false" />
                        {/if}
                      </span>
                      <span class={`disc-case-disc ${discBackingClass(item)}${isCartridgePlatform(item.platform) ? ' disc-case-disc--cartridge' : ''}`}>
                        <span class="disc-shell-backing"></span>
                        {#if libraryDiscImageUrl(item)}
                          <img src={libraryDiscImageUrl(item) ?? ''} alt="" class="disc-image" aria-hidden="true" draggable="false" />
                        {:else}
                          <span class="disc-shell-fallback">{iconInitials(item.title)}</span>
                        {/if}
                        {#if discOverlayUrl(item)}
                          <img src={discOverlayUrl(item) ?? ''} alt="" class="game-overlay game-overlay--disc" aria-hidden="true" draggable="false" />
                        {/if}
                        {#if !isCartridgePlatform(item.platform)}
                          <span class="disc-hole"></span>
                        {/if}
                      </span>
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
                {#if isCartridgePlatform(selectedItem.platform)}
                  <div class="details-cart-flipper">
                    <div class="details-disc-flip-face details-disc-flip-face--front">
                      <div class={`details-cartridge ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if discOverlayUrl(selectedItem)}
                          <img src={discOverlayUrl(selectedItem) ?? ''} alt="" class="game-overlay game-overlay--cartridge" aria-hidden="true" draggable="false" />
                        {/if}
                      </div>
                    </div>
                    <div class="details-disc-flip-face details-disc-flip-face--back" aria-hidden="true">
                      <div class={`details-cartridge ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if detailBackImageUrl(selectedItem)}
                          <img src={detailBackImageUrl(selectedItem) ?? ''} alt="" class="details-cartridge-back" draggable="false" />
                        {/if}
                      </div>
                    </div>
                  </div>
                {:else}
                  <div class="details-disc-flipper">
                    <div class="details-disc-flip-face details-disc-flip-face--front">
                      <div class={`details-game-disc ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if selectedItem.cover_image && !brokenCoverIds.has(selectedItem.id)}
                          <img src={selectedItem.cover_image} alt={selectedItem.title} class="details-game-disc-art" draggable="false" />
                        {:else}
                          <div class="details-game-disc-fallback">{iconInitials(selectedItem.title)}</div>
                        {/if}
                        {#if discOverlayUrl(selectedItem)}
                          <img src={discOverlayUrl(selectedItem) ?? ''} alt="" class="game-overlay game-overlay--disc" aria-hidden="true" draggable="false" />
                        {/if}
                        <span class="disc-hole"></span>
                        <span class="details-game-disc-shine"></span>
                      </div>
                    </div>
                    <div class="details-disc-flip-face details-disc-flip-face--back" aria-hidden="true">
                      <div class={`details-game-disc ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if detailBackImageUrl(selectedItem)}
                          <img src={detailBackImageUrl(selectedItem) ?? ''} alt="" class="details-game-disc-back" draggable="false" />
                        {/if}
                        <span class="disc-hole"></span>
                      </div>
                    </div>
                  </div>
                {/if}
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
          <p class="details-line-5">{selectedItem.notes?.trim() || 'No description available.'}</p>
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
          <button type="button" on:click={() => openAdminMode('systems')}>Manage Systems</button>
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
      {#if !isAdmin}
        <div class="admin-header">
          <h2>Admin Access</h2>
          <button type="button" class="ghost" on:click={() => (adminOpen = false)}>Close</button>
        </div>
        <div class="admin-login">
          <label for="admin-password">Password</label>
          <input id="admin-password" type="password" bind:value={adminPassword} placeholder="Enter password..." />
          <button type="button" disabled={adminBusy} on:click={adminLogin}>Log In</button>
        </div>
      {:else}
        {#if adminMode === 'hub'}
          <!-- ADMIN HUB VIEW -->
          <div class="admin-header">
            <h2>Admin Hub</h2>
            <button type="button" class="ghost" on:click={() => (adminOpen = false)}>Close</button>
          </div>
          
          <div class="admin-hub-options">
            <button type="button" class="admin-hub-card" on:click={() => openAdminMode('systems')}>
              <h3>System Manager</h3>
              <p>Manage game consoles and gaming systems</p>
            </button>
            <button type="button" class="admin-hub-card" on:click={() => openAdminMode('library', 'games')}>
              <h3>Library Manager</h3>
              <p>Manage games and music in your collection</p>
            </button>
          </div>

          <div class="admin-actions">
            <button type="button" class="ghost" on:click={adminLogout}>Log Out</button>
          </div>
        {:else if adminMode === 'systems'}
          <!-- SYSTEMS MANAGER VIEW -->
          <div class="admin-header">
            <button type="button" class="ghost back-to-hub" on:click={backToAdminHub}>← Hub</button>
            <h2>System Manager</h2>
            <button type="button" class="ghost" on:click={() => (adminOpen = false)}>Close</button>
          </div>

          <div class="admin-layout">
            <!-- Systems List (Left) -->
            <div class="admin-list-pane">
              <div class="systems-add-section">
                <h4>Add New System</h4>
                <div class="systems-add-row">
                  <input type="text" bind:value={newSystemName} placeholder="System name" />
                  <input type="text" bind:value={newSystemIcon} placeholder="Logo URL (optional)" />
                  <button type="button" on:click={addSystem} class="add-button">Add</button>
                </div>
              </div>

              {#if systemError}
                <p class="admin-error">{systemError}</p>
              {/if}

              <div class="systems-list">
                {#each editableSystems as system}
                  <div class="systems-row">
                    <div class="systems-row-main">
                      <div class="systems-logo-container">
                        {#if system.logoImage}
                          <img src={system.logoImage} alt={system.name} class="systems-logo" draggable="false" />
                        {:else}
                          <span class="systems-fallback">{system.shortName}</span>
                        {/if}
                      </div>
                      <div class="systems-info">
                        <strong>{system.name}</strong>
                        <small>{system.shortName}</small>
                      </div>
                    </div>
                    <div class="systems-actions">
                      <button type="button" class="edit-button" on:click={() => startEditSystem(system.id)}>Edit</button>
                      <button type="button" class="danger" on:click={() => removeSystem(system.id)}>Remove</button>
                    </div>
                  </div>
                {/each}
              </div>
            </div>

            <!-- System Editor (Right) -->
            <div class="admin-form-pane">
              {#if editingSystemId !== null}
                <div class="systems-edit-mode">
                  <h3>Edit System</h3>
                  <input type="text" bind:value={editingSystemName} placeholder="System name" class="edit-name" />
                  <input type="text" bind:value={editingSystemIcon} placeholder="Logo URL" class="edit-icon" />
                  <div class="form-actions">
                    <button type="button" on:click={saveEditSystem} class="save-button">Save</button>
                    <button type="button" on:click={cancelEditSystem} class="cancel-button">Cancel</button>
                  </div>
                </div>
              {:else}
                <div class="admin-form-empty">
                  <p>Select a system to edit, or add a new one on the left.</p>
                </div>
              {/if}
            </div>
          </div>

        {:else if adminMode === 'library'}
          <!-- LIBRARY MANAGER VIEW -->
          <div class="admin-header">
            <button type="button" class="ghost back-to-hub" on:click={backToAdminHub}>← Hub</button>
            <h2>Library Manager</h2>
            <button type="button" class="ghost" on:click={() => (adminOpen = false)}>Close</button>
          </div>

          <div class="admin-tabs">
            <button 
              type="button" 
              class:active={libraryAdminTab === 'games'}
              on:click={() => { libraryAdminTab = 'games'; adminListPage = 0; }}
            >
              Games
            </button>
            <button 
              type="button" 
              class:active={libraryAdminTab === 'music'}
              on:click={() => { libraryAdminTab = 'music'; adminListPage = 0; }}
            >
              Music
            </button>
          </div>

          <div class="admin-layout">
            <!-- Library List (Left) -->
            <div class="admin-list-pane">
              <div class="admin-list-filters">
                <input type="search" class="search-input-unified" bind:value={adminSearchQuery} placeholder="Search by title..." />
                {#if libraryAdminTab === 'games'}
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
                  {#if item.category === (libraryAdminTab === 'games' ? 'Games' : 'Music')}
                    <div
                      class="admin-row"
                      class:active={adminEditingId === item.id}
                      role="button"
                      tabindex="0"
                      on:click={() => openAdminMode('library', libraryAdminTab, item)}
                      on:keydown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          openAdminMode('library', libraryAdminTab, item);
                        }
                      }}
                    >
                      <div class="admin-row-content">
                        <strong>{item.title}</strong>
                        <small>{item.platform ?? item.format ?? item.artist ?? 'Unknown'}</small>
                      </div>
                      <div class="admin-row-actions">
                        <button type="button" on:click|stopPropagation={() => openAdminMode('library', libraryAdminTab, item)}>Edit</button>
                        <button type="button" class="danger" on:click|stopPropagation={() => openDeleteConfirm(item)}>Delete</button>
                      </div>
                    </div>
                  {/if}
                {/each}
              </div>

              {#if adminListTotalPages > 1}
                <div class="admin-list-pager">
                  <button type="button" on:click={() => (adminListPage = Math.max(0, adminListPage - 1))} disabled={adminListPage === 0}>Back</button>
                  <div class="admin-pager-info">Page {adminListPage + 1} / {adminListTotalPages}</div>
                  <button type="button" on:click={() => (adminListPage = Math.min(adminListTotalPages - 1, adminListPage + 1))} disabled={adminListPage >= adminListTotalPages - 1}>Next</button>
                </div>
              {/if}
            </div>

            <!-- Library Editor (Right) -->
            <div class="admin-form-pane">
              {#if adminEditingId !== null}
                <form class="admin-form" on:submit|preventDefault={saveAdminItem}>
                  <h3>{adminContextItem?.title ?? 'Edit Item'}</h3>
                  <input type="text" bind:value={adminForm.title} placeholder="Title" required />
                  
                  {#if libraryAdminTab === 'games'}
                    <select bind:value={adminForm.platform}>
                      <option value="">Select console</option>
                      {#each adminConsoleOptions as consoleName}
                        <option value={consoleName}>{consoleName}</option>
                      {/each}
                    </select>
                    <select bind:value={adminForm.genre} required>
                      <option value="" disabled>Select genre</option>
                      {#each adminGenreOptions as genreName}
                        <option value={genreName}>{genreName}</option>
                      {/each}
                    </select>
                    <input type="date" bind:value={adminForm.release_date} placeholder="Release date" />
                    <select bind:value={adminForm.players}>
                      <option value="">Number of players</option>
                      {#each adminPlayerOptions as playerCount}
                        <option value={String(playerCount)}>{playerCount}</option>
                      {/each}
                    </select>
                    <select bind:value={adminForm.rating}>
                      {#each gameRatingOptions as ratingOption}
                        <option value={ratingOption}>{ratingOption}</option>
                      {/each}
                    </select>
                  {:else}
                    <input type="text" bind:value={adminForm.artist} placeholder="Artist" />
                    <input type="text" bind:value={adminForm.format} placeholder="Format" />
                  {/if}

                  {#if libraryAdminTab !== 'games'}
                    <select bind:value={adminForm.genre} required>
                      <option value="" disabled>Select genre</option>
                      {#each adminGenreOptions as genreName}
                        <option value={genreName}>{genreName}</option>
                      {/each}
                    </select>
                  {/if}
                  <input type="text" bind:value={adminForm.cover_image} placeholder="Cover image URL" />
                  <textarea bind:value={adminForm.notes} rows="3" placeholder="Short description"></textarea>
                  
                  <div class="form-actions">
                    <button type="submit" disabled={adminBusy}>{adminEditingId ? 'Save Changes' : 'Create Item'}</button>
                    <button type="button" on:click={() => { adminEditingId = null; adminContextItem = null; }}>Clear</button>
                  </div>
                </form>
              {:else}
                <div class="admin-form-empty">
                  <p>Select an item from the list to edit, or click the button below to create a new one.</p>
                  <button type="button" on:click={() => { resetAdminForm(); adminEditingId = -1; }}>Create New {libraryAdminTab === 'games' ? 'Game' : 'Album'}</button>
                </div>
              {/if}
            </div>
          </div>
        {/if}

        {#if adminError}
          <p class="admin-error">{adminError}</p>
        {/if}
        {#if adminMessage}
          <p class="admin-status">{adminMessage}</p>
        {/if}
      {/if}
    </div>
  </div>
{/if}


    <div class="footer">
      <p>&copy; 2026 ALEX PRITT</p>
    </div>
  </div>
{/if}

