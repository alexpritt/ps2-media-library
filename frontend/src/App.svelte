<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { TransitionConfig } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
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
    publishers: string[];
    gameGenres: string[];
    release_date: string;
    year_released: string;
    rating: GameRating;
    players: string;
    cooperative: string;
    artist: string;
    musicGenre: string;
    cover_image: string | null;
    spine_image: string | null;
    disc_image: string | null;
    notes: string;
  };

  type GameArtField = 'cover_image' | 'spine_image' | 'disc_image';
  type LaunchboxArtKind = 'cover' | 'disc' | 'spine';
  type DataSource = 'launchbox' | 'mobygames' | 'rawg' | 'cache' | 'unknown';
  type DetailTagTone = 'blue' | 'cyan' | 'green' | 'amber' | 'rose' | 'violet';

  type DetailTag = {
    label: string;
    query: string;
    tone: DetailTagTone;
  };

  type ConsoleOption = {
    name: string;
    shortName: string;
    logo: string;
    logoImage?: string;
    caseType?: 'disc' | 'cartridge' | 'hybrid';
    appearancePreset?: string | null;
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
  const gameGenreDefaults = [
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
  const musicGenreDefaults = [
    'Alternative',
    'Electronic',
    'Hip-Hop',
    'Jazz',
    'Pop',
    'R&B',
    'Rock',
    'Soundtrack',
  ];
  const publisherDefaults = [
    'Activision',
    'Atari',
    'Bandai Namco Entertainment',
    'Bethesda Softworks',
    'Capcom',
    'Electronic Arts',
    'Konami',
    'Microsoft Game Studios',
    'Nintendo',
    'Rockstar Games',
    'Sega',
    'Sony Computer Entertainment',
    'Square Enix',
    'THQ',
    'Take-Two Interactive',
    'Ubisoft',
    'Warner Bros. Games',
  ];
  const cooperativeOptions = ['No', 'Yes'];
  const SITE_LOGO_SRC = '/brand-logo.png';

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
  let bootRescueTimeout: ReturnType<typeof setTimeout> | null = null;
  let bootPlaybackRetryInterval: ReturnType<typeof setInterval> | null = null;
  let bootHardFailTimeout: ReturnType<typeof setTimeout> | null = null;
  let bootRevealAt = 9;
  const BOOT_SKIP_TIME = 6;
  const BOOT_RESCUE_TIMEOUT_MS = 5000;
  const BOOT_HARD_FAIL_OPEN_MS = 12000;
  const BOOT_LOOP_CEILING_TIME = 600;

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
  let brokenSpineIds = new Set<number>();
  let brokenDiscIds = new Set<number>();
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
  let adminPublisherChoice = '';
  let adminGameGenreChoice = '';
  let adminMusicGenreChoice = '';
  let detailsEditMode = false;
  let adminEditingId: number | null = null;
  let adminPassword = '';
  let adminBusy = false;
  let adminError = '';
  let adminMessage = '';
  let launchboxFetchBusy = false;
  let launchboxFetchError = '';
  let launchboxArtPickerOpen = false;
  let launchboxArtPickerBusy = false;
  let launchboxArtPickerError = '';
  let launchboxArtPickerField: GameArtField | null = null;
  let launchboxArtOptions: string[] = [];
  let bulkOpen = false;
  let bulkText = '';
  let bulkBusy = false;
  let bulkResults: { line: string; status: 'success' | 'error'; message: string }[] = [];
  let bulkTotalCount = 0;
  let bulkProcessedCount = 0;
  let bulkProgressPercent = 0;
  let bulkStatusText = '';
  let bulkErrorText = '';
  let adminForm: AdminForm = emptyAdminForm();
  let editableSystems: EditableSystem[] = [];
  let editingSystemId: string | null = null;
  let editingSystemName = '';
  let editingSystemIcon = '';
  let editingSystemCaseType: '' | 'disc' | 'cartridge' | 'hybrid' = '';
  let newSystemName = '';
  let newSystemIcon = '';
  let newSystemCaseType: '' | 'disc' | 'cartridge' | 'hybrid' = '';
  let systemError = '';
  let systemLogoFetchBusy = false;
  let systemLogoFetchError = '';
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
  $: if (stage === 'console' && hoveredConsole) {
    hoveredConsoleFadeVisible = true;
    if (hoveredConsoleFadeTimeout) clearTimeout(hoveredConsoleFadeTimeout);
    hoveredConsoleFadeTimeout = setTimeout(() => {
      hoveredConsole = null;
    }, 4000);
  }
  $: if (stage !== 'console' || !hoveredConsole) {
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
  $: hoveredConsoleCountLabel = hoveredConsoleGameCount !== null
    ? `${hoveredConsoleGameCount} ${hoveredConsoleGameCount === 1 ? 'Game' : 'Games'} in Library`
    : consoleLibraryCountLabel;
  $: currentItems = pagedItems();
  $: totalPages = Math.ceil(media.length / itemsPerPage);
  $: libraryCountLabel = category === 'Music'
    ? `${media.length} ${media.length === 1 ? 'Album' : 'Albums'} in Library`
    : `${media.length} ${media.length === 1 ? 'Game' : 'Games'} in ${selectedConsole ?? activeConsole.name} Library`;
  $: adminConsoleOptions = availableConsoles.map((item) => item.name);
  $: adminGameGenreOptions = buildGameGenreOptions(allMedia);
  $: adminMusicGenreOptions = buildMusicGenreOptions(allMedia);
  $: adminPublisherOptions = buildPublisherOptions(allMedia);
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
  $: detailsConsoleLogo = selectedItem?.category === 'Games'
    ? availableConsoles.find((item) => item.name === (selectedItem.platform ?? ''))?.logoImage ?? null
    : null;

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
      result = result.filter((item) => matchesLibrarySearch(item, q));
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
  $: if (selectedItem?.id != null) {
    const refreshedSelectedItem = allMedia.find((item) => item.id === selectedItem?.id) ?? null;
    if (refreshedSelectedItem && refreshedSelectedItem !== selectedItem) {
      selectedItem = refreshedSelectedItem;
    }
  }
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


  function emptyAdminForm(category: Category = 'Games'): AdminForm {
    return {
      id: null,
      title: '',
      category,
      platform: 'PlayStation 2',
      publishers: [],
      gameGenres: [],
      release_date: '',
      year_released: '',
      rating: 'RP',
      players: '',
      cooperative: 'No',
      artist: '',
      musicGenre: '',
      cover_image: null,
      spine_image: null,
      disc_image: null,
      notes: '',
    };
  }

  function normalizeSelectionValues(values: string[]) {
    return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
  }

  function splitDelimitedValues(value: string | null | undefined) {
    return normalizeSelectionValues((value ?? '').split(',').map((entry) => entry.trim()));
  }

  function combineSelectionValues(values: string[]) {
    const normalized = normalizeSelectionValues(values);
    return normalized.length > 0 ? normalized.join(', ') : null;
  }

  function buildOptionValues(defaultValues: string[], existingValues: string[]) {
    return normalizeSelectionValues([...defaultValues, ...existingValues]).sort((left, right) => left.localeCompare(right));
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

  function inferAppearancePreset(platform: string | null | undefined) {
    const key = normalizeConsoleKey(platform);
    if (key === 'nds' || key === '3ds' || key === 'gb') return key;
    if (key === 'ps2' || key === 'ps3' || key === 'ps4' || key === 'gamecube' || key === 'wii' || key === 'xbox' || key === 'xbox360') return key;
    return 'generic-disc';
  }

  function getSystemAppearance(platform: string | null | undefined) {
    const system = availableConsoles.find((entry) => entry.name === (platform ?? ''));
    const preset = (system?.appearancePreset ?? inferAppearancePreset(platform) ?? 'generic-disc').toLowerCase();
    const inferredCartridge = preset === 'nds' || preset === '3ds' || preset === 'gb';
    const caseType = inferredCartridge ? 'cartridge' : (system?.caseType ?? 'disc');
    return { caseType, preset } as const;
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

  function normalizeGameTitle(title: string) {
    const cleaned = title.trim().replace(/\s+/g, ' ');
    if (!cleaned) return '';
    const lowerWords = new Set(['a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into', 'nor', 'of', 'on', 'or', 'over', 'the', 'to', 'up', 'with']);
    const preserveWords = new Set(['II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV', 'HD', '3D', 'DS', 'PSP', 'VR', 'USA', 'EU', 'USA.']);
    return cleaned
      .split(' ')
      .map((word, index, words) => {
        const stripped = word.replace(/^["'([{]+|["')\]}.,:;!?]+$/g, '');
        const punctuationPrefix = word.slice(0, word.indexOf(stripped));
        const punctuationSuffix = word.slice(word.indexOf(stripped) + stripped.length);
        const normalizedToken = stripped.includes('-')
          ? stripped.split('-').map((segment) => segment ? normalizeGameTitle(segment) : segment).join('-')
          : stripped;
        const upper = normalizedToken.toUpperCase();
        if (preserveWords.has(upper)) return `${punctuationPrefix}${upper}${punctuationSuffix}`;
        if (word.includes(':')) {
          return `${punctuationPrefix}${normalizedToken.split(':').map((segment, segmentIndex) => {
            if (segmentIndex === 0 || segmentIndex === words.length - 1) return segment ? normalizeGameTitle(segment) : segment;
            return segment;
          }).join(':')}${punctuationSuffix}`;
        }
        if (index !== 0 && lowerWords.has(normalizedToken.toLowerCase())) return `${punctuationPrefix}${normalizedToken.toLowerCase()}${punctuationSuffix}`;
        return `${punctuationPrefix}${normalizedToken ? normalizedToken[0].toUpperCase() + normalizedToken.slice(1).toLowerCase() : normalizedToken}${punctuationSuffix}`;
      })
      .join(' ')
      .replace(/\bVii\b/g, 'VII')
      .replace(/\bVi\b/g, 'VI')
      .replace(/\bViii\b/g, 'VIII')
      .replace(/\bIv\b/g, 'IV')
      .replace(/\bIii\b/g, 'III')
      .replace(/\bIi\b/g, 'II');
  }

  function isCartridgePlatform(platform: string | null | undefined) {
    return getSystemAppearance(platform).caseType === 'cartridge';
  }

  function caseGeometryClass(platform: string | null | undefined) {
    const { caseType, preset } = getSystemAppearance(platform);
    if (caseType === 'cartridge') {
      if (preset === 'nds') return ' disc-case--nds';
      if (preset === '3ds') return ' disc-case--3ds';
      if (preset === 'gb') return ' disc-case--gb';
      return ' disc-case--cart-generic';
    }
    if (preset === 'ps2') return ' disc-case--ps2';
    if (preset === 'ps3') return ' disc-case--ps3';
    if (preset === 'ps4') return ' disc-case--ps4';
    if (preset === 'gamecube') return ' disc-case--gamecube';
    if (preset === 'wii') return ' disc-case--wii';
    if (preset === 'xbox') return ' disc-case--xbox';
    if (preset === 'xbox360') return ' disc-case--xbox360';
    return '';
  }

  function discBackingClass(item: MediaItem) {
    const { caseType, preset } = getSystemAppearance(item.platform);
    if (caseType === 'cartridge') {
      if (preset === 'nds') return 'disc-shell--nds';
      if (preset === '3ds') return 'disc-shell--3ds';
      if (preset === 'gb') return 'disc-shell--gb';
      return 'disc-shell--cart-generic';
    }
    if (preset === 'ps2') return 'disc-shell--ps2';
    if (preset === 'ps3') return 'disc-shell--ps3';
    if (preset === 'ps4') return 'disc-shell--ps4';
    if (preset === 'gamecube') return 'disc-shell--gamecube';
    if (preset === 'wii') return 'disc-shell--wii';
    if (preset === 'xbox') return 'disc-shell--xbox';
    if (preset === 'xbox360') return 'disc-shell--xbox360';
    return 'disc-shell--default';
  }

  function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function popupOverlayTransition(_node: Element): TransitionConfig {
    return {
      duration: 190,
      easing: cubicOut,
      css: (t) => `opacity: ${t};`,
    };
  }

  function popupPanelTransition(_node: Element): TransitionConfig {
    return {
      duration: 220,
      easing: cubicOut,
      css: (t) => {
        const scale = 0.97 + (0.03 * t);
        const y = (1 - t) * 10;
        return `opacity: ${t}; transform: translateY(${y}px) scale(${scale});`;
      },
    };
  }

  function buildConsoleList(_mediaItems: MediaItem[], systems: EditableSystem[]) {
    // Sort by displayOrder (or alphabetically if displayOrder is missing)
    const sorted = [...systems].sort((a, b) => {
      const orderA = a.displayOrder ?? 999;
      const orderB = b.displayOrder ?? 999;
      if (orderA !== orderB) return orderA - orderB;
      return a.name.localeCompare(b.name);
    });

    return sorted.map((system) => ({
      name: system.name,
      shortName: system.shortName,
      logo: system.logo,
      logoImage: system.logoImage,
      caseType: system.caseType,
      appearancePreset: system.appearancePreset,
    }));
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

  function releaseTagValue(item: MediaItem) {
    const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    if (item.release_date) {
      const parts = item.release_date.split('-');
      if (parts.length === 3) {
        const [year, month, day] = parts;
        const monthName = MONTHS[parseInt(month, 10) - 1] ?? month;
        return `${monthName} ${parseInt(day, 10)}, ${year}`;
      }
    }
    if (item.year_released) return String(item.year_released);
    return 'Unknown';
  }

  function normalizeDateForInput(value: unknown): string {
    if (typeof value !== 'string') return '';
    const raw = value.trim();
    if (!raw) return '';

    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

    const slash = raw.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
    if (slash) {
      const [, y, m, d] = slash;
      return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
    }

    const yearOnly = raw.match(/^(19|20)\d{2}$/);
    if (yearOnly) return `${raw}-01-01`;

    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) {
      const y = parsed.getFullYear();
      const m = String(parsed.getMonth() + 1).padStart(2, '0');
      const d = String(parsed.getDate()).padStart(2, '0');
      return `${y}-${m}-${d}`;
    }

    return '';
  }

  function detailText(item: MediaItem) {
    if (item.category === 'Music') {
      return `Genre: ${item.genre?.trim() || 'Unknown'}`;
    }

    const genres = (item.genres ?? item.genre ?? '').trim() || 'Unknown genre';
    const publisher = (item.publisher ?? '').trim() || 'Unknown publisher';
    const players = item.players ? `${item.players} player${item.players === 1 ? '' : 's'}` : 'Players unknown';
    const cooperative = item.cooperative?.trim() ? `Co-op: ${item.cooperative}` : 'Co-op: Unknown';
    const rating = `Rated ${normalizeGameRating(item.rating)}`;

    return `${genres} | ${publisher} | ${players} | ${cooperative} | ${rating}`;
  }

  function librarySearchTokens(item: MediaItem) {
    const tokens: string[] = [];
    const push = (...values: Array<string | number | null | undefined>) => {
      for (const value of values) {
        const text = String(value ?? '').trim();
        if (text) tokens.push(text.toLowerCase());
      }
    };

    push(item.title, item.platform, item.genre, item.genres, item.publisher, item.artist, item.rating, item.cooperative, item.release_date, item.notes);
    if (item.year_released != null) push(String(item.year_released));

    if (item.players != null) {
      push(
        String(item.players),
        `${item.players} player`,
        `${item.players} players`,
        `players ${item.players}`,
        `player count ${item.players}`,
      );
    }

    return tokens;
  }

  function matchesLibrarySearch(item: MediaItem, query: string) {
    if (!query) return true;
    const tokens = librarySearchTokens(item);
    return tokens.some((token) => token.includes(query));
  }

  function addTag(tags: DetailTag[], seen: Set<string>, label: string, query: string, tone: DetailTagTone) {
    const normalizedLabel = label.trim();
    const normalizedQuery = query.trim();
    if (!normalizedLabel || !normalizedQuery) return;
    const key = `${normalizedLabel.toLowerCase()}|${normalizedQuery.toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    tags.push({ label: normalizedLabel, query: normalizedQuery, tone });
  }

  function detailTags(item: MediaItem): DetailTag[] {
    const tags: DetailTag[] = [];
    const seen = new Set<string>();

    if (item.category === 'Games') {
      addTag(tags, seen, `Platform: ${item.platform ?? selectedConsole ?? 'Unknown'}`, item.platform ?? selectedConsole ?? 'Unknown', 'blue');
      addTag(tags, seen, `Release: ${releaseTagValue(item)}`, item.year_released ? String(item.year_released) : releaseTagValue(item), 'cyan');

      for (const genre of splitDelimitedValues(item.genres ?? item.genre)) {
        addTag(tags, seen, `Genre: ${genre}`, genre, 'green');
      }

      for (const publisher of splitDelimitedValues(item.publisher)) {
        addTag(tags, seen, `Publisher: ${publisher}`, publisher, 'amber');
      }

      if (item.players != null) {
        const playerLabel = `${item.players} Player${item.players === 1 ? '' : 's'}`;
        addTag(tags, seen, `Players: ${playerLabel}`, `${item.players} players`, 'violet');
      }

      if (item.cooperative?.trim()) {
        addTag(tags, seen, `Co-op: ${item.cooperative}`, item.cooperative, 'rose');
      }

      addTag(tags, seen, `Rating: ${normalizeGameRating(item.rating)}`, normalizeGameRating(item.rating), 'blue');
      return tags;
    }

    addTag(tags, seen, `Artist: ${item.artist?.trim() || 'Unknown'}`, item.artist?.trim() || 'Unknown', 'blue');
    addTag(tags, seen, `Genre: ${item.genre?.trim() || 'Unknown'}`, item.genre?.trim() || 'Unknown', 'green');
    addTag(tags, seen, `Release: ${releaseTagValue(item)}`, item.year_released ? String(item.year_released) : releaseTagValue(item), 'cyan');

    if (item.format?.trim()) addTag(tags, seen, `Format: ${item.format}`, item.format, 'violet');
    if (item.region?.trim()) addTag(tags, seen, `Region: ${item.region}`, item.region, 'amber');

    return tags;
  }

  function applyDetailTagFilter(query: string) {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) return;
    librarySearch = normalizedQuery;
    librarySearchOpen = true;
    playersDropdownOpen = false;
    page = 0;
    closeDetails();
  }

  function buildGameGenreOptions(mediaItems: MediaItem[]) {
    const existing = mediaItems
      .filter((item) => item.category === 'Games')
      .flatMap((item) => splitDelimitedValues(item.genres ?? item.genre));
    return buildOptionValues(gameGenreDefaults, existing);
  }

  function buildMusicGenreOptions(mediaItems: MediaItem[]) {
    const existing = mediaItems
      .filter((item) => item.category === 'Music')
      .map((item) => item.genre)
      .filter(Boolean)
      .flatMap((value) => splitDelimitedValues(value));
    return buildOptionValues(musicGenreDefaults, existing);
  }

  function buildPublisherOptions(mediaItems: MediaItem[]) {
    const existing = mediaItems
      .filter((item) => item.category === 'Games')
      .flatMap((item) => splitDelimitedValues(item.publisher));
    return buildOptionValues(publisherDefaults, existing);
  }

  function updateAdminSelection(field: 'publishers' | 'gameGenres', value: string, action: 'add' | 'remove') {
    const normalizedValue = value.trim();
    if (!normalizedValue) return;
    const currentValues = adminForm[field];
    const nextValues = action === 'add'
      ? normalizeSelectionValues([...currentValues, normalizedValue])
      : currentValues.filter((entry) => entry !== normalizedValue);
    adminForm = { ...adminForm, [field]: nextValues };
  }

  function canFetchLaunchBoxGameData() {
    const title = (adminForm.title ?? '').trim();
    const platform = ((adminForm.platform ?? '').trim() || (selectedConsole ?? '').trim());
    return title.length > 0 && platform.length > 0;
  }

  function launchboxArtKindForField(field: GameArtField): LaunchboxArtKind {
    if (field === 'cover_image') return 'cover';
    if (field === 'spine_image') return 'spine';
    return 'disc';
  }

  function adminArtLabel(field: GameArtField) {
    if (field === 'cover_image') return 'Box Art';
    if (field === 'spine_image') return 'Spine Art';
    return 'Disc/Cart Art';
  }

  function formatDataSourceLabel(value: unknown): string {
    const source = String(value ?? '').trim().toLowerCase();
    if (source === 'launchbox') return 'LaunchBox';
    if (source === 'mobygames') return 'MobyGames';
    if (source === 'rawg') return 'RAWG';
    if (source === 'igdb') return 'IGDB';
    if (source === 'cache') return 'cache';
    return 'backup source';
  }

  function closeLaunchboxArtPicker() {
    launchboxArtPickerOpen = false;
    launchboxArtPickerBusy = false;
    launchboxArtPickerError = '';
    launchboxArtOptions = [];
    launchboxArtPickerField = null;
  }

  async function openLaunchboxArtPicker(field: GameArtField) {
    if (launchboxArtPickerBusy) return;

    launchboxFetchError = '';
    adminError = '';
    adminMessage = '';

    if (!canFetchLaunchBoxGameData()) {
      launchboxFetchError = 'Enter a game title and select a platform first.';
      return;
    }

    launchboxArtPickerOpen = true;
    launchboxArtPickerBusy = true;
    launchboxArtPickerError = '';
    launchboxArtPickerField = field;
    launchboxArtOptions = [];

    try {
      const response = await fetch('/api/launchbox/game-art-options', {
        method: 'POST',
        headers: mediaHeaders(),
        body: JSON.stringify({
          title: (adminForm.title ?? '').trim(),
          platform: ((adminForm.platform ?? '').trim() || (selectedConsole ?? '').trim()),
          art_type: launchboxArtKindForField(field),
        }),
      });
      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        adminError = 'Session expired. Log in again.';
        closeLaunchboxArtPicker();
        return;
      }

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        launchboxArtPickerError = data?.detail ?? 'Could not find art options for this category from any source.';
        return;
      }

      launchboxArtOptions = Array.isArray(data?.options)
        ? data.options.filter((entry: unknown) => typeof entry === 'string' && entry.trim())
        : [];

      if (!launchboxArtOptions.length) {
        launchboxArtPickerError = 'No art options were returned for this category.';
      }
    } catch {
      launchboxArtPickerError = 'Could not fetch art options from any source.';
    } finally {
      launchboxArtPickerBusy = false;
    }
  }

  function chooseLaunchboxArtOption(imageData: string) {
    if (!launchboxArtPickerField || !imageData) return;
    const label = adminArtLabel(launchboxArtPickerField);
    adminForm = {
      ...adminForm,
      [launchboxArtPickerField]: imageData,
    } as AdminForm;
    adminMessage = `${label} selected from LaunchBox.`;
    adminError = '';
    launchboxFetchError = '';
    closeLaunchboxArtPicker();
  }

  async function bulkUpload() {
    if (bulkBusy) return;
    bulkResults = [];
    bulkErrorText = '';
    bulkBusy = true;
    adminError = '';
    adminMessage = '';
    const lines = bulkText.split('\n').map((l) => l.trim()).filter(Boolean);
    bulkTotalCount = lines.length;
    bulkProcessedCount = 0;
    bulkProgressPercent = 0;
    bulkStatusText = lines.length ? `Starting upload for ${lines.length} item${lines.length === 1 ? '' : 's'}...` : '';
    if (!lines.length) { bulkBusy = false; return; }
    const bulkPlatform = libraryAdminTab === 'games' ? (adminSearchPlatform === 'All' ? '' : adminSearchPlatform.trim()) : '';
    if (libraryAdminTab === 'games' && !bulkPlatform) {
      adminError = 'Select a platform filter above before bulk uploading games.';
      bulkErrorText = adminError;
      bulkStatusText = 'Upload blocked: select a platform first.';
      bulkBusy = false;
      return;
    }
    const endpoint = libraryAdminTab === 'games' ? '/api/bulk/games' : '/api/bulk/music';
    const nextResults: { line: string; status: 'success' | 'error'; message: string }[] = [];
    let successCount = 0;
    let errorCount = 0;

    try {
      for (const line of lines) {
        try {
          const response = await fetch(endpoint, {
            method: 'POST',
            headers: mediaHeaders(),
            body: JSON.stringify(
              libraryAdminTab === 'games'
                ? { items: [line], platform: bulkPlatform }
                : { items: [line] }
            ),
          });

          if (response.status === 401) {
            adminToken = '';
            localStorage.removeItem('ps2-admin-token');
            adminError = 'Session expired. Log in again.';
            bulkErrorText = adminError;
            nextResults.push({
              line,
              status: 'error',
              message: 'Error: Session expired. Log in again.',
            });
            errorCount += 1;
            bulkProcessedCount += 1;
            bulkProgressPercent = Math.round((bulkProcessedCount / bulkTotalCount) * 100);
            bulkResults = [...nextResults];
            bulkStatusText = `Stopped at ${bulkProcessedCount}/${bulkTotalCount}. ${successCount} succeeded, ${errorCount} failed.`;
            break;
          }

          const data = await response.json().catch(() => null);
          if (!response.ok) {
            const detail = typeof data?.detail === 'string' && data.detail.trim()
              ? data.detail
              : `Request failed (${response.status})`;
            nextResults.push({
              line,
              status: 'error',
              message: `Error: ${detail}`,
            });
            errorCount += 1;
          } else {
            const singleResult = Array.isArray(data?.results) && data.results.length ? data.results[0] : null;
            const status = singleResult?.status === 'success' ? 'success' : 'error';
            if (status === 'success') {
              successCount += 1;
            } else {
              errorCount += 1;
            }
            nextResults.push({
              line: singleResult?.line ?? line,
              status,
              message: status === 'success'
                ? `Added: ${singleResult?.title ?? 'Created item'}`
                : `Error: ${singleResult?.error ?? 'Unknown upload error'}`,
            });
          }
        } catch {
          nextResults.push({
            line,
            status: 'error',
            message: 'Error: Network failure while uploading this line.',
          });
          errorCount += 1;
        }

        bulkProcessedCount += 1;
        bulkProgressPercent = Math.round((bulkProcessedCount / bulkTotalCount) * 100);
        bulkResults = [...nextResults];
        const remaining = Math.max(0, bulkTotalCount - bulkProcessedCount);
        bulkStatusText = `Processed ${bulkProcessedCount}/${bulkTotalCount}. ${remaining} remaining. ${successCount} succeeded, ${errorCount} failed.`;
      }

      if (!bulkStatusText && bulkTotalCount > 0) {
        bulkStatusText = `Processed ${bulkProcessedCount}/${bulkTotalCount}. ${successCount} succeeded, ${errorCount} failed.`;
      }
      if (errorCount > 0) {
        bulkErrorText = `${errorCount} item${errorCount === 1 ? '' : 's'} failed. See details below.`;
      }
      await Promise.all([loadAllMedia(), loadMedia()]);
    } catch {
      adminError = 'Bulk upload failed.';
      bulkErrorText = adminError;
      bulkStatusText = 'Upload failed before completion.';
    } finally {
      bulkBusy = false;
      if (!bulkStatusText && bulkTotalCount > 0) {
        bulkStatusText = `Processed ${bulkProcessedCount}/${bulkTotalCount}.`;
      }
    }
  }

  async function fetchLaunchBoxGameData() {
    launchboxFetchError = '';
    adminError = '';
    adminMessage = '';
    if (!canFetchLaunchBoxGameData()) {
      launchboxFetchError = 'Enter a game title and select a platform first.';
      return;
    }

    launchboxFetchBusy = true;
    try {
      const response = await fetch('/api/launchbox/game-data', {
        method: 'POST',
        headers: mediaHeaders(),
        body: JSON.stringify({
          title: (adminForm.title ?? '').trim(),
          platform: ((adminForm.platform ?? '').trim() || (selectedConsole ?? '').trim()),
          item_id: adminForm.id ?? null,
        }),
      });
      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        adminError = 'Session expired. Log in again.';
        return;
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        launchboxFetchError = data?.detail ?? 'LaunchBox could not find matching game data.';
        return;
      }

      const sourceLabel = formatDataSourceLabel(data?.data_source);

      adminForm = {
        ...adminForm,
        title: data?.title ?? adminForm.title,
        // Keep the selected platform from the form to avoid dropdown mismatches
        // when LaunchBox returns labels that do not exist in local console options.
        platform: adminForm.platform,
        publishers: Array.isArray(data?.publishers) ? normalizeSelectionValues(data.publishers) : adminForm.publishers,
        gameGenres: Array.isArray(data?.gameGenres) ? normalizeSelectionValues(data.gameGenres) : adminForm.gameGenres,
        release_date: normalizeDateForInput(data?.release_date) || adminForm.release_date,
        year_released: data?.year_released ? String(data.year_released) : adminForm.year_released,
        rating: normalizeGameRating(data?.rating ?? adminForm.rating),
        players: data?.players ? String(data.players) : adminForm.players,
        cooperative: data?.cooperative ?? adminForm.cooperative,
        notes: data?.notes ?? adminForm.notes,
        cover_image: data?.coverImage ?? adminForm.cover_image,
        spine_image: data?.spineImage ?? adminForm.spine_image,
        disc_image: data?.discImage ?? adminForm.disc_image,
      };

      if (data?.publishers?.length) {
        adminPublisherChoice = '';
      }
      if (data?.gameGenres?.length) {
        adminGameGenreChoice = '';
      }
      adminMessage = `Game data loaded from ${sourceLabel}.`;
    } catch {
      launchboxFetchError = 'Could not fetch game data from available sources.';
    } finally {
      launchboxFetchBusy = false;
    }
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
    bootRevealAt = 9;
    bootTextVisible = false;
    bootStarted = false;
    bootAudioFadeInMs = 1000;
    clearBootRescueTimer();
    clearBootPlaybackRetry();
    clearBootHardFailTimer();

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
    if (stage !== 'boot') {
      clearBootRescueTimer();
      clearBootPlaybackRetry();
      clearBootHardFailTimer();
    }

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
    brokenSpineIds = new Set();
    brokenDiscIds = new Set();

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

  function clearBootRescueTimer() {
    if (bootRescueTimeout) {
      clearTimeout(bootRescueTimeout);
      bootRescueTimeout = null;
    }
  }

  function clearBootPlaybackRetry() {
    if (bootPlaybackRetryInterval) {
      clearInterval(bootPlaybackRetryInterval);
      bootPlaybackRetryInterval = null;
    }
  }

  function clearBootHardFailTimer() {
    if (bootHardFailTimeout) {
      clearTimeout(bootHardFailTimeout);
      bootHardFailTimeout = null;
    }
  }

  function armBootHardFailTimer() {
    clearBootHardFailTimer();
    bootHardFailTimeout = setTimeout(() => {
      if (stage !== 'boot' || bootTextVisible) return;
      bootError = !bootVideoRef || bootVideoRef.readyState < 1;
      bootTextVisible = true;
      bootStarted = false;
      clearBootRescueTimer();
      clearBootPlaybackRetry();
    }, BOOT_HARD_FAIL_OPEN_MS);
  }

  function armBootRescueTimer() {
    clearBootRescueTimer();
    const observedTime = bootVideoRef?.currentTime ?? 0;
    bootRescueTimeout = setTimeout(() => {
      if (stage !== 'boot' || bootTextVisible) return;

      if (
        bootVideoRef
        && !bootVideoRef.error
        && bootVideoRef.readyState >= 2
        && bootVideoRef.currentTime > observedTime + 0.15
      ) {
        armBootRescueTimer();
        return;
      }

      bootError = !bootVideoRef || bootVideoRef.readyState < 1;
      bootTextVisible = true;
      bootStarted = false;
      clearBootPlaybackRetry();
    }, BOOT_RESCUE_TIMEOUT_MS);
  }

  function armBootPlaybackRetry() {
    clearBootPlaybackRetry();
    bootPlaybackRetryInterval = setInterval(() => {
      if (stage !== 'boot' || bootError || bootTextVisible || !bootVideoRef) {
        clearBootPlaybackRetry();
        return;
      }

      if (!bootVideoRef.paused) return;
      if (bootVideoRef.error || bootVideoRef.readyState < 2) return;

      void bootVideoRef.play().catch(() => {
        // Ignore transient autoplay-policy or buffering failures and retry.
      });
    }, 1200);
  }

  async function startBoot() {
    if (!bootVideoRef || bootStarted) return;
    bootStarted = true;
    armBootRescueTimer();
    armBootPlaybackRetry();
    armBootHardFailTimer();

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
      clearBootRescueTimer();
      clearBootPlaybackRetry();
      clearBootHardFailTimer();
    }
  }

  function skipBootIntro() {
    if (stage !== 'boot' || bootTextVisible) return;

    unlockBootAudio();
    bootResumeAtSix = true;
    bootStartAt = BOOT_SKIP_TIME;

    if (!bootVideoRef) {
      bootTextVisible = true;
      clearBootRescueTimer();
      clearBootPlaybackRetry();
      clearBootHardFailTimer();
      return;
    }

    bootVideoRef.currentTime = BOOT_SKIP_TIME;
    bootTextVisible = true;
    clearBootRescueTimer();
    clearBootPlaybackRetry();
    clearBootHardFailTimer();

    if (bootVideoRef.paused) {
      void bootVideoRef.play().catch(() => {
        bootError = true;
        bootTextVisible = true;
        bootStarted = false;
        clearBootRescueTimer();
        clearBootPlaybackRetry();
        clearBootHardFailTimer();
      });
    }
  }

  async function queueBootStart() {
    armBootRescueTimer();
    armBootPlaybackRetry();
    armBootHardFailTimer();
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await tick();
      if (bootVideoRef) {
        await startBoot();
        return;
      }
      await sleep(25);
    }

    if (stage === 'boot') {
      bootError = true;
      bootTextVisible = true;
      bootStarted = false;
    }
    clearBootRescueTimer();
    clearBootPlaybackRetry();
    clearBootHardFailTimer();
  }

  function isBootSpaceKey(event: KeyboardEvent) {
    return event.code === 'Space' || event.key === ' ' || event.key === 'Spacebar';
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
    detailsManualRotateY = 0;
    detailsSpinPaused = false;
    detailsDragActive = false;
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

  function resetAdminForm(category: Category = libraryAdminTab === 'music' ? 'Music' : 'Games') {
    adminEditingId = null;
    adminContextItem = null;
    adminPublisherChoice = '';
    adminGameGenreChoice = '';
    adminMusicGenreChoice = '';
    adminForm = emptyAdminForm(category);
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

  async function loadSystemsFromAPI() {
    try {
      const response = await fetch('/api/systems');
      if (response.ok) {
        const systems = await response.json();
        editableSystems = systems.map((s: any) => ({
          id: s.id,
          name: s.name,
          shortName: s.shortName,
          logo: s.logo,
          logoImage: normalizeSystemLogoImage(s.logoImage),
          caseType: s.caseType ?? undefined,
          appearancePreset: s.appearancePreset ?? null,
          isCartridgeInferred: Boolean(s.isCartridgeInferred),
          displayOrder: s.displayOrder ?? 0,
        }));
      } else {
        console.warn('Failed to load systems from API, using defaults');
        loadSystemsFromStorage();
      }
    } catch (error) {
      console.warn('Error loading systems from API:', error);
      loadSystemsFromStorage();
    }
  }

  function initializeDefaultSystems(): EditableSystem[] {
    return [
      { id: 'ps2', name: 'PlayStation 2', shortName: 'PS2', logo: 'PS2',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg', caseType: 'disc', appearancePreset: 'ps2' },
      { id: 'ps3', name: 'PlayStation 3', shortName: 'PS3', logo: 'PS3',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg', caseType: 'disc', appearancePreset: 'ps3' },
      { id: 'ps4', name: 'PlayStation 4', shortName: 'PS4', logo: 'PS4',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg', caseType: 'disc', appearancePreset: 'ps4' },
      { id: 'nds', name: 'Nintendo DS', shortName: 'NDS', logo: 'NDS',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg', caseType: 'cartridge', appearancePreset: 'nds' },
      { id: '3ds', name: 'Nintendo 3DS', shortName: '3DS', logo: '3DS',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg', caseType: 'cartridge', appearancePreset: '3ds' },
      { id: 'gb', name: 'GameBoy', shortName: 'GB', logo: 'GB',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg', caseType: 'cartridge', appearancePreset: 'gb' },
      { id: 'gc', name: 'GameCube', shortName: 'GC', logo: 'GC',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg', caseType: 'disc', appearancePreset: 'gamecube' },
      { id: 'wii', name: 'Wii', shortName: 'Wii', logo: 'Wii',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg', caseType: 'disc', appearancePreset: 'wii' },
      { id: 'xbox', name: 'Xbox', shortName: 'XBX', logo: 'XBX',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg', caseType: 'disc', appearancePreset: 'xbox' },
      { id: 'xbox360', name: 'Xbox 360', shortName: '360', logo: '360',
        logoImage: 'https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg', caseType: 'disc', appearancePreset: 'xbox360' },
    ];
  }

  function persistSystems() {
    localStorage.setItem('ps2-editable-systems', JSON.stringify(editableSystems));
  }

  function inferImageMimeTypeFromBase64(base64Data: string) {
    try {
      const binary = atob(base64Data.trim());
      if (binary.startsWith('\x89PNG\r\n\x1a\n')) return 'image/png';
      if (binary.startsWith('\xff\xd8\xff')) return 'image/jpeg';
      if (binary.startsWith('GIF87a') || binary.startsWith('GIF89a')) return 'image/gif';
      if (binary.startsWith('RIFF') && binary.slice(8, 12) === 'WEBP') return 'image/webp';
      if (binary.includes('<svg') || binary.includes('<?xml')) return 'image/svg+xml';
    } catch {
      return 'image/svg+xml';
    }

    return 'image/png';
  }

  function normalizeSystemLogoImage(logoImage: string | null | undefined) {
    if (!logoImage) return null;
    if (logoImage.startsWith('data:image/')) return logoImage;
    if (logoImage.startsWith('data:')) return logoImage;
    return `data:${inferImageMimeTypeFromBase64(logoImage)};base64,${logoImage}`;
  }

  async function addSystem() {
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
    
    try {
      const response = await fetch('/api/systems', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${adminToken}` },
        body: JSON.stringify({
          id,
          name,
          shortName: name.slice(0, 3).toUpperCase(),
          logo: name.slice(0, 3).toUpperCase(),
          logoImageUrl: newSystemIcon.trim() || '',
          caseType: newSystemCaseType || undefined,
        }),
      });
      if (response.ok) {
        await loadSystemsFromAPI();
        newSystemName = '';
        newSystemIcon = '';
        newSystemCaseType = '';
      } else {
        const error = await response.json();
        systemError = error.detail || 'Failed to add system';
      }
    } catch (error) {
      systemError = `Error adding system: ${error}`;
    }
  }

  async function removeSystem(systemId: string) {
    const removedSystem = editableSystems.find((s) => s.id === systemId);
    try {
      const response = await fetch(`/api/systems/${systemId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${adminToken}` },
      });
      if (response.ok) {
        if (removedSystem && selectedConsole === removedSystem.name) {
          selectedConsole = null;
          if (stage === 'library' && category === 'Games') {
            stage = 'console';
          }
        }
        await loadSystemsFromAPI();
      } else {
        const error = await response.json();
        systemError = error.detail || 'Failed to delete system';
      }
    } catch (error) {
      systemError = `Error deleting system: ${error}`;
    }
  }

  async function updateSystem(systemId: string, updates: Partial<EditableSystem> & { caseType?: EditableSystem['caseType'] | '' }) {
    try {
      const system = editableSystems.find((s) => s.id === systemId);
      if (!system) return;
      
      const response = await fetch(`/api/systems/${systemId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${adminToken}` },
        body: JSON.stringify({
          name: updates.name || system.name,
          shortName: updates.shortName || system.shortName,
          logo: updates.logo || system.logo,
          logoImageUrl: updates.logoImage || '',
          caseType: updates.caseType === '' ? 'auto' : (updates.caseType ?? system.caseType ?? undefined),
        }),
      });
      if (response.ok) {
        await loadSystemsFromAPI();
      } else {
        const error = await response.json();
        systemError = error.detail || 'Failed to update system';
      }
    } catch (error) {
      systemError = `Error updating system: ${error}`;
    }
  }

  function startEditSystem(systemId: string) {
    const system = editableSystems.find((s) => s.id === systemId);
    if (system) {
      editingSystemId = systemId;
      editingSystemName = system.name;
      editingSystemIcon = system.logoImage || '';
      editingSystemCaseType = (system.caseType as '' | 'disc' | 'cartridge' | 'hybrid') ?? '';
    }
  }

  function cancelEditSystem() {
    editingSystemId = null;
    editingSystemName = '';
    editingSystemIcon = '';
    editingSystemCaseType = '';
  }

  let draggedSystemId: string | null = null;

  function handleSystemDragStart(event: DragEvent, systemId: string) {
    draggedSystemId = systemId;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
    }
  }

  function handleSystemDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
  }

  async function handleSystemDrop(event: DragEvent, targetSystemId: string) {
    event.preventDefault();
    if (!draggedSystemId || draggedSystemId === targetSystemId) {
      draggedSystemId = null;
      return;
    }

    const draggedIndex = editableSystems.findIndex((s) => s.id === draggedSystemId);
    const targetIndex = editableSystems.findIndex((s) => s.id === targetSystemId);

    if (draggedIndex === -1 || targetIndex === -1) {
      draggedSystemId = null;
      return;
    }

    // Reorder locally
    const newSystems = [...editableSystems];
    const [draggedSystem] = newSystems.splice(draggedIndex, 1);
    newSystems.splice(targetIndex, 0, draggedSystem);
    editableSystems = newSystems;

    // Persist new order to backend
    try {
      await fetch('/api/systems/reorder', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${adminToken}` },
        body: JSON.stringify({
          order: editableSystems.map((s) => s.id),
        }),
      });
    } catch (error) {
      console.warn('Failed to persist system order:', error);
    }

    draggedSystemId = null;
  }

  function handleSystemDragEnd() {
    draggedSystemId = null;
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
      caseType: editingSystemCaseType,
    });
    cancelEditSystem();
    systemError = '';
  }

  async function handleLogoUpload(event: Event, isNewSystem: boolean = false) {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      if (isNewSystem) {
        newSystemIcon = result;
      } else {
        editingSystemIcon = result;
      }
    };
    reader.readAsDataURL(file);
  }

  function canFetchSystemLogo(isNewSystem: boolean = false) {
    const name = isNewSystem ? newSystemName : editingSystemName;
    return name.trim().length > 0;
  }

  function resolveKnownSystemLogoUrl(systemName: string) {
    const key = normalizeConsoleKey(systemName);
    const knownLogos: Record<string, string> = {
      ps2: 'https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg',
      playstation2: 'https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg',
      ps3: 'https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg',
      playstation3: 'https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg',
      ps4: 'https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg',
      playstation4: 'https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg',
      nds: 'https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg',
      nintendods: 'https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg',
      '3ds': 'https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg',
      nintendo3ds: 'https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg',
      gb: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg',
      gameboy: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg',
      gc: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg',
      gamecube: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg',
      wii: 'https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg',
      xbox: 'https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg',
      xbox360: 'https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg',
    };

    if (knownLogos[key]) return knownLogos[key];
    for (const [lookupKey, url] of Object.entries(knownLogos)) {
      if (lookupKey.includes(key) || key.includes(lookupKey)) return url;
    }
    return null;
  }

  async function imageUrlToDataUri(imageUrl: string) {
    const response = await fetch(imageUrl);
    if (!response.ok) {
      throw new Error('Image request failed');
    }
    const blob = await response.blob();
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(new Error('Could not read image data'));
      reader.readAsDataURL(blob);
    });
  }

  async function fetchSystemLogoFromKnownSources(systemName: string) {
    const logoUrl = resolveKnownSystemLogoUrl(systemName);
    if (!logoUrl) return null;
    return await imageUrlToDataUri(logoUrl);
  }

  async function fetchSystemLogo(isNewSystem: boolean = false) {
    if (systemLogoFetchBusy) return;
    systemLogoFetchError = '';
    systemError = '';

    const name = (isNewSystem ? newSystemName : editingSystemName).trim();
    if (!name) {
      systemLogoFetchError = 'Enter a system name first.';
      return;
    }

    systemLogoFetchBusy = true;
    try {
      const apiEndpoints = ['/api/logo/system-data', '/api/system-logo-data', '/api/systems/logo-data'];
      let logoImage: string | null = null;
      let apiError = '';

      for (const endpoint of apiEndpoints) {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: mediaHeaders(),
          body: JSON.stringify({ name }),
        });

        if (response.status === 401) {
          adminToken = '';
          localStorage.removeItem('ps2-admin-token');
          systemError = 'Session expired. Log in again.';
          return;
        }

        const data = await response.json().catch(() => null);
        if (response.ok && typeof data?.logoImage === 'string') {
          logoImage = data.logoImage;
          break;
        }
        apiError = data?.detail ?? apiError;
      }

      if (!logoImage) {
        logoImage = await fetchSystemLogoFromKnownSources(name);
      }

      if (!logoImage) {
        systemLogoFetchError = apiError || 'Could not fetch system logo image.';
        return;
      }

      if (isNewSystem) {
        newSystemIcon = logoImage;
      } else {
        editingSystemIcon = logoImage;
      }
    } catch {
      systemLogoFetchError = 'Could not fetch system logo image.';
    } finally {
      systemLogoFetchBusy = false;
    }
  }

  async function handleGameArtUpload(event: Event, field: GameArtField) {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      adminError = 'Please upload an image file.';
      target.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      adminForm = {
        ...adminForm,
        [field]: result,
      } as AdminForm;
      adminError = '';
      launchboxFetchError = '';
      if (field === 'cover_image') {
        adminMessage = 'Custom box art loaded.';
      } else if (field === 'spine_image') {
        adminMessage = 'Custom spine art loaded.';
      } else {
        adminMessage = 'Custom disc/cart art loaded.';
      }
    };
    reader.readAsDataURL(file);
    target.value = '';
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
    resetAdminForm(category === 'Music' ? 'Music' : 'Games');
    adminForm = {
      ...adminForm,
      platform: category === 'Music' ? '' : (selectedConsole ?? 'PlayStation 2'),
    };
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

    resetAdminForm(tab === 'music' ? 'Music' : 'Games');
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
    const isGames = item.category === 'Games';
    adminForm = {
      id: item.id,
      title: item.title,
      category: item.category === 'Music' ? 'Music' : 'Games',
      platform: item.platform ?? '',
      publishers: isGames ? splitDelimitedValues(item.publisher) : [],
      gameGenres: isGames ? splitDelimitedValues(item.genres ?? item.genre) : [],
      release_date: normalizeDateForInput(item.release_date) || (item.year_released ? `${item.year_released}-01-01` : ''),
      year_released: item.year_released ? String(item.year_released) : '',
      rating: normalizeGameRating(item.rating),
      players: item.players ? String(item.players) : '',
      cooperative: isGames ? (item.cooperative ?? 'No') : 'No',
      artist: item.artist ?? '',
      musicGenre: item.category === 'Music' ? item.genre : '',
      cover_image: item.cover_image ?? null,
      spine_image: item.spine_image ?? null,
      disc_image: item.disc_image ?? null,
      notes: item.notes ?? '',
    };
    adminPublisherChoice = '';
    adminGameGenreChoice = '';
    adminMusicGenreChoice = item.category === 'Music' ? item.genre : '';
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
    const isGames = adminForm.category === 'Games';
    if (!adminForm.title.trim()) {
      adminError = 'Title is required.';
      return;
    }
    if (isGames && adminForm.gameGenres.length === 0) {
      adminError = 'Select at least one genre for the game.';
      return;
    }
    if (!isGames && !adminForm.musicGenre.trim()) {
      adminError = 'Select a genre for the music item.';
      return;
    }

    const normalizedTitle = normalizeGameTitle(adminForm.title);

    adminBusy = true;
    const releaseDate = adminForm.release_date ? adminForm.release_date.trim() : '';
    const releaseYear = releaseDate ? Number(releaseDate.slice(0, 4)) : (adminForm.year_released ? Number(adminForm.year_released) : null);
    const existingItem = adminContextItem;
    const gameGenres = isGames ? normalizeSelectionValues(adminForm.gameGenres) : [];
    const publishers = isGames ? normalizeSelectionValues(adminForm.publishers) : [];
    const payload = {
      title: normalizedTitle || adminForm.title.trim(),
      category: adminForm.category,
      platform: isGames ? adminForm.platform.trim() || null : null,
      genre: isGames ? (gameGenres[0] ?? '') : adminForm.musicGenre.trim(),
      genres: isGames ? combineSelectionValues(gameGenres) : null,
      release_date: releaseDate || null,
      year_released: releaseYear,
      rating: isGames ? normalizeGameRating(adminForm.rating) : null,
      players: isGames && adminForm.players ? Number(adminForm.players) : null,
      cooperative: isGames ? adminForm.cooperative : null,
      artist: isGames ? null : adminForm.artist.trim() || null,
      publisher: isGames ? combineSelectionValues(publishers) : existingItem?.publisher ?? null,
      format: existingItem?.format ?? null,
      region: existingItem?.region ?? null,
      cover_image: isGames ? adminForm.cover_image ?? existingItem?.cover_image ?? null : existingItem?.cover_image ?? null,
      spine_image: isGames ? adminForm.spine_image ?? existingItem?.spine_image ?? null : existingItem?.spine_image ?? null,
      disc_image: isGames ? adminForm.disc_image ?? existingItem?.disc_image ?? null : existingItem?.disc_image ?? null,
      tags: existingItem?.tags ?? null,
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

  function normalizeConsoleLogoScale(e: Event) {
    const img = e.currentTarget as HTMLImageElement;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;
    const ratio = img.naturalWidth / img.naturalHeight;
    // Slightly scale down medium-wide wordmarks to keep icon sizes visually even.
    const scale = ratio >= 2.3 ? 0.92 : ratio >= 1.9 ? 0.95 : ratio >= 1.5 ? 0.98 : 1;
    img.style.setProperty('--logo-optical-scale', String(scale));
  }

  function markCoverBroken(itemId: number) {
    const next = new Set(brokenCoverIds);
    next.add(itemId);
    brokenCoverIds = next;
  }

  function markSpineBroken(itemId: number) {
    const next = new Set(brokenSpineIds);
    next.add(itemId);
    brokenSpineIds = next;
  }

  function markDiscBroken(itemId: number) {
    const next = new Set(brokenDiscIds);
    next.add(itemId);
    brokenDiscIds = next;
  }

  function handleGlobalBootKeydown(event: KeyboardEvent) {
    if (!isBootSpaceKey(event)) return;
    if (stage !== 'boot' || bootTextVisible) return;
    event.preventDefault();
    unlockBootAudio();
    skipBootIntro();
  }

  function handleGlobalEscapeKeydown(event: KeyboardEvent) {
    if (event.key !== 'Escape') return;
    if (isTransitioning) return;

    if (launchboxArtPickerOpen) {
      event.preventDefault();
      closeLaunchboxArtPicker();
      return;
    }

    if (confirmOpen) {
      event.preventDefault();
      closeConfirm();
      return;
    }

    if (playersDropdownOpen) {
      event.preventDefault();
      playersDropdownOpen = false;
      return;
    }

    if (librarySearchOpen && !librarySearch.trim()) {
      event.preventDefault();
      librarySearchOpen = false;
      return;
    }

    if (adminOpen) {
      event.preventDefault();
      adminOpen = false;
      return;
    }

    if (stage === 'details') {
      event.preventDefault();
      closeDetails();
      return;
    }

    if (stage !== 'boot') {
      event.preventDefault();
      backAction();
    }
  }

  onMount(async () => {
    const savedToken = localStorage.getItem('ps2-admin-token');
    if (savedToken) {
      adminToken = savedToken;
    }
    await loadSystemsFromAPI();

    await loadAllMedia();
    history.replaceState(currentHistoryState(), '');
    window.addEventListener('popstate', handlePopState);
    window.addEventListener('keydown', handleGlobalBootKeydown);
    window.addEventListener('keydown', handleGlobalEscapeKeydown);
    void queueBootStart();

    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('keydown', handleGlobalBootKeydown);
      window.removeEventListener('keydown', handleGlobalEscapeKeydown);
      clearBootRescueTimer();
      clearBootPlaybackRetry();
      clearBootHardFailTimer();
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
      bootRevealAt = 9;
      bootError = false;
      bootTextVisible = false;
      void queueBootStart();
    } else {
      clearBootRescueTimer();
      clearBootPlaybackRetry();
      clearBootHardFailTimer();
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
      if (event.key === 'Enter') {
        event.preventDefault();
        toggleBootMute();
        return;
      }
      if (event.code === 'Space' || event.key === ' ' || event.key === 'Spacebar') {
        event.preventDefault();
        unlockBootAudio();
        skipBootIntro();
      }
    }}
  >
    {#if !bootError}
      <video
        bind:this={bootVideoRef}
        class="boot-video"
        autoplay
        preload="auto"
        muted={bootMuted}
        playsinline
        webkit-playsinline="true"
        on:loadedmetadata={() => {
          if (bootVideoRef) {
            bootVideoRef.currentTime = Math.max(0, bootResumeAtSix ? BOOT_SKIP_TIME : bootStartAt);
            if (!bootResumeAtSix) {
              const duration = Number.isFinite(bootVideoRef.duration) ? bootVideoRef.duration : 9;
              bootRevealAt = Math.min(9, Math.max(1.8, duration - 0.35));
            }
          }
          if (stage === 'boot' && !bootTextVisible) {
            armBootRescueTimer();
            armBootPlaybackRetry();
          }
        }}
        on:timeupdate={() => {
          if (!bootVideoRef) return;

          if (bootVideoRef.currentTime >= BOOT_LOOP_CEILING_TIME) {
            bootVideoRef.currentTime = BOOT_SKIP_TIME;
            if (bootVideoRef.paused) {
              void bootVideoRef.play().catch(() => {
                // Keep the fallback flow alive when replaying the loop window fails.
              });
            }
          }

          if (bootResumeAtSix) {
            if (bootVideoRef.currentTime >= BOOT_SKIP_TIME) {
              bootTextVisible = true;
              clearBootRescueTimer();
              clearBootPlaybackRetry();
              clearBootHardFailTimer();
            }
          } else {
            if (bootVideoRef.currentTime >= bootRevealAt) {
              bootTextVisible = true;
              clearBootRescueTimer();
              clearBootPlaybackRetry();
              clearBootHardFailTimer();
            }
          }
        }}
        on:playing={() => {
          if (stage !== 'boot') return;
          armBootRescueTimer();
        }}
        on:waiting={() => {
          if (stage === 'boot' && !bootTextVisible) {
            armBootRescueTimer();
          }
        }}
        on:stalled={() => {
          if (stage === 'boot' && !bootTextVisible) {
            armBootRescueTimer();
          }
        }}
        on:suspend={() => {
          if (stage === 'boot' && !bootTextVisible) {
            armBootRescueTimer();
          }
        }}
        on:ended={() => {
          bootTextVisible = true;
          clearBootRescueTimer();
          clearBootPlaybackRetry();
          clearBootHardFailTimer();
        }}
        on:error={() => {
          bootError = true;
          bootTextVisible = true;
          bootStarted = false;
          clearBootRescueTimer();
          clearBootPlaybackRetry();
          clearBootHardFailTimer();
        }}
      >
        <source src="https://media.theavenoircollection.com/ps2-intro.mp4" type="video/mp4" />
        <track kind="captions" srclang="en" label="English" src="/ps2-intro.en.vtt" />
      </video>
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
      <div class="boot-brand" transition:fade={{ duration: 500 }}>
        <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="site-brand-logo site-brand-logo--boot" draggable="false" />
      </div>
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
      <p class="footer-content">
        <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="footer-brand-logo" draggable="false" />
        <span class="footer-delimiter">|</span>
        <span>&copy; 2026 ALEX PRITT</span>
      </p>
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
            <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="site-brand-logo site-brand-logo--header" draggable="false" />
          </div>
          <div class="hud-right console-header-count console-header-right">
            {#if consoleHeaderOption?.logoImage && hoveredConsoleFadeVisible}
              <div class="console-hover-meta">
                <img
                  src={consoleHeaderOption.logoImage}
                  alt={consoleHeaderOption.name}
                  class="console-header-logo console-header-logo--hover"
                  draggable="false"
                />
                <span class="console-header-copy console-header-count-copy console-header-subcopy">{hoveredConsoleCountLabel}</span>
              </div>
            {:else}
              <div class="console-hover-meta console-hover-meta--static">
                <span class="console-header-copy console-header-count-copy console-header-subcopy">{consoleLibraryCountLabel}</span>
              </div>
            {/if}
          </div>
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
                  on:load={normalizeConsoleLogoScale}
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
            <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="site-brand-logo site-brand-logo--header" draggable="false" />
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

          {#if stage === 'library' && category === 'Games' && selectedLibraryConsole?.logoImage}
            <div class="library-hud-right console-header-right">
              <div class="console-hover-meta">
                <img src={selectedLibraryConsole.logoImage} alt={selectedLibraryConsole.name} class="console-header-logo" draggable="false" />
                <span class="console-header-copy console-header-count-copy library-header-subcopy">{libraryHeaderRight}</span>
              </div>
            </div>
          {:else if libraryHeaderRight}
            <div class="library-hud-right library-header-right-text">{libraryHeaderRight}</div>
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
                    <span
                      class={`disc-case${caseGeometryClass(item.platform)}`}
                      aria-hidden="true"
                    >
                      <span class="disc-case-spine">
                        {#if item.spine_image && !brokenSpineIds.has(item.id)}
                          <img src={item.spine_image} alt="" class="spine-image spine-image--bg" aria-hidden="true" draggable="false" />
                          <img src={item.spine_image} alt="" class="spine-image spine-image--fg" aria-hidden="true" draggable="false" on:error={() => markSpineBroken(item.id)} />
                        {/if}
                      </span>
                      <span class="disc-case-front">
                        {#if item.cover_image && !brokenCoverIds.has(item.id)}
                          <img src={item.cover_image} alt="" class="library-art library-art--bg" loading="lazy" aria-hidden="true" />
                          <img src={item.cover_image} alt={item.title} class="library-art library-art--fg" loading="lazy" on:error={() => markCoverBroken(item.id)} />
                        {:else}
                          <span class="library-fallback">{iconInitials(item.title)}</span>
                        {/if}
                      </span>
                      <span class={`disc-case-disc ${discBackingClass(item)}${isCartridgePlatform(item.platform) ? ' disc-case-disc--cartridge' : ''}`}>
                        {#if item.disc_image && !brokenDiscIds.has(item.id)}
                          <img src={item.disc_image} alt="" class={`disc-image${isCartridgePlatform(item.platform) ? ' disc-image--cartridge' : ''}`} aria-hidden="true" draggable="false" on:error={() => markDiscBroken(item.id)} />
                        {:else if isCartridgePlatform(item.platform) && item.cover_image && !brokenCoverIds.has(item.id)}
                          <img src={item.cover_image} alt="" class="disc-image disc-image--cartridge" aria-hidden="true" draggable="false" on:error={() => markCoverBroken(item.id)} />
                        {:else}
                          <span class="disc-shell-fallback">{iconInitials(item.title)}</span>
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
        <button type="button" class="popup-close details-close" aria-label="Close details" on:click={closeDetails}>×</button>
        {#if detailsConsoleLogo}
          <img src={detailsConsoleLogo} alt="" class="details-console-logo-bg" aria-hidden="true" draggable="false" />
        {/if}
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
                        {#if selectedItem.disc_image && !brokenDiscIds.has(selectedItem.id)}
                          <img src={selectedItem.disc_image} alt={selectedItem.title} class="details-cartridge-art" draggable="false" on:error={() => markDiscBroken(selectedItem.id)} />
                        {:else if selectedItem.cover_image && !brokenCoverIds.has(selectedItem.id)}
                          <img src={selectedItem.cover_image} alt={selectedItem.title} class="details-cartridge-art" draggable="false" on:error={() => markCoverBroken(selectedItem.id)} />
                        {:else}
                          <div class="details-cartridge-fallback">{iconInitials(selectedItem.title)}</div>
                        {/if}
                      </div>
                    </div>
                    <div class="details-disc-flip-face details-disc-flip-face--back" aria-hidden="true">
                      <div class={`details-cartridge details-cartridge--back ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
                        <span class="details-cartridge-back-panel"></span>
                        <span class="details-cartridge-contacts"></span>
                      </div>
                    </div>
                  </div>
                {:else}
                  <div class="details-disc-flipper">
                    <div class="details-disc-flip-face details-disc-flip-face--front">
                      <div class={`details-game-disc ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if selectedItem.disc_image && !brokenDiscIds.has(selectedItem.id)}
                          <img src={selectedItem.disc_image} alt={selectedItem.title} class="details-game-disc-art" draggable="false" on:error={() => markDiscBroken(selectedItem.id)} />
                        {:else}
                          <div class="details-game-disc-fallback">{iconInitials(selectedItem.title)}</div>
                        {/if}
                        <span class="disc-hole"></span>
                        <span class="details-game-disc-shine"></span>
                      </div>
                    </div>
                    <div class="details-disc-flip-face details-disc-flip-face--back" aria-hidden="true">
                      <div class={`details-game-disc ${discBackingClass(selectedItem)}`}>
                        <span class="disc-shell-backing"></span>
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
          <p class="details-line-2">{selectedItem.title}</p>
          <div class="details-tags" aria-label="Details tags">
            {#each detailTags(selectedItem) as tag}
              <button
                type="button"
                class={`details-tag details-tag--${tag.tone}`}
                on:click={() => applyDetailTagFilter(tag.query)}
              >
                {tag.label}
              </button>
            {/each}
          </div>
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

    {#if launchboxArtPickerOpen}
      <div class="launchbox-art-picker-overlay" role="dialog" aria-modal="true" aria-labelledby="launchbox-art-picker-title" transition:popupOverlayTransition>
        <button type="button" class="launchbox-art-picker-backdrop" aria-label="Close LaunchBox art selector" on:click={closeLaunchboxArtPicker}></button>
        <div class="launchbox-art-picker-panel" transition:popupPanelTransition>
          <button type="button" class="popup-close" aria-label="Close LaunchBox art selector" on:click={closeLaunchboxArtPicker}>×</button>
          <div class="launchbox-art-picker-header">
            <h3 id="launchbox-art-picker-title">Choose {adminArtLabel(launchboxArtPickerField ?? 'cover_image')}</h3>
          </div>
          {#if launchboxArtPickerBusy}
            <p class="launchbox-art-picker-state">Loading art options from available sources...</p>
          {:else if launchboxArtPickerError}
            <p class="admin-error launchbox-art-picker-state">{launchboxArtPickerError}</p>
          {:else if launchboxArtOptions.length}
            <div class="launchbox-art-picker-grid">
              {#each launchboxArtOptions as artOption, index}
                <button
                  type="button"
                  class="launchbox-art-picker-option"
                  on:click={() => chooseLaunchboxArtOption(artOption)}
                  aria-label={`Select ${adminArtLabel(launchboxArtPickerField ?? 'cover_image')} option ${index + 1}`}
                >
                  <img src={artOption} alt={`LaunchBox art option ${index + 1}`} loading="lazy" />
                </button>
              {/each}
            </div>
          {:else}
            <p class="launchbox-art-picker-state">No options available.</p>
          {/if}
        </div>
      </div>
    {/if}

    {#if confirmOpen && confirmItem}
      <div class="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title" transition:popupOverlayTransition>
        <button type="button" class="confirm-backdrop" aria-label="Close confirmation" on:click={closeConfirm}></button>
        <div class="confirm-panel" transition:popupPanelTransition>
          <button type="button" class="popup-close" aria-label="Close confirmation" on:click={closeConfirm}>×</button>
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
  <div class="admin-overlay" role="dialog" aria-modal="true" transition:popupOverlayTransition>
    <button type="button" class="admin-backdrop" aria-label="Close admin panel" on:click={() => (adminOpen = false)}></button>
    <div class="admin-panel" transition:popupPanelTransition>
      {#if !isAdmin}
        <div class="admin-header">
          <h2>Admin Access</h2>
          <button type="button" class="popup-close" aria-label="Close admin panel" on:click={() => (adminOpen = false)}>×</button>
        </div>
        <div class="admin-login">
          <label for="admin-password">Password</label>
          <input id="admin-password" type="password" bind:value={adminPassword} placeholder="Enter password..." on:keydown={(e) => e.key === 'Enter' && adminLogin()} />
          <button type="button" disabled={adminBusy} on:click={adminLogin}>Log In</button>
        </div>
      {:else}
        {#if adminMode === 'hub'}
          <!-- ADMIN HUB VIEW -->
          <div class="admin-header">
            <h2>Admin Hub</h2>
            <button type="button" class="popup-close" aria-label="Close admin panel" on:click={() => (adminOpen = false)}>×</button>
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
            <button type="button" class="popup-close" aria-label="Close admin panel" on:click={() => (adminOpen = false)}>×</button>
          </div>

          <div class="admin-layout systems-layout">
            <!-- Systems List (Left) -->
            <div class="admin-list-pane">
              <div class="systems-add-section">
                <h4>Add New System</h4>
                <div class="systems-add-row">
                  <div class="form-field">
                    <label for="new-system-name">System Name</label>
                    <input id="new-system-name" type="text" bind:value={newSystemName} placeholder="e.g., PlayStation 5" />
                  </div>
                  <div class="form-field">
                    <label for="new-system-case-type">Case Type</label>
                    <select id="new-system-case-type" bind:value={newSystemCaseType}>
                      <option value="">Auto-detect</option>
                      <option value="cartridge">Cartridge</option>
                      <option value="disc">Disc</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                  </div>
                  <div class="form-field form-field--logo">
                    <label for="new-system-logo">Logo Image</label>
                    <div class="file-input-group file-input-group--logo">
                      <input id="new-system-logo" type="file" accept="image/*" on:change={(e) => handleLogoUpload(e, true)} />
                      <span class="file-input-group-divider" aria-hidden="true"><span>or</span></span>
                      <input type="text" bind:value={newSystemIcon} placeholder="Image URL (optional)" />
                    </div>
                    <div class="system-logo-controls">
                      <button
                        type="button"
                        class="system-logo-fetch-button"
                        disabled={systemLogoFetchBusy}
                        on:click={() => fetchSystemLogo(true)}
                      >
                        {systemLogoFetchBusy ? 'Fetching Logo...' : 'Fetch Logo'}
                      </button>
                      {#if systemLogoFetchError && canFetchSystemLogo(true)}
                        <p class="admin-error system-logo-fetch-error">{systemLogoFetchError}</p>
                      {/if}
                    </div>
                    {#if newSystemIcon}
                      <div class="logo-preview logo-preview--compact">
                        <img src={newSystemIcon} alt="Logo preview" />
                      </div>
                    {/if}
                  </div>
                  <button type="button" on:click={addSystem} class="add-button">Add System</button>
                </div>
              </div>

              {#if systemError}
                <p class="admin-error">{systemError}</p>
              {/if}

              <div class="systems-list" role="list">
                {#each editableSystems as system}
                  <div
                    class="systems-row"
                    role="listitem"
                    draggable="true"
                    on:dragstart={(e) => handleSystemDragStart(e, system.id)}
                    on:dragover={handleSystemDragOver}
                    on:drop={(e) => handleSystemDrop(e, system.id)}
                    on:dragend={handleSystemDragEnd}
                    on:dragleave={(e) => e.preventDefault()}
                  >
                    <div class="systems-row-handle" aria-label="Drag to reorder">
                      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" aria-hidden="true">
                        <circle cx="6" cy="6" r="1.5" />
                        <circle cx="6" cy="12" r="1.5" />
                        <circle cx="6" cy="18" r="1.5" />
                        <circle cx="12" cy="6" r="1.5" />
                        <circle cx="12" cy="12" r="1.5" />
                        <circle cx="12" cy="18" r="1.5" />
                      </svg>
                    </div>
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
                  <div class="form-field">
                    <label for="edit-system-name">System Name</label>
                    <input id="edit-system-name" type="text" bind:value={editingSystemName} placeholder="System name" />
                  </div>
                  <div class="form-field">
                    <label for="edit-system-case-type">Case Type</label>
                    <select id="edit-system-case-type" bind:value={editingSystemCaseType}>
                      <option value="">Auto-detect</option>
                      <option value="cartridge">Cartridge</option>
                      <option value="disc">Disc</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                  </div>
                  <div class="form-field form-field--logo">
                    <label for="edit-system-logo">Logo Image</label>
                    <div class="file-input-group file-input-group--logo">
                      <input id="edit-system-logo" type="file" accept="image/*" on:change={(e) => handleLogoUpload(e, false)} />
                      <span class="file-input-group-divider" aria-hidden="true"><span>or</span></span>
                      <input type="text" bind:value={editingSystemIcon} placeholder="Image URL" />
                    </div>
                    <div class="system-logo-controls">
                      <button
                        type="button"
                        class="system-logo-fetch-button"
                        disabled={systemLogoFetchBusy}
                        on:click={() => fetchSystemLogo(false)}
                      >
                        {systemLogoFetchBusy ? 'Fetching Logo...' : 'Fetch Logo'}
                      </button>
                      {#if systemLogoFetchError && canFetchSystemLogo(false)}
                        <p class="admin-error system-logo-fetch-error">{systemLogoFetchError}</p>
                      {/if}
                    </div>
                    {#if editingSystemIcon}
                      <div class="logo-preview logo-preview--compact">
                        <img src={editingSystemIcon} alt="Logo preview" />
                      </div>
                    {/if}
                  </div>
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
            <button type="button" class="popup-close" aria-label="Close admin panel" on:click={() => (adminOpen = false)}>×</button>
          </div>

          <div class="admin-tabs">
            <button 
              type="button" 
              class:active={libraryAdminTab === 'games'}
              on:click={() => { libraryAdminTab = 'games'; adminListPage = 0; if (adminEditingId === null) resetAdminForm('Games'); }}
            >
              Games
            </button>
            <button 
              type="button" 
              class:active={libraryAdminTab === 'music'}
              on:click={() => { libraryAdminTab = 'music'; adminListPage = 0; if (adminEditingId === null) resetAdminForm('Music'); }}
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
                      {#if item.cover_image}
                        <img src={item.cover_image} alt="" class="admin-row-thumb" draggable="false" />
                      {/if}
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

              <!-- Bulk Upload -->
              <div class="bulk-upload-section">
                <button
                  type="button"
                  class="bulk-upload-toggle"
                  on:click={() => {
                    bulkOpen = !bulkOpen;
                    bulkResults = [];
                    bulkText = '';
                    bulkTotalCount = 0;
                    bulkProcessedCount = 0;
                    bulkProgressPercent = 0;
                    bulkStatusText = '';
                    bulkErrorText = '';
                  }}
                >
                  {bulkOpen ? '▲ Hide Bulk Upload' : '▼ Bulk Upload'}
                </button>
                <div class="bulk-upload-body" class:open={bulkOpen}>
                  <p class="bulk-format-hint">
                    {#if libraryAdminTab === 'games'}
                      One game title per line. Platform comes from the filter above.
                    {:else}
                      One album per line: <code>Album Title - Artist</code>
                    {/if}
                  </p>
                  <textarea
                    class="bulk-upload-textarea"
                    bind:value={bulkText}
                    placeholder={libraryAdminTab === 'games'
                      ? 'Final Fantasy VII\nShadow of the Colossus'
                      : 'Nevermind - Nirvana\nAbbey Road - The Beatles'}
                    rows="6"
                    disabled={bulkBusy}
                  ></textarea>
                  <button
                    type="button"
                    class="bulk-submit-button"
                    disabled={!bulkText.trim() || bulkBusy}
                    on:click={bulkUpload}
                  >
                    {bulkBusy ? 'Uploading...' : libraryAdminTab === 'games' ? 'Upload Games' : 'Upload Albums'}
                  </button>
                  {#if bulkTotalCount > 0 || bulkBusy}
                    <div class="bulk-progress-panel" role="status" aria-live="polite">
                      <div class="bulk-progress-track" aria-hidden="true">
                        <span class="bulk-progress-fill" style={`width: ${bulkProgressPercent}%`}></span>
                      </div>
                      <p class="bulk-progress-text">
                        {bulkStatusText || (bulkBusy ? 'Uploading...' : 'Upload complete.')}
                      </p>
                      {#if bulkErrorText}
                        <p class="bulk-progress-error">{bulkErrorText}</p>
                      {/if}
                    </div>
                  {/if}
                  {#if bulkResults.length}
                    <div class="bulk-result-list">
                      {#each bulkResults as result}
                        <div class="bulk-result-item" class:bulk-success={result.status === 'success'} class:bulk-error={result.status === 'error'}>
                          <span class="bulk-result-line">{result.line}</span>
                          <span class="bulk-result-msg">{result.message}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>
            </div>

            <!-- Library Editor (Right) -->
            <div class="admin-form-pane">
              {#if adminEditingId !== null}
                <form class="admin-form" on:submit|preventDefault={saveAdminItem}>
                  <h3>{adminContextItem?.title ?? 'Edit Item'}</h3>
                  {#if libraryAdminTab === 'games'}
                    <section class="admin-loaded-art" aria-label="Loaded Art">
                      <p class="admin-loaded-art-title">Loaded Art</p>
                      <div class="admin-loaded-art-grid">
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Box Art</span>
                            <label for="admin-upload-cover-art" class="admin-art-upload-button">Upload</label>
                            <input
                              id="admin-upload-cover-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'cover_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            {#if adminForm.cover_image}
                              <button type="button" class="admin-loaded-art-preview" on:click={() => openLaunchboxArtPicker('cover_image')}>
                                <img src={adminForm.cover_image} alt="Fetched box art" />
                              </button>
                            {:else}
                              <div class="admin-loaded-art-empty">No box art loaded</div>
                            {/if}
                          </div>
                        </div>
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Disc/Cart Art</span>
                            <label for="admin-upload-disc-art" class="admin-art-upload-button">Upload</label>
                            <input
                              id="admin-upload-disc-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'disc_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            {#if adminForm.disc_image}
                              <button type="button" class="admin-loaded-art-preview" on:click={() => openLaunchboxArtPicker('disc_image')}>
                                <img src={adminForm.disc_image} alt="Fetched disc/cart art" />
                              </button>
                            {:else}
                              <div class="admin-loaded-art-empty">No disc/cart art loaded</div>
                            {/if}
                          </div>
                        </div>
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Spine Art</span>
                            <label for="admin-upload-spine-art" class="admin-art-upload-button">Upload</label>
                            <input
                              id="admin-upload-spine-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'spine_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            {#if adminForm.spine_image}
                              <button type="button" class="admin-loaded-art-preview" on:click={() => openLaunchboxArtPicker('spine_image')}>
                                <img src={adminForm.spine_image} alt="Fetched spine art" />
                              </button>
                            {:else}
                              <div class="admin-loaded-art-empty">No spine art loaded</div>
                            {/if}
                          </div>
                        </div>
                      </div>
                    </section>
                  {/if}
                  <div class="form-field">
                    <label for="admin-item-title">Title</label>
                    <input id="admin-item-title" type="text" bind:value={adminForm.title} placeholder="Title" required />
                  </div>

                  {#if libraryAdminTab === 'games'}
                    <div class="form-field">
                      <label for="admin-platform">Platform</label>
                      <select id="admin-platform" bind:value={adminForm.platform} required>
                        <option value="">Select console</option>
                        {#each adminConsoleOptions as consoleName}
                          <option value={consoleName}>{consoleName}</option>
                        {/each}
                      </select>
                    </div>
                    <button
                      type="button"
                      class="launchbox-fetch-button"
                      class:pulse={canFetchLaunchBoxGameData() && !launchboxFetchBusy}
                      disabled={launchboxFetchBusy}
                      on:click={fetchLaunchBoxGameData}
                    >
                      {launchboxFetchBusy ? 'Fetching Game Data...' : 'Fetch Game Data'}
                    </button>
                    {#if launchboxFetchError}
                      <p class="admin-error launchbox-fetch-error">{launchboxFetchError}</p>
                    {/if}
                    <div class="admin-field-group">
                      <label class="admin-field-label" for="admin-publishers">Publisher(s)</label>
                      <div class="admin-chip-row">
                        <select id="admin-publishers" bind:value={adminPublisherChoice} on:change={() => {
                          if (adminPublisherChoice) {
                            updateAdminSelection('publishers', adminPublisherChoice, 'add');
                            adminPublisherChoice = '';
                          }
                        }}>
                          <option value="">Select publisher</option>
                          {#each adminPublisherOptions as publisherName}
                            <option value={publisherName} disabled={adminForm.publishers.includes(publisherName)}>{publisherName}</option>
                          {/each}
                        </select>
                      </div>
                      {#if adminForm.publishers.length}
                        <div class="admin-chip-list">
                          {#each adminForm.publishers as publisherName}
                            <button type="button" class="admin-chip" on:click={() => updateAdminSelection('publishers', publisherName, 'remove')}>
                              {publisherName}
                              <span aria-hidden="true">×</span>
                            </button>
                          {/each}
                        </div>
                      {/if}
                    </div>
                    <div class="admin-field-group">
                      <label class="admin-field-label" for="admin-game-genres">Genre(s)</label>
                      <div class="admin-chip-row">
                        <select id="admin-game-genres" bind:value={adminGameGenreChoice} on:change={() => {
                          if (adminGameGenreChoice) {
                            updateAdminSelection('gameGenres', adminGameGenreChoice, 'add');
                            adminGameGenreChoice = '';
                          }
                        }}>
                          <option value="">Select genre</option>
                          {#each adminGameGenreOptions as genreName}
                            <option value={genreName} disabled={adminForm.gameGenres.includes(genreName)}>{genreName}</option>
                          {/each}
                        </select>
                      </div>
                      {#if adminForm.gameGenres.length}
                        <div class="admin-chip-list">
                          {#each adminForm.gameGenres as genreName}
                            <button type="button" class="admin-chip" on:click={() => updateAdminSelection('gameGenres', genreName, 'remove')}>
                              {genreName}
                              <span aria-hidden="true">×</span>
                            </button>
                          {/each}
                        </div>
                      {/if}
                    </div>
                    <div class="form-field">
                      <label for="admin-release-date">Release Date</label>
                      <input id="admin-release-date" type="date" bind:value={adminForm.release_date} placeholder="Release date" />
                    </div>
                    <div class="form-field">
                      <label for="admin-players">Players</label>
                      <select id="admin-players" bind:value={adminForm.players}>
                        <option value="">Number of players</option>
                        {#each adminPlayerOptions as playerCount}
                          <option value={String(playerCount)}>{playerCount}</option>
                        {/each}
                      </select>
                    </div>
                    <div class="form-field">
                      <label for="admin-cooperative">Cooperative</label>
                      <select id="admin-cooperative" bind:value={adminForm.cooperative}>
                        {#each cooperativeOptions as cooperativeOption}
                          <option value={cooperativeOption}>{cooperativeOption}</option>
                        {/each}
                      </select>
                    </div>
                    <div class="form-field">
                      <label for="admin-rating">Rating</label>
                      <select id="admin-rating" bind:value={adminForm.rating}>
                        {#each gameRatingOptions as ratingOption}
                          <option value={ratingOption}>{ratingOption}</option>
                        {/each}
                      </select>
                    </div>
                  {:else}
                    <div class="form-field">
                      <label for="admin-artist">Artist</label>
                      <input id="admin-artist" type="text" bind:value={adminForm.artist} placeholder="Artist" />
                    </div>
                    <div class="form-field">
                      <label for="admin-music-genre">Genre</label>
                      <select id="admin-music-genre" bind:value={adminMusicGenreChoice} required on:change={() => {
                        adminForm = { ...adminForm, musicGenre: adminMusicGenreChoice };
                      }}>
                        <option value="">Select genre</option>
                        {#each adminMusicGenreOptions as genreName}
                          <option value={genreName}>{genreName}</option>
                        {/each}
                      </select>
                    </div>
                    <div class="form-field">
                      <label for="admin-music-release-date">Release Date</label>
                      <input id="admin-music-release-date" type="date" bind:value={adminForm.release_date} placeholder="Release date" />
                    </div>
                  {/if}
                  <div class="form-field">
                    <label for="admin-notes">Overview</label>
                    <textarea id="admin-notes" bind:value={adminForm.notes} rows="3" placeholder="Overview"></textarea>
                  </div>
                  
                  <div class="form-actions">
                    <button type="submit" disabled={adminBusy}>{adminEditingId ? 'Save Changes' : 'Create Item'}</button>
                    <button type="button" on:click={() => { adminEditingId = null; adminContextItem = null; }}>Clear</button>
                  </div>
                </form>
              {:else}
                <div class="admin-form-empty">
                  <p>Select an item from the list to edit, or click the button below to create a new one.</p>
                  <button type="button" on:click={() => { resetAdminForm(libraryAdminTab === 'music' ? 'Music' : 'Games'); adminEditingId = -1; }}>Create New {libraryAdminTab === 'games' ? 'Game' : 'Album'}</button>
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
      <p class="footer-content">
        <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="footer-brand-logo" draggable="false" />
        <span class="footer-delimiter">|</span>
        <span>&copy; 2026 ALEX PRITT</span>
      </p>
    </div>
  </div>
{/if}

