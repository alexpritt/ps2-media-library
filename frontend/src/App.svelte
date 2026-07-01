<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { TransitionConfig } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import type { MediaItem, EditableSystem } from './types';

  type Stage = 'boot' | 'console' | 'library' | 'details';
  type Category = 'Games' | 'Music';
  type GameRating = 'RP' | 'E' | 'E10+' | 'T' | 'M' | 'AO';
  type LibraryView = 'owned' | 'wishlist';
  type AdminLibraryTab = 'games' | 'music' | 'wishlists';

  type WishlistKind = 'console' | 'games' | 'music';

  type WishlistMediaItem = MediaItem & {
    wishlistId: string;
    wishlistKind: 'games' | 'music';
  };

  type WishlistSystemItem = EditableSystem & {
    wishlistId: string;
    wishlistKind: 'console';
  };

  type WishlistAdminSection = 'console' | 'games' | 'music';
  type BulkUploadSection = 'console' | 'games' | 'music';

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
    starRating: number | null;
  };

  type WishlistSystemForm = {
    id: string | null;
    name: string;
    shortName: string;
    logo: string;
    logoImage: string | null;
    caseType: '' | 'disc' | 'cartridge' | 'hybrid';
    appearancePreset: string;
  };

  type GameArtField = 'cover_image' | 'spine_image' | 'disc_image';
  type ArtPickerSource = 'launchbox' | 'music';
  type LaunchboxArtKind = 'cover' | 'disc' | 'spine';
  type DataSource = 'launchbox' | 'mobygames' | 'rawg' | 'igdb' | 'libretro' | 'wikidata' | 'cache' | 'unknown';
  type DetailTagTone = 'blue' | 'cyan' | 'green' | 'amber' | 'rose' | 'violet';

  type DetailTag = {
    label: string;
    query: string;
    tone: DetailTagTone;
  };

  type PriceValue = {
    value: number | null;
    url: string | null;
  };

  type DetailPriceData = {
    kind: 'game' | 'music' | 'unknown';
    averageLoose: PriceValue;
    averageCib: PriceValue;
    averageNew: PriceValue;
    averageStandard: PriceValue;
    averageLimited: PriceValue;
    averageChangePercent: number | null;
    soldRangeMin: number | null;
    soldRangeMax: number | null;
    soldRangeByCondition: Record<string, { min: number; max: number }>;
  };

  type DetailPriceSummaryEntry = {
    label: string;
    value: number | null;
    url: string | null;
    colorClass: string;
  };

  type ConsoleOption = {
    name: string;
    shortName: string;
    logo: string;
    logoImage?: string;
    caseType?: 'disc' | 'cartridge' | 'hybrid';
    appearancePreset?: string | null;
  };

  type FetchToolKey = 'gameArt' | 'gameDetails' | 'gamePrice' | 'musicArt' | 'musicDetails' | 'musicPrice';

  type FetchToolActivityEntry = {
    key: string;
    line: string;
    status: 'running' | 'success' | 'error';
    message: string;
  };

  type FetchToolState = {
    running: boolean;
    runningAction: 'empty' | 'all' | null;
    processed: number;
    total: number;
    progress: number;
    showProgress: boolean;
    statusText: string;
    errorText: string;
    updatedCount: number;
    activity: FetchToolActivityEntry[];
  };

  const ZOOM_TRANSITION_MS = 900;
  const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim();
  const isLocalPreviewHost = typeof window !== 'undefined'
    && /^(localhost|127\.0\.0\.1)$/i.test(window.location.hostname);
  const API_BASE_URL = configuredApiBaseUrl
    || (isLocalPreviewHost ? '' : 'https://ps2-media-library-api.fly.dev');

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
  const BOOT_VIDEO_SRC = (import.meta.env.VITE_BOOT_INTRO_SRC || '').trim() || 'https://media.theavenoircollection.com/ps2-intro.mov';
  const BOOT_MOBILE_VIDEO_SRC = (import.meta.env.VITE_BOOT_MOBILE_SRC || '').trim() || 'https://media.theavenoircollection.com/ps2-intro.mov';

  function isMobileClient() {
    if (typeof navigator === 'undefined') return false;
    const ua = navigator.userAgent || '';
    if (/Android|iPhone|iPad|iPod|IEMobile|Opera Mini/i.test(ua)) return true;
    return navigator.maxTouchPoints > 1 && /Macintosh/i.test(ua);
  }

  const isMobile = isMobileClient();

  function shouldPreferMobileBootSource() {
    if (!BOOT_MOBILE_VIDEO_SRC) return false;
    if (isMobileClient()) return true;
    if (typeof navigator !== 'undefined') {
      const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
      if (connection?.saveData) return true;
      if (connection?.effectiveType && /(^2g$|^slow-2g$)/i.test(connection.effectiveType)) return true;
    }
    return false;
  }

  function buildBootVideoSources() {
    const ordered = shouldPreferMobileBootSource()
      ? [BOOT_MOBILE_VIDEO_SRC, BOOT_VIDEO_SRC]
      : [BOOT_VIDEO_SRC, BOOT_MOBILE_VIDEO_SRC];
    return Array.from(new Set(ordered.map((value) => value?.trim()).filter(Boolean))) as string[];
  }

  const BOOT_VIDEO_SOURCES = buildBootVideoSources();
  const BOOT_VIDEO_PRELOAD = shouldPreferMobileBootSource() ? 'metadata' : 'auto';
  const CONSOLE_WISHLIST_KEY = 'ps2-console-wishlist';
  const GAME_WISHLIST_KEY = 'ps2-game-wishlist';
  const MUSIC_WISHLIST_KEY = 'ps2-music-wishlist';
  const DARK_MODE_KEY = 'ps2-dark-mode-enabled';
  const LOCAL_STAR_RATING_OVERRIDES_KEY = 'ps2-local-star-rating-overrides';
  const fetchToolEntries: Array<{ key: FetchToolKey; title: string; description: string }> = [
    { key: 'gameArt', title: 'Game Art', description: 'Fetch cover, spine, and disc art for games in libraries and wish lists.' },
    { key: 'gameDetails', title: 'Game Details', description: 'Fetch notes, genre, publisher, release, ESRB, players, and co-op data.' },
    { key: 'gamePrice', title: 'Game Price', description: 'Fetch PriceCharting price data for games in libraries and wish lists.' },
    { key: 'musicArt', title: 'Album Art', description: 'Fetch album covers for music entries in libraries and wish lists.' },
    { key: 'musicDetails', title: 'Album Details', description: 'Fetch music genre and release details for libraries and wish lists.' },
    { key: 'musicPrice', title: 'Album Price', description: 'Fetch Discogs price data for music entries in libraries and wish lists.' },
  ];

  function apiPath(path: string) {
    if (!API_BASE_URL) return path;
    return `${API_BASE_URL.replace(/\/$/, '')}${path}`;
  }

  let stage: Stage = 'boot';
  let category: Category | null = null;
  let selectedConsole: string | null = null;
  let libraryView: LibraryView = 'owned';
  let media: MediaItem[] = [];
  let allMedia: MediaItem[] = [];
  let selectedItem: MediaItem | null = null;
  let selectedWishlistItem: WishlistMediaItem | null = null;
  let selectedWishlistConsole: WishlistSystemItem | null = null;
  let consoleWishlist: WishlistSystemItem[] = [];
  let gameWishlist: WishlistMediaItem[] = [];
  let musicWishlist: WishlistMediaItem[] = [];
  let darkModeEnabled = false;

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
  let bootLastTouchAt = 0;
  let bootSkipTapTimeout: ReturnType<typeof setTimeout> | null = null;

  const bootSkipHintText = isMobile ? 'Tap to skip intro' : 'Press spacebar to skip intro';
  $: bootMuteHintText = bootMuted
    ? (isMobile ? 'Double tap to enable audio' : 'Press M to enable audio')
    : (isMobile ? 'Double tap to mute' : 'Press M to mute');
  let bootHardFailTimeout: ReturnType<typeof setTimeout> | null = null;
  let bootSourceIndex = 0;
  let bootVideoSource = BOOT_VIDEO_SOURCES[0] ?? BOOT_VIDEO_SRC;
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
  let consoleHeaderIdleVisible = true;
  let consoleHeaderHoverVisible = false;
  let consoleHeaderSwapTimeout: ReturnType<typeof setTimeout> | null = null;
  const CONSOLE_HEADER_FADE_MS = 500;

  let page = 0;
  let itemsPerPage = 15;
  let viewportWidth = 0;
  let mediaLoadRequestId = 0;
  let libraryLoading = false;

  let adminToken = '';
  let adminOpen = false;
    let adminMode: 'hub' | 'systems' | 'library' = 'hub';
    let libraryAdminTab: AdminLibraryTab = 'games';
    let adminContextItem: MediaItem | null = null;
  let wishlistAdminSection: WishlistAdminSection = 'console';
  let wishlistSystemForm: WishlistSystemForm = {
    id: null,
    name: '',
    shortName: '',
    logo: '',
    logoImage: null,
    caseType: '',
    appearancePreset: '',
  };
  let wishlistEditingId: string | null = null;
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
  let launchboxManualUrl = '';
  let musicFetchBusy = false;
  let musicFetchError = '';
  let launchboxArtPickerOpen = false;
  let launchboxArtPickerBusy = false;
  let launchboxArtPickerError = '';
  let launchboxArtPickerStatus = '';
  let launchboxArtPickerField: GameArtField | null = null;
  let launchboxArtPickerSource: ArtPickerSource = 'launchbox';
  let launchboxArtOptions: string[] = [];
  let launchboxArtOptionsBySource: { discogs: string[]; deezer: string[] } = {
    discogs: [],
    deezer: [],
  };
  let bulkOpen = false;
  let bulkText = '';
  let bulkBusy = false;
  let bulkResults: { line: string; status: 'success' | 'error'; message: string }[] = [];
  let bulkTotalCount = 0;
  let bulkProcessedCount = 0;
  let bulkProgressPercent = 0;
  let bulkStatusText = '';
  let bulkErrorText = '';
  let bulkAddWishlistBusy = false;
  let bulkAddWishlistResults: { title: string; status: 'success' | 'error'; message: string }[] = [];
  let bulkAddWishlistStatusText = '';
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
  let libraryStarFilter: number | null = null;
  let starDropdownOpen = false;
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
  let confirmMode: 'edit' | 'delete' | 'delete-system' = 'delete';
  let confirmItem: MediaItem | null = null;
  let confirmSystem: EditableSystem | null = null;
  let confirmWishlistKind: WishlistKind | null = null;
  let detailCombinedStarRating: number | null = null;
  let detailEditedStarRating: number | null = null;
  let detailInitialStarRating: number | null = null;
  let detailRatingStateKey = '';
  let detailRatingSaving = false;
  let detailRatingMessage = '';
  let detailPriceFetchBusy = false;
  let detailPriceFetchError = '';
  let detailPriceFetchStatus = '';
  let detailPriceFetchProgress = 0;
  let detailPriceExpanded = false;
  let localStarRatingOverrides: Record<string, number | null> = {};
  let detailRatingKey = '';
  let detailRatingDirty = false;
  let fetchToolsOpen = false;
  let fetchToolsBusy = false;
  let fetchToolsCancelRequested = false;
  const createFetchToolState = (): FetchToolState => ({
    running: false,
    runningAction: null,
    processed: 0,
    total: 0,
    progress: 0,
    showProgress: false,
    statusText: '',
    errorText: '',
    updatedCount: 0,
    activity: [],
  });
  let fetchToolStates: Record<FetchToolKey, FetchToolState> = {
    gameArt: createFetchToolState(),
    gameDetails: createFetchToolState(),
    gamePrice: createFetchToolState(),
    musicArt: createFetchToolState(),
    musicDetails: createFetchToolState(),
    musicPrice: createFetchToolState(),
  };
  let fetchToolConsoleScopes: Record<FetchToolKey, string> = {
    gameArt: 'all',
    gameDetails: 'all',
    gamePrice: 'all',
    musicArt: 'all',
    musicDetails: 'all',
    musicPrice: 'all',
  };
  let detailPriceSummary: DetailPriceSummaryEntry[] = [];
  let detailPriceData: DetailPriceData = {
    kind: 'unknown',
    averageLoose: { value: null, url: null },
    averageCib: { value: null, url: null },
    averageNew: { value: null, url: null },
    averageStandard: { value: null, url: null },
    averageLimited: { value: null, url: null },
    averageChangePercent: null,
    soldRangeMin: null,
    soldRangeMax: null,
    soldRangeByCondition: {},
  };

  function combinedStarRating(item: MediaItem): number | null {
    return item.star_rating ?? null;
  }

  $: isAdmin = adminToken.length > 0;
  $: availableConsoles = buildConsoleList(allMedia, editableSystems);
  $: activeConsoleSource = libraryView === 'wishlist' ? consoleWishlist : availableConsoles;
  $: activeConsole = availableConsoles[0] ?? fallbackConsoles[0];
  $: activeWishlistConsole = activeConsoleSource[0] ?? null;
  $: detailItem = selectedWishlistItem ?? selectedItem;
  $: detailCombinedStarRating = detailItem ? combinedStarRating(detailItem) : null;
  $: detailIsWishlist = selectedWishlistItem !== null;
  $: detailRatingKey = detailItem
    ? detailIsWishlist && selectedWishlistItem
      ? `wishlist-${selectedWishlistItem.wishlistKind}-${selectedWishlistItem.wishlistId}`
      : `media-${detailItem.id}`
    : '';
  $: if (detailRatingKey !== detailRatingStateKey) {
    detailRatingStateKey = detailRatingKey;
    detailEditedStarRating = detailCombinedStarRating;
    detailInitialStarRating = detailCombinedStarRating;
    detailRatingSaving = false;
    detailRatingMessage = '';
    detailPriceFetchBusy = false;
    detailPriceFetchError = '';
    detailPriceFetchStatus = '';
    detailPriceFetchProgress = 0;
  }
  $: detailRatingDirty = detailEditedStarRating !== detailInitialStarRating;
  $: detailPriceData = parseDetailPriceData(detailItem);
  $: detailPriceSummary = detailPriceSummaryEntries(detailItem, detailPriceData);
  $: consoleHeaderSelection = hoveredConsole ?? (stage === 'console' ? selectedConsole : null);
  $: consoleHeaderOption = availableConsoles.find((item) => item.name === consoleHeaderSelection) ?? null;
  $: if (stage !== 'console') {
    hoveredConsole = null;
    consoleHeaderIdleVisible = true;
    consoleHeaderHoverVisible = false;
    if (consoleHeaderSwapTimeout) clearTimeout(consoleHeaderSwapTimeout);
    consoleHeaderSwapTimeout = null;
  }
  $: totalGameLibraryCount = allMedia.filter((item) => item.category === 'Games').length;
  $: totalConsoleWishlistCount = consoleWishlist.length;
  $: consoleLibraryCountLabel = libraryView === 'wishlist'
    ? `${totalConsoleWishlistCount} ${totalConsoleWishlistCount === 1 ? 'Console' : 'Consoles'} on Wish List`
    : `${totalGameLibraryCount} ${totalGameLibraryCount === 1 ? 'Game' : 'Games'} in Library`;
  $: hoveredConsoleGameCount = hoveredConsole
    ? (libraryView === 'wishlist'
      ? gameWishlist.filter((item) => item.platform === hoveredConsole).length
      : allMedia.filter((item) => item.category === 'Games' && item.platform === hoveredConsole).length)
    : stage === 'console' && selectedConsole
      ? (libraryView === 'wishlist'
        ? gameWishlist.filter((item) => item.platform === selectedConsole).length
        : allMedia.filter((item) => item.category === 'Games' && item.platform === selectedConsole).length)
      : null;
  $: hoveredConsoleCountLabel = hoveredConsoleGameCount !== null
    ? libraryView === 'wishlist'
      ? `${hoveredConsoleGameCount} ${hoveredConsoleGameCount === 1 ? 'Item' : 'Items'} ON WISH LIST`
      : `${hoveredConsoleGameCount} ${hoveredConsoleGameCount === 1 ? 'Game' : 'Games'} IN LIBRARY`
    : consoleLibraryCountLabel;
  $: itemsPerPage = viewportWidth <= 420 ? 4 : viewportWidth <= 640 ? 6 : 15;
  $: consolePageItems = activeConsoleSource.slice(page * itemsPerPage, page * itemsPerPage + itemsPerPage);
  $: consoleTotalPages = Math.ceil(Math.max(1, activeConsoleSource.length) / itemsPerPage);
  $: currentItems = pagedItems();
  $: totalPages = Math.ceil(media.length / itemsPerPage);
  $: libraryCountLabel = category === 'Music'
    ? `${media.length} ${media.length === 1 ? 'Album' : 'Albums'} ${libraryView === 'wishlist' ? 'on Wish List' : 'in Library'}`
    : `${media.length} ${media.length === 1 ? 'Game' : 'Games'} ${libraryView === 'wishlist' ? 'on' : 'in'} ${(selectedConsole ?? activeConsole.name)} ${libraryView === 'wishlist' ? 'Wish List' : 'Library'}`;
  $: libraryCountCopy = category === 'Music'
    ? libraryView === 'wishlist'
      ? `${media.length} ${media.length === 1 ? 'ALBUM' : 'ALBUMS'} IN WISH LIST`
      : `${media.length} ${media.length === 1 ? 'ALBUM' : 'ALBUMS'} IN LIBRARY`
    : libraryView === 'wishlist'
      ? `${media.length} ${media.length === 1 ? 'GAME' : 'GAMES'} IN WISH LIST`
      : `${media.length} ${media.length === 1 ? 'GAME' : 'GAMES'} IN LIBRARY`;
  $: consoleCountCopy = libraryView === 'wishlist'
    ? `${totalConsoleWishlistCount} ${totalConsoleWishlistCount === 1 ? 'CONSOLE' : 'CONSOLES'} ON WISH LIST`
    : `${totalGameLibraryCount} ${totalGameLibraryCount === 1 ? 'GAME' : 'GAMES'} IN LIBRARY`;
  $: wishlistToggleContextLabel = stage === 'console'
    ? `CONSOLE ${libraryView === 'wishlist' ? 'WISH LIST' : 'LIBRARY'}`
    : `${(category ?? 'Games').toUpperCase()} ${libraryView === 'wishlist' ? 'WISH LIST' : 'LIBRARY'}`;
  $: adminConsoleOptions = (availableConsoles.length ? availableConsoles : fallbackConsoles).map((item) => item.name);
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
  $: adminWishlistGameItems = gameWishlist.filter((item) => {
    if (adminSearchQuery.trim() && !item.title.toLowerCase().includes(adminSearchQuery.toLowerCase().trim())) return false;
    if (adminSearchPlatform !== 'All' && item.platform !== adminSearchPlatform) return false;
    return true;
  });
  $: adminWishlistMusicItems = musicWishlist.filter((item) => {
    if (adminSearchQuery.trim() && !item.title.toLowerCase().includes(adminSearchQuery.toLowerCase().trim())) return false;
    return true;
  });
  $: adminWishlistConsoleItems = consoleWishlist.filter((item) => {
    if (adminSearchQuery.trim() && !item.name.toLowerCase().includes(adminSearchQuery.toLowerCase().trim())) return false;
    return true;
  });
  $: activeAdminWishlistItems = wishlistAdminSection === 'console'
    ? adminWishlistConsoleItems
    : wishlistAdminSection === 'games'
      ? adminWishlistGameItems
      : adminWishlistMusicItems;
  $: adminActiveTotalPages = libraryAdminTab === 'wishlists'
    ? Math.ceil(Math.max(1, activeAdminWishlistItems.length) / adminListItemsPerPage)
    : adminListTotalPages;
  $: if (adminListPage >= adminActiveTotalPages) adminListPage = Math.max(0, adminActiveTotalPages - 1);
  $: activeAdminWishlistPageItems = activeAdminWishlistItems.slice(
    adminListPage * adminListItemsPerPage,
    (adminListPage + 1) * adminListItemsPerPage,
  );
  $: adminListTotalPages = Math.ceil(Math.max(1, adminFilteredMedia.length) / adminListItemsPerPage);
  $: if (adminListPage >= adminListTotalPages) adminListPage = Math.max(0, adminListTotalPages - 1);
  $: adminPagedMedia = adminFilteredMedia.slice(
    adminListPage * adminListItemsPerPage,
    (adminListPage + 1) * adminListItemsPerPage
  );
  $: detailsConsoleLogo = detailItem?.category === 'Games'
    ? availableConsoles.find((item) => item.name === (detailItem.platform ?? ''))?.logoImage ?? null
    : null;

  $: selectedLibraryConsole = (libraryView === 'wishlist'
    ? category === 'Games'
      ? availableConsoles.find((item) => item.name === (selectedConsole ?? activeConsole.name))
      : consoleWishlist.find((item) => item.name === (selectedConsole ?? activeWishlistConsole?.name ?? ''))
    : availableConsoles.find((item) => item.name === (selectedConsole ?? activeConsole.name))) ?? activeConsole;
  $: libraryHeaderLeft = category === 'Music'
    ? `Music ${libraryView === 'wishlist' ? 'Wish List' : 'Library'}`
    : selectedConsole ?? activeConsole.name;
  $: libraryHeaderRight = libraryCountLabel;
  $: selectedWishlistGameItems = gameWishlist.filter((item) => item.platform === (selectedConsole ?? activeConsole.name));
  $: wishlistConsoleGamesCostTotal = sumCollectionCibOrStandard(gameWishlist, false);
  $: wishlistLibraryGamesCostTotal = sumCollectionCibOrStandard(selectedWishlistGameItems, false);
  $: libraryCostTotal = libraryView === 'wishlist'
    ? category === 'Music'
      ? sumCollectionCibOrStandard(musicWishlist, true)
      : wishlistLibraryGamesCostTotal
    : sumCollectionCibOrStandard(media, category === 'Music');
  $: libraryCostLabel = category === 'Music'
    ? `STANDARD TOTAL ${formatCurrencyCompact(libraryCostTotal)}`
    : `CIB TOTAL ${formatCurrencyCompact(libraryCostTotal)}`;
  $: consoleOwnedGamesCostTotal = libraryView === 'wishlist'
    ? wishlistConsoleGamesCostTotal
    : sumCollectionCibOrStandard(allMedia.filter((item) => item.category === 'Games'), false);
  $: consoleOwnedGamesCostLabel = `CIB TOTAL ${formatCurrencyCompact(consoleOwnedGamesCostTotal)}`;
  $: libraryGridKey = `${libraryView}-${category ?? ''}-${selectedConsole ?? ''}-${librarySearch.trim().toLowerCase()}-${libraryPlayersFilter ?? 'all'}-${libraryStarFilter ?? 'all'}-${page}`;
  $: showEmptyGamesState = category === 'Games' && !libraryLoading && filteredMedia.length === 0;
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
    if (libraryStarFilter !== null) {
      result = result.filter((item) => {
        const combined = combinedStarRating(item);
        return combined !== null && combined >= libraryStarFilter!;
      });
    }
    return result;
  })();
  $: filteredTotalPages = Math.ceil(Math.max(1, filteredMedia.length) / itemsPerPage);
  $: activeStageTotalPages = stage === 'console'
    ? consoleTotalPages
    : stage === 'library'
      ? filteredTotalPages
      : totalPages;
  $: if (page >= activeStageTotalPages) page = Math.max(0, activeStageTotalPages - 1);
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
    starDropdownOpen = false;
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
    confirmSystem = null;
    confirmOpen = true;
  }

  function openDeleteSystemConfirm(system: EditableSystem) {
    confirmMode = 'delete-system';
    confirmSystem = system;
    confirmItem = null;
    confirmOpen = true;
  }

  function closeConfirm() {
    confirmOpen = false;
    confirmItem = null;
    confirmSystem = null;
  }

  async function confirmAction() {
    if (!confirmItem && !confirmSystem) return;

    const item = confirmItem;
    const system = confirmSystem;
    const mode = confirmMode;
    closeConfirm();

    if (mode === 'edit') {
      startEditItem(item);
      return;
    }

    if (mode === 'delete-system' && system) {
      await removeSystem(system.id);
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

  function emptyWishlistSystemForm(): WishlistSystemForm {
    return {
      id: null,
      name: '',
      shortName: '',
      logo: '',
      logoImage: null,
      caseType: '',
      appearancePreset: '',
    };
  }

  function createWishlistId(prefix: WishlistKind) {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function createWishlistMediaId() {
    return -Math.floor(Date.now() + Math.random() * 1_000_000);
  }

  function loadWishlistItems<T>(storageKey: string, fallback: T[]): T[] {
    const stored = localStorage.getItem(storageKey);
    if (!stored) return fallback;
    try {
      return JSON.parse(stored) as T[];
    } catch {
      return fallback;
    }
  }

  function persistConsoleWishlist() {
    localStorage.setItem(CONSOLE_WISHLIST_KEY, JSON.stringify(consoleWishlist));
  }

  function persistGameWishlist() {
    localStorage.setItem(GAME_WISHLIST_KEY, JSON.stringify(gameWishlist));
  }

  function persistMusicWishlist() {
    localStorage.setItem(MUSIC_WISHLIST_KEY, JSON.stringify(musicWishlist));
  }

  function loadWishlistsFromStorage() {
    consoleWishlist = loadWishlistItems<WishlistSystemItem>(CONSOLE_WISHLIST_KEY, []);
    gameWishlist = loadWishlistItems<WishlistMediaItem>(GAME_WISHLIST_KEY, []);
    musicWishlist = loadWishlistItems<WishlistMediaItem>(MUSIC_WISHLIST_KEY, []);
  }

  function normalizeStarRating(value: unknown): number | null {
    if (value === null || value === undefined || value === '') return null;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    const rounded = Math.round(numeric);
    if (rounded < 1 || rounded > 5) return null;
    return rounded;
  }

  function loadLocalStarRatingOverrides() {
    const stored = localStorage.getItem(LOCAL_STAR_RATING_OVERRIDES_KEY);
    if (!stored) {
      localStarRatingOverrides = {};
      return;
    }
    try {
      const parsed = JSON.parse(stored) as Record<string, unknown>;
      localStarRatingOverrides = Object.fromEntries(
        Object.entries(parsed).map(([key, value]) => [key, normalizeStarRating(value)])
      );
    } catch {
      localStarRatingOverrides = {};
    }
  }

  function persistLocalStarRatingOverrides() {
    localStorage.setItem(LOCAL_STAR_RATING_OVERRIDES_KEY, JSON.stringify(localStarRatingOverrides));
  }

  function applyLocalStarRatingOverrides(items: MediaItem[]) {
    return items.map((item) => {
      const overrideKey = String(item.id);
      if (!(overrideKey in localStarRatingOverrides)) return item;
      return {
        ...item,
        star_rating: normalizeStarRating(localStarRatingOverrides[overrideKey]),
      };
    });
  }

  function updateLibraryItemStarRating(itemId: number, starRating: number | null) {
    allMedia = allMedia.map((item) => item.id === itemId ? { ...item, star_rating: starRating } : item);
    media = media.map((item) => item.id === itemId ? { ...item, star_rating: starRating } : item);
    if (selectedItem?.id === itemId) {
      selectedItem = { ...selectedItem, star_rating: starRating };
    }
  }

  function updateWishlistItemStarRating(item: WishlistMediaItem, starRating: number | null) {
    const updated = { ...item, star_rating: starRating };
    if (item.wishlistKind === 'games') {
      gameWishlist = gameWishlist.map((entry) => entry.wishlistId === item.wishlistId ? { ...entry, star_rating: starRating } : entry);
      persistGameWishlist();
    } else {
      musicWishlist = musicWishlist.map((entry) => entry.wishlistId === item.wishlistId ? { ...entry, star_rating: starRating } : entry);
      persistMusicWishlist();
    }
    selectedWishlistItem = updated;
    selectedItem = updated;
  }

  function setDetailStarRating(n: number) {
    detailEditedStarRating = detailEditedStarRating === n ? null : n;
    detailRatingMessage = '';
  }

  function starDisplay(value: number | null, max = 5): string {
    return value == null ? '☆'.repeat(max) : renderStars(value, max);
  }

  function resetWishlistSystemForm() {
    wishlistEditingId = null;
    wishlistSystemForm = emptyWishlistSystemForm();
  }

  function isWishlistMediaItem(item: MediaItem | null): item is WishlistMediaItem {
    return Boolean(item && 'wishlistId' in item && (item as WishlistMediaItem).wishlistKind);
  }

  function wishlistIconLabel() {
    if (stage === 'console') return libraryView === 'wishlist' ? 'Show Console Library' : 'Show Console Wish List';
    if (category === 'Music') return libraryView === 'wishlist' ? 'Show Music Library' : 'Show Music Wish List';
    return libraryView === 'wishlist' ? 'Show Game Library' : 'Show Game Wish List';
  }

  function toggleDarkMode() {
    darkModeEnabled = !darkModeEnabled;
    localStorage.setItem(DARK_MODE_KEY, darkModeEnabled ? 'true' : 'false');
  }

  function darkModeToggleLabel() {
    return darkModeEnabled ? 'Disable dark mode' : 'Enable dark mode';
  }

  function switchLibraryView(nextView: LibraryView) {
    if (libraryView === nextView) return;
    libraryView = nextView;
    page = 0;
    librarySearch = '';
    librarySearchOpen = false;
    libraryPlayersFilter = null;
    playersDropdownOpen = false;
    libraryStarFilter = null;
    starDropdownOpen = false;
    selectedWishlistItem = null;
    selectedWishlistConsole = null;

    if (stage === 'library') {
      void loadMedia(category, selectedConsole);
    }
  }

  function toggleWishlistView() {
    switchLibraryView(libraryView === 'owned' ? 'wishlist' : 'owned');
  }

  function closeWishlistView() {
    switchLibraryView('owned');
  }

  function currentWishlistCollection(kind: WishlistKind) {
    if (kind === 'console') return consoleWishlist;
    if (kind === 'games') return gameWishlist;
    return musicWishlist;
  }

  function removeWishlistItemById(kind: WishlistKind, wishlistId: string) {
    if (kind === 'console') {
      consoleWishlist = consoleWishlist.filter((item) => item.wishlistId !== wishlistId);
      persistConsoleWishlist();
      if (selectedWishlistConsole?.wishlistId === wishlistId) selectedWishlistConsole = null;
      return;
    }
    if (kind === 'games') {
      gameWishlist = gameWishlist.filter((item) => item.wishlistId !== wishlistId);
      persistGameWishlist();
    } else {
      musicWishlist = musicWishlist.filter((item) => item.wishlistId !== wishlistId);
      persistMusicWishlist();
    }
    if (selectedWishlistItem?.wishlistId === wishlistId) {
      selectedWishlistItem = null;
      selectedItem = null;
    }
  }

  function populateAdminFormFromWishlistItem(item: WishlistMediaItem) {
    adminContextItem = item;
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
      starRating: item.star_rating ?? null,
    };
    adminPublisherChoice = '';
    adminGameGenreChoice = '';
    adminMusicGenreChoice = item.category === 'Music' ? item.genre : '';
    launchboxManualUrl = '';
  }

  function openWishlistConsoleDetails(item: WishlistSystemItem) {
    selectedWishlistConsole = item;
    selectedWishlistItem = null;
    selectedItem = null;
  }

  function closeWishlistConsoleDetails() {
    selectedWishlistConsole = null;
  }

  function startEditWishlistMedia(item: WishlistMediaItem) {
    adminOpen = true;
    adminMode = 'library';
    libraryAdminTab = 'wishlists';
    wishlistAdminSection = item.wishlistKind;
    wishlistEditingId = item.wishlistId;
    populateAdminFormFromWishlistItem(item);
  }

  function startEditWishlistConsole(item: WishlistSystemItem) {
    adminOpen = true;
    adminMode = 'library';
    libraryAdminTab = 'wishlists';
    wishlistAdminSection = 'console';
    wishlistEditingId = item.wishlistId;
    wishlistSystemForm = {
      id: item.id,
      name: item.name,
      shortName: item.shortName,
      logo: item.logo,
      logoImage: item.logoImage ?? null,
      caseType: (item.caseType as '' | 'disc' | 'cartridge' | 'hybrid') ?? '',
      appearancePreset: item.appearancePreset ?? '',
    };
  }

  function createWishlistMediaPayload(kind: 'games' | 'music'): WishlistMediaItem {
    const isGames = kind === 'games';
    const releaseDate = adminForm.release_date ? adminForm.release_date.trim() : '';
    const releaseYear = releaseDate ? Number(releaseDate.slice(0, 4)) : (adminForm.year_released ? Number(adminForm.year_released) : null);
    const gameGenres = isGames ? normalizeSelectionValues(adminForm.gameGenres) : [];
    const publishers = isGames ? normalizeSelectionValues(adminForm.publishers) : [];
    return {
      id: adminForm.id ?? -1,
      wishlistId: wishlistEditingId ?? createWishlistId(kind),
      wishlistKind: kind,
      title: (isGames ? normalizeGameTitle(adminForm.title) : adminForm.title).trim(),
      category: isGames ? 'Games' : 'Music',
      platform: isGames ? adminForm.platform.trim() || null : null,
      genre: isGames ? (gameGenres[0] ?? '') : adminForm.musicGenre.trim(),
      genres: isGames ? combineSelectionValues(gameGenres) : null,
      year_released: releaseYear,
      release_date: releaseDate || null,
      rating: isGames ? normalizeGameRating(adminForm.rating) : null,
      players: isGames && adminForm.players ? Number(adminForm.players) : null,
      cooperative: isGames ? adminForm.cooperative : null,
      artist: isGames ? null : adminForm.artist.trim() || null,
      publisher: isGames ? combineSelectionValues(publishers) : null,
      format: null,
      region: null,
      cover_image: adminForm.cover_image ?? null,
      spine_image: adminForm.spine_image ?? null,
      disc_image: adminForm.disc_image ?? null,
      tags: null,
      notes: adminForm.notes.trim() || null,
      star_rating: adminForm.starRating,
    };
  }

  function saveWishlistMediaItem(kind: 'games' | 'music') {
    const isEditingExisting = Boolean(wishlistEditingId);
    const nextItem = createWishlistMediaPayload(kind);
    if (kind === 'games') {
      gameWishlist = [nextItem, ...gameWishlist.filter((item) => item.wishlistId !== nextItem.wishlistId)];
      persistGameWishlist();
    } else {
      musicWishlist = [nextItem, ...musicWishlist.filter((item) => item.wishlistId !== nextItem.wishlistId)];
      persistMusicWishlist();
    }
    wishlistEditingId = null;
    adminMessage = isEditingExisting ? 'Wish list item updated.' : 'Wish list item added.';
    resetAdminForm(kind === 'music' ? 'Music' : 'Games');
    if (libraryView === 'wishlist') {
      void loadMedia(category, selectedConsole);
    }
  }

  function saveWishlistConsoleItem() {
    const name = wishlistSystemForm.name.trim();
    if (!name) {
      adminError = 'System name is required.';
      return;
    }
    const nextItem: WishlistSystemItem = {
      id: wishlistSystemForm.id ?? name.toLowerCase().replace(/\s+/g, '-'),
      wishlistId: wishlistEditingId ?? createWishlistId('console'),
      wishlistKind: 'console',
      name,
      shortName: (wishlistSystemForm.shortName.trim() || name.slice(0, 3)).toUpperCase(),
      logo: (wishlistSystemForm.logo.trim() || name.slice(0, 3)).toUpperCase(),
      logoImage: wishlistSystemForm.logoImage ?? null,
      caseType: wishlistSystemForm.caseType || undefined,
      appearancePreset: wishlistSystemForm.appearancePreset.trim() || null,
    };
    consoleWishlist = [nextItem, ...consoleWishlist.filter((item) => item.wishlistId !== nextItem.wishlistId)];
    persistConsoleWishlist();
    wishlistEditingId = null;
    resetWishlistSystemForm();
    adminMessage = 'Console wish list item saved.';
  }

  async function saveWishlistItem() {
    adminError = '';
    adminMessage = '';
    if (wishlistAdminSection === 'console') {
      saveWishlistConsoleItem();
      return;
    }
    const isGames = wishlistAdminSection === 'games';
    if (!adminForm.title.trim()) {
      adminError = 'Title is required.';
      return;
    }
    if (isGames && !adminForm.platform.trim()) {
      adminError = 'Platform is required.';
      return;
    }
    if (isGames && adminForm.gameGenres.length === 0) {
      adminError = 'Select at least one genre for the game.';
      return;
    }
    if (!isGames && !adminForm.musicGenre.trim()) {
      adminError = 'Select a genre for the album.';
      return;
    }
    saveWishlistMediaItem(isGames ? 'games' : 'music');
  }

  async function addWishlistMediaToLibrary(item: WishlistMediaItem) {
    if (!adminToken) {
      adminError = 'Login required.';
      return;
    }

    adminBusy = true;
    adminError = '';
    adminMessage = '';
    try {
      const response = await fetch(apiPath('/api/media'), {
        method: 'POST',
        headers: mediaHeaders(),
        body: JSON.stringify({
          title: item.title,
          category: item.category,
          platform: item.category === 'Games' ? item.platform : null,
          genre: item.genre,
          genres: item.genres,
          release_date: item.release_date,
          year_released: item.year_released,
          rating: item.category === 'Games' ? normalizeGameRating(item.rating) : null,
          players: item.players,
          cooperative: item.cooperative,
          artist: item.artist,
          publisher: item.publisher,
          format: item.format,
          region: item.region,
          cover_image: item.cover_image,
          spine_image: item.spine_image,
          disc_image: item.disc_image,
          tags: item.tags,
          notes: item.notes,
        }),
      });
      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        adminError = 'Session expired. Log in again.';
        return;
      }
      if (!response.ok) {
        adminError = 'Could not add wish list item to the library.';
        return;
      }
      removeWishlistItemById(item.wishlistKind, item.wishlistId);
      selectedWishlistItem = null;
      selectedItem = null;
      adminMessage = `${item.category === 'Music' ? 'Album' : 'Game'} added to the library.`;
      await Promise.all([loadAllMedia(), loadMedia(category, selectedConsole)]);
    } catch {
      adminError = 'Could not add wish list item to the library.';
    } finally {
      adminBusy = false;
    }
  }

  async function addWishlistConsoleToLibrary(item: WishlistSystemItem) {
    if (!adminToken) {
      adminError = 'Login required.';
      return;
    }

    adminBusy = true;
    adminError = '';
    adminMessage = '';
    try {
      const response = await fetch(apiPath('/api/systems'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}` },
        body: JSON.stringify({
          id: item.id,
          name: item.name,
          shortName: item.shortName,
          logo: item.logo,
          logoImageUrl: item.logoImage ?? '',
          caseType: item.caseType ?? undefined,
        }),
      });
      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        adminError = 'Session expired. Log in again.';
        return;
      }
      if (!response.ok) {
        adminError = 'Could not add console to the library.';
        return;
      }
      removeWishlistItemById('console', item.wishlistId);
      selectedWishlistConsole = null;
      adminMessage = 'Console added to the library.';
      await loadSystemsFromAPI();
    } catch {
      adminError = 'Could not add console to the library.';
    } finally {
      adminBusy = false;
    }
  }

  async function bulkAddWishlistToLibrary() {
    if (!adminToken) {
      adminError = 'Login required.';
      return;
    }

    const section = wishlistAdminSection;
    const itemsToAdd = section === 'console'
      ? consoleWishlist
      : section === 'games'
        ? gameWishlist
        : musicWishlist;

    if (!itemsToAdd.length) {
      adminMessage = `No ${section} wish list items to add.`;
      return;
    }

    bulkAddWishlistBusy = true;
    bulkAddWishlistResults = [];
    bulkAddWishlistStatusText = '';
    adminError = '';
    adminMessage = '';

    let successCount = 0;
    let errorCount = 0;
    const results: { title: string; status: 'success' | 'error'; message: string }[] = [];

    try {
      for (const item of itemsToAdd) {
        try {
          if (section === 'console') {
            const consoleItem = item as WishlistSystemItem;
            const response = await fetch(apiPath('/api/systems'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}` },
              body: JSON.stringify({
                id: consoleItem.id,
                name: consoleItem.name,
                shortName: consoleItem.shortName,
                logo: consoleItem.logo,
                logoImageUrl: consoleItem.logoImage ?? '',
                caseType: consoleItem.caseType ?? undefined,
              }),
            });
            if (response.status === 401) {
              adminToken = '';
              localStorage.removeItem('ps2-admin-token');
              adminError = 'Session expired. Log in again.';
              return;
            }
            if (response.ok) {
              successCount += 1;
              results.push({ title: consoleItem.name, status: 'success', message: `Added console: ${consoleItem.name}` });
            } else {
              errorCount += 1;
              results.push({ title: consoleItem.name, status: 'error', message: 'Failed to add console' });
            }
          } else {
            const mediaItem = item as WishlistMediaItem;
            const response = await fetch(apiPath('/api/media'), {
              method: 'POST',
              headers: mediaHeaders(),
              body: JSON.stringify({
                title: mediaItem.title,
                category: mediaItem.category,
                platform: mediaItem.category === 'Games' ? mediaItem.platform : null,
                genre: mediaItem.genre,
                genres: mediaItem.genres,
                release_date: mediaItem.release_date,
                year_released: mediaItem.year_released,
                rating: mediaItem.category === 'Games' ? normalizeGameRating(mediaItem.rating) : null,
                players: mediaItem.players,
                cooperative: mediaItem.cooperative,
                artist: mediaItem.artist,
                publisher: mediaItem.publisher,
                format: mediaItem.format,
                region: mediaItem.region,
                cover_image: mediaItem.cover_image,
                spine_image: mediaItem.spine_image,
                disc_image: mediaItem.disc_image,
                tags: mediaItem.tags,
                notes: mediaItem.notes,
              }),
            });
            if (response.status === 401) {
              adminToken = '';
              localStorage.removeItem('ps2-admin-token');
              adminError = 'Session expired. Log in again.';
              return;
            }
            if (response.ok) {
              successCount += 1;
              results.push({ title: mediaItem.title, status: 'success', message: `Added ${mediaItem.category === 'Music' ? 'album' : 'game'}: ${mediaItem.title}` });
            } else {
              errorCount += 1;
              results.push({ title: mediaItem.title, status: 'error', message: 'Failed to add item' });
            }
          }
        } catch {
          errorCount += 1;
          results.push({ title: (item as any).name ?? (item as any).title ?? 'Unknown', status: 'error', message: 'Network error' });
        }
        bulkAddWishlistResults = [...results];
        bulkAddWishlistStatusText = `Processing ${results.length}/${itemsToAdd.length}...`;
      }

      if (successCount > 0) {
        // Remove all successfully added items from wishlist
        if (section === 'console') {
          consoleWishlist = consoleWishlist.filter(c =>
            !results.find(r => r.status === 'success' && r.title === c.name)
          );
          persistConsoleWishlist();
        } else if (section === 'games') {
          gameWishlist = gameWishlist.filter(g =>
            !results.find(r => r.status === 'success' && r.title === g.title)
          );
          persistGameWishlist();
        } else {
          musicWishlist = musicWishlist.filter(m =>
            !results.find(r => r.status === 'success' && r.title === m.title)
          );
          persistMusicWishlist();
        }
      }

      adminMessage = `Added ${successCount} ${successCount === 1 ? 'item' : 'items'} to the library.`;
      if (errorCount > 0) {
        adminError = `${errorCount} item${errorCount === 1 ? '' : 's'} failed to add.`;
      }
      bulkAddWishlistStatusText = `Complete: ${successCount} succeeded, ${errorCount} failed.`;
      await Promise.all([loadAllMedia(), loadMedia(category, selectedConsole)]);
    } catch {
      adminError = 'Bulk add failed.';
      bulkAddWishlistStatusText = 'Bulk add failed.';
    } finally {
      bulkAddWishlistBusy = false;
    }
  }

  function deleteWishlistSelection(kind: WishlistKind, wishlistId: string) {
    removeWishlistItemById(kind, wishlistId);
    if (libraryView === 'wishlist' && stage === 'library') {
      void loadMedia(category, selectedConsole);
    }
    adminMessage = 'Wish list item deleted.';
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

  function handleBootScreenTouchEnd(event: TouchEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.boot-option')) return;
    if (!isMobile) return;

    const now = Date.now();
    if (now - bootLastTouchAt <= 330) {
      if (bootSkipTapTimeout) {
        clearTimeout(bootSkipTapTimeout);
        bootSkipTapTimeout = null;
      }
      toggleBootMute();
      bootLastTouchAt = 0;
      return;
    }
    bootLastTouchAt = now;
    if (bootSkipTapTimeout) {
      clearTimeout(bootSkipTapTimeout);
    }
    bootSkipTapTimeout = setTimeout(() => {
      bootSkipTapTimeout = null;
      bootLastTouchAt = 0;
      if (stage === 'boot' && !bootTextVisible) {
        skipBootIntro();
      }
    }, 340);
  }

  function handleBootScreenClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.boot-option')) return;
    if (isMobile) return;
    // Desktop mute is controlled by the M key.
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
      starRating: null,
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

  function launchboxPlatformCandidates(platform: string | null | undefined) {
    const base = (platform ?? '').trim();
    if (!base) return [];

    const compact = base.toLowerCase().replace(/[^a-z0-9]+/g, '');
    const aliasMap: Record<string, string[]> = {
      ps1: ['PlayStation'],
      psx: ['PlayStation'],
      playstation1: ['PlayStation'],
      ps2: ['PlayStation 2'],
      playstation2: ['PlayStation 2'],
      ps3: ['PlayStation 3'],
      playstation3: ['PlayStation 3'],
      ps4: ['PlayStation 4'],
      playstation4: ['PlayStation 4'],
      nds: ['Nintendo DS'],
      nintendods: ['Nintendo DS'],
      ds: ['Nintendo DS'],
      '3ds': ['Nintendo 3DS'],
      nintendo3ds: ['Nintendo 3DS'],
      gc: ['GameCube'],
      gamecube: ['GameCube'],
      gb: ['GameBoy'],
      gameboy: ['GameBoy'],
      xbx: ['Xbox'],
      xbox360: ['Xbox 360'],
      x360: ['Xbox 360'],
    };

    const options = [base, ...(aliasMap[compact] ?? [])];
    return Array.from(new Set(options.map((value) => value.trim()).filter(Boolean)));
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

  function normalizeGameTitle(title: string): string {
    const cleaned = title.trim().replace(/\s+/g, ' ');
    if (!cleaned) return '';
    const lowerWords = new Set(['a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into', 'nor', 'of', 'on', 'or', 'over', 'the', 'to', 'up', 'with']);
    const preserveWords = new Set(['II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV', 'HD', '3D', 'DS', 'PSP', 'VR', 'USA', 'EU', 'USA.']);
    return cleaned
      .split(' ')
      .map((word: string, index: number, words: string[]) => {
        const stripped = word.replace(/^["'([{]+|["')\]}.,:;!?]+$/g, '');
        const punctuationPrefix = word.slice(0, word.indexOf(stripped));
        const punctuationSuffix = word.slice(word.indexOf(stripped) + stripped.length);
        const normalizedToken: string = stripped.includes('-')
          ? stripped.split('-').map((segment: string) => segment ? normalizeGameTitle(segment) : segment).join('-')
          : stripped;
        const upper: string = normalizedToken.toUpperCase();
        if (preserveWords.has(upper)) return `${punctuationPrefix}${upper}${punctuationSuffix}`;
        if (word.includes(':')) {
          return `${punctuationPrefix}${normalizedToken.split(':').map((segment: string, segmentIndex: number) => {
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
    page = Math.max(0, Math.min(activeStageTotalPages - 1, nextPage));
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

  function supportsConsoleHover(event: PointerEvent) {
    if (event.pointerType) {
      return event.pointerType === 'mouse';
    }
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    }
    return true;
  }

  function clearConsoleHeaderSwapTimeout() {
    if (consoleHeaderSwapTimeout) {
      clearTimeout(consoleHeaderSwapTimeout);
      consoleHeaderSwapTimeout = null;
    }
  }

  function showConsoleHeaderHover(consoleName: string) {
    hoveredConsole = consoleName;
    clearConsoleHeaderSwapTimeout();

    if (consoleHeaderHoverVisible) return;

    consoleHeaderIdleVisible = false;
    consoleHeaderHoverVisible = false;
    consoleHeaderSwapTimeout = setTimeout(() => {
      consoleHeaderHoverVisible = true;
      consoleHeaderSwapTimeout = null;
    }, CONSOLE_HEADER_FADE_MS);
  }

  function showConsoleHeaderIdle() {
    clearConsoleHeaderSwapTimeout();

    if (!consoleHeaderHoverVisible) {
      hoveredConsole = null;
      consoleHeaderIdleVisible = true;
      return;
    }

    consoleHeaderHoverVisible = false;
    consoleHeaderIdleVisible = false;
    consoleHeaderSwapTimeout = setTimeout(() => {
      hoveredConsole = null;
      consoleHeaderIdleVisible = true;
      consoleHeaderSwapTimeout = null;
    }, CONSOLE_HEADER_FADE_MS);
  }

  function handleConsolePointerEnter(event: PointerEvent, consoleName: string) {
    if (!supportsConsoleHover(event)) return;
    showConsoleHeaderHover(consoleName);
  }

  function handleConsolePointerLeave(event: PointerEvent) {
    if (!supportsConsoleHover(event)) return;
    showConsoleHeaderIdle();
    clearIconFollow(event as unknown as MouseEvent);
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

  function readPriceValue(rawValue: unknown, rawUrl: unknown): PriceValue {
    const value = typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null;
    const url = typeof rawUrl === 'string' && rawUrl.trim() ? rawUrl.trim() : null;
    return { value, url };
  }

  function parseDetailPriceData(item: MediaItem | null): DetailPriceData {
    const empty: DetailPriceData = {
      kind: 'unknown',
      averageLoose: { value: null, url: null },
      averageCib: { value: null, url: null },
      averageNew: { value: null, url: null },
      averageStandard: { value: null, url: null },
      averageLimited: { value: null, url: null },
      averageChangePercent: null,
      soldRangeMin: null,
      soldRangeMax: null,
      soldRangeByCondition: {},
    };

    if (!item?.price_data_json) {
      return {
        ...empty,
        kind: item?.category === 'Games' ? 'game' : item?.category === 'Music' ? 'music' : 'unknown',
      };
    }

    try {
      const parsed = JSON.parse(item.price_data_json) as Record<string, unknown>;
      const average = (parsed?.average ?? {}) as Record<string, unknown>;
      const soldRange = (parsed?.sold_range ?? {}) as Record<string, unknown>;
      const soldRangeByCondition = (parsed?.sold_range_by_condition ?? {}) as Record<string, Record<string, number>>;

      const loose = (average.loose ?? {}) as Record<string, unknown>;
      const cib = (average.cib ?? {}) as Record<string, unknown>;
      const newValue = (average.new ?? {}) as Record<string, unknown>;
      const standard = (average.standard ?? {}) as Record<string, unknown>;
      const limited = (average.limited ?? {}) as Record<string, unknown>;

      const kindRaw = typeof parsed?.kind === 'string' ? parsed.kind.toLowerCase() : '';
      const kind: DetailPriceData['kind'] = kindRaw === 'game' || kindRaw === 'music'
        ? kindRaw
        : item.category === 'Games'
          ? 'game'
          : item.category === 'Music'
            ? 'music'
            : 'unknown';

      const averageChangePercent = typeof parsed?.average_change_percent === 'number' && Number.isFinite(parsed.average_change_percent)
        ? parsed.average_change_percent
        : null;
      const soldRangeMin = typeof soldRange?.min === 'number' && Number.isFinite(soldRange.min) ? soldRange.min : null;
      const soldRangeMax = typeof soldRange?.max === 'number' && Number.isFinite(soldRange.max) ? soldRange.max : null;

      // Parse per-condition sold ranges, validating the structure
      const parsedSoldRangeByCondition: Record<string, { min: number; max: number }> = {};
      if (typeof soldRangeByCondition === 'object' && soldRangeByCondition !== null) {
        for (const [condition, range] of Object.entries(soldRangeByCondition)) {
          if (typeof range === 'object' && range !== null && 'min' in range && 'max' in range) {
            const min = (range as Record<string, unknown>).min;
            const max = (range as Record<string, unknown>).max;
            if (typeof min === 'number' && typeof max === 'number' && Number.isFinite(min) && Number.isFinite(max)) {
              parsedSoldRangeByCondition[condition] = { min, max };
            }
          }
        }
      }

      return {
        kind,
        averageLoose: readPriceValue(loose.value, loose.url),
        averageCib: readPriceValue(cib.value, cib.url),
        averageNew: readPriceValue(newValue.value, newValue.url),
        averageStandard: readPriceValue(standard.value, standard.url),
        averageLimited: readPriceValue(limited.value, limited.url),
        averageChangePercent,
        soldRangeMin,
        soldRangeMax,
        soldRangeByCondition: parsedSoldRangeByCondition,
      };
    } catch {
      return {
        ...empty,
        kind: item.category === 'Games' ? 'game' : item.category === 'Music' ? 'music' : 'unknown',
      };
    }
  }

  function formatPrice(value: number | null): string {
    if (value == null) return '—';
    return `$${value.toFixed(2)}`;
  }

  function formatPercentChange(value: number | null): string {
    if (value == null) return '—';
    const arrow = value >= 0 ? '↑' : '↓';
    return `${arrow} ${Math.abs(value).toFixed(2)}%`;
  }

  function soldRangeDisplay(minValue: number | null, maxValue: number | null): string {
    if (minValue == null || maxValue == null) return '—';
    return `${formatPrice(minValue)} - ${formatPrice(maxValue)}`;
  }

  function soldRangeByConditionDisplay(data: DetailPriceData, key: string): string {
    const range = data.soldRangeByCondition[key];
    if (!range) return '—';
    return `${formatPrice(range.min)} - ${formatPrice(range.max)}`;
  }

  function openPriceSource(url: string | null) {
    if (!url) return;
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  function detailPriceSummaryEntries(item: MediaItem | null, data: DetailPriceData): DetailPriceSummaryEntry[] {
    if (item?.category === 'Games') {
      return [
        { label: 'LOOSE', value: data.averageLoose.value, url: data.averageLoose.url, colorClass: 'loose' },
        { label: 'CIB', value: data.averageCib.value, url: data.averageCib.url, colorClass: 'cib' },
        { label: 'NEW', value: data.averageNew.value, url: data.averageNew.url, colorClass: 'new' },
      ];
    }

    if (item?.category === 'Music') {
      return [
        { label: 'STANDARD', value: data.averageStandard.value, url: data.averageStandard.url, colorClass: 'standard' },
        { label: 'LIMITED ED.', value: data.averageLimited.value, url: data.averageLimited.url, colorClass: 'limited' },
      ];
    }

    return [];
  }

  function detailPriceChangeEntries(item: MediaItem | null, data: DetailPriceData): { label: string; percent: number | null; colorClass: string }[] {
    if (item?.category === 'Games') {
      const base = data.averageLoose.value;
      const cibPct = (base != null && base > 0 && data.averageCib.value != null)
        ? ((data.averageCib.value - base) / base) * 100 : null;
      const newPct = (base != null && base > 0 && data.averageNew.value != null)
        ? ((data.averageNew.value - base) / base) * 100 : null;
      return [
        { label: 'LOOSE', percent: null, colorClass: 'loose' },
        { label: 'CIB', percent: cibPct, colorClass: 'cib' },
        { label: 'NEW', percent: newPct, colorClass: 'new' },
      ];
    }
    if (item?.category === 'Music') {
      const base = data.averageStandard.value;
      const limitedPct = (base != null && base > 0 && data.averageLimited.value != null)
        ? ((data.averageLimited.value - base) / base) * 100 : null;
      return [
        { label: 'STANDARD', percent: null, colorClass: 'standard' },
        { label: 'LIMITED ED.', percent: limitedPct, colorClass: 'limited' },
      ];
    }
    return [];
  }

  function formatFetchDate(value: string | null | undefined): string {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleString([], {
      month: 'numeric',
      day: 'numeric',
      year: '2-digit',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).replace(',', ' -');
  }

  function formatCurrencyCompact(value: number): string {
    return `$${value.toFixed(2)}`;
  }

  function parseCollectionPrice(item: MediaItem, preferMusicStandard: boolean): number {
    if (!item?.price_data_json) return 0;
    try {
      const parsed = JSON.parse(item.price_data_json) as Record<string, unknown>;
      const average = (parsed?.average ?? {}) as Record<string, unknown>;
      const gameCib = (average.cib ?? {}) as Record<string, unknown>;
      const musicStandard = (average.standard ?? {}) as Record<string, unknown>;
      const value = preferMusicStandard
        ? (typeof musicStandard.value === 'number' ? musicStandard.value : null)
        : (typeof gameCib.value === 'number' ? gameCib.value : null);
      return value != null && Number.isFinite(value) ? value : 0;
    } catch {
      return 0;
    }
  }

  function sumCollectionCibOrStandard(items: MediaItem[], preferMusicStandard: boolean): number {
    return items.reduce((sum, item) => sum + parseCollectionPrice(item, preferMusicStandard), 0);
  }

  function isBlankTextValue(value: string | null | undefined): boolean {
    return !value || !value.trim();
  }

  function isEmptyGameArt(item: MediaItem): boolean {
    return isBlankTextValue(item.cover_image) || isBlankTextValue(item.disc_image) || isBlankTextValue(item.spine_image);
  }

  function isEmptyGameDetails(item: MediaItem): boolean {
    return isBlankTextValue(item.notes)
      || isBlankTextValue(item.publisher)
      || isBlankTextValue(item.genres ?? item.genre)
      || isBlankTextValue(item.release_date)
      || item.year_released == null
      || isBlankTextValue(item.rating)
      || item.players == null
      || isBlankTextValue(item.cooperative);
  }

  function isEmptyMusicArt(item: MediaItem): boolean {
    return isBlankTextValue(item.cover_image);
  }

  function isEmptyMusicDetails(item: MediaItem): boolean {
    return isBlankTextValue(item.genre) || isBlankTextValue(item.release_date) || item.year_released == null;
  }

  function isEmptyPriceData(item: MediaItem): boolean {
    return isBlankTextValue(item.price_data_json);
  }

  function resetFetchToolState(key: FetchToolKey) {
    fetchToolStates = {
      ...fetchToolStates,
      [key]: createFetchToolState(),
    };
  }

  function updateFetchToolState(key: FetchToolKey, patch: Partial<FetchToolState>) {
    if (!fetchToolsOpen) return;
    fetchToolStates = {
      ...fetchToolStates,
      [key]: {
        ...fetchToolStates[key],
        ...patch,
      },
    };
  }

  function upsertFetchToolActivity(
    key: FetchToolKey,
    entryKey: string,
    line: string,
    status: FetchToolActivityEntry['status'],
    message: string,
  ) {
    if (!fetchToolsOpen) return;
    const current = fetchToolStates[key].activity;
    const index = current.findIndex((entry) => entry.key === entryKey);
    const nextEntry: FetchToolActivityEntry = { key: entryKey, line, status, message };
    const next = index === -1
      ? [...current, nextEntry]
      : current.map((entry, i) => (i === index ? nextEntry : entry));
    updateFetchToolState(key, { activity: next });
  }

  function resetAllFetchToolStates() {
    fetchToolStates = {
      gameArt: createFetchToolState(),
      gameDetails: createFetchToolState(),
      gamePrice: createFetchToolState(),
      musicArt: createFetchToolState(),
      musicDetails: createFetchToolState(),
      musicPrice: createFetchToolState(),
    };
  }

  function closeFetchToolsPopup() {
    fetchToolsOpen = false;
    fetchToolsBusy = false;
    resetAllFetchToolStates();
  }

  function openFetchToolsPopup() {
    fetchToolsOpen = true;
    adminError = '';
    adminMessage = '';
  }

  function applyGameFetchToWishlistItem(item: WishlistMediaItem, fetched: any, mode: 'art' | 'details' | 'all', force: boolean): WishlistMediaItem {
    const next = { ...item };
    if (mode === 'art' || mode === 'all') {
      const cover = typeof fetched?.coverImage === 'string' ? fetched.coverImage : '';
      const disc = typeof fetched?.discImage === 'string' ? fetched.discImage : '';
      const spine = typeof fetched?.spineImage === 'string' ? fetched.spineImage : '';
      if (cover && (force || isBlankTextValue(next.cover_image))) next.cover_image = cover;
      if (disc && (force || isBlankTextValue(next.disc_image))) next.disc_image = disc;
      if (spine && (force || isBlankTextValue(next.spine_image))) next.spine_image = spine;
    }
    if (mode === 'details' || mode === 'all') {
      const publishers = Array.isArray(fetched?.publishers)
        ? fetched.publishers.filter((entry: unknown) => typeof entry === 'string' && entry.trim())
        : [];
      const genres = Array.isArray(fetched?.gameGenres)
        ? fetched.gameGenres.filter((entry: unknown) => typeof entry === 'string' && entry.trim())
        : [];
      const notes = typeof fetched?.notes === 'string' ? fetched.notes : '';
      const cooperative = typeof fetched?.cooperative === 'string' ? fetched.cooperative : '';
      const rating = typeof fetched?.rating === 'string' ? fetched.rating : '';
      const releaseDate = typeof fetched?.release_date === 'string' ? fetched.release_date : '';
      const players = typeof fetched?.players === 'number' && Number.isFinite(fetched.players) ? fetched.players : null;
      const yearReleased = typeof fetched?.year_released === 'number' && Number.isFinite(fetched.year_released) ? fetched.year_released : null;

      if (notes && (force || isBlankTextValue(next.notes))) next.notes = notes;
      if (publishers.length && (force || isBlankTextValue(next.publisher))) next.publisher = publishers.join(', ');
      if (genres.length && (force || isBlankTextValue(next.genres ?? next.genre))) {
        next.genres = genres.join(', ');
        next.genre = genres[0];
      }
      if (releaseDate && (force || isBlankTextValue(next.release_date))) next.release_date = releaseDate;
      if (yearReleased != null && (force || next.year_released == null)) next.year_released = yearReleased;
      if (rating && (force || isBlankTextValue(next.rating))) next.rating = rating;
      if (cooperative && (force || isBlankTextValue(next.cooperative))) next.cooperative = cooperative;
      if (players != null && (force || next.players == null)) next.players = players;
    }
    return next;
  }

  function applyMusicFetchToWishlistItem(item: WishlistMediaItem, fetched: any, mode: 'art' | 'details' | 'all', force: boolean): WishlistMediaItem {
    const next = { ...item };
    if (mode === 'art' || mode === 'all') {
      const cover = typeof fetched?.coverImage === 'string' ? fetched.coverImage : '';
      if (cover && (force || isBlankTextValue(next.cover_image))) next.cover_image = cover;
    }
    if (mode === 'details' || mode === 'all') {
      const genre = typeof fetched?.genre === 'string' ? fetched.genre : '';
      const releaseDate = typeof fetched?.release_date === 'string' ? fetched.release_date : '';
      const yearReleased = typeof fetched?.year_released === 'number' && Number.isFinite(fetched.year_released) ? fetched.year_released : null;
      if (genre && (force || isBlankTextValue(next.genre))) next.genre = genre;
      if (releaseDate && (force || isBlankTextValue(next.release_date))) next.release_date = releaseDate;
      if (yearReleased != null && (force || next.year_released == null)) next.year_released = yearReleased;
    }
    return next;
  }

  function applyPriceFetchToWishlistItem(item: WishlistMediaItem, fetched: any): WishlistMediaItem {
    const next = { ...item };
    const priceDataJson = typeof fetched?.price_data_json === 'string' ? fetched.price_data_json : '';
    const priceLastFetchedAt = typeof fetched?.price_last_fetched_at === 'string' ? fetched.price_last_fetched_at : '';
    if (priceDataJson) next.price_data_json = priceDataJson;
    if (priceLastFetchedAt) next.price_last_fetched_at = priceLastFetchedAt;
    return next;
  }

  async function runFetchTool(key: FetchToolKey, includePopulated: boolean) {
    if (!isAdmin || fetchToolsBusy) return;

    type ToolSpec = {
      key: FetchToolKey;
      category: 'Games' | 'Music';
      mode: 'art' | 'details' | 'price';
      label: string;
      isEmpty: (item: MediaItem) => boolean;
      isEmptyWishlist: (item: WishlistMediaItem) => boolean;
    };

    const specs: Record<FetchToolKey, ToolSpec> = {
      gameArt: {
        key: 'gameArt',
        category: 'Games',
        mode: 'art',
        label: 'game art',
        endpointPrefix: '/api/fetch-tools/game/',
        isEmpty: isEmptyGameArt,
        isEmptyWishlist: isEmptyGameArt,
      },
      gameDetails: {
        key: 'gameDetails',
        category: 'Games',
        mode: 'details',
        label: 'game details',
        isEmpty: isEmptyGameDetails,
        isEmptyWishlist: isEmptyGameDetails,
      },
      gamePrice: {
        key: 'gamePrice',
        category: 'Games',
        mode: 'price',
        label: 'game prices',
        isEmpty: isEmptyPriceData,
        isEmptyWishlist: isEmptyPriceData,
      },
      musicArt: {
        key: 'musicArt',
        category: 'Music',
        mode: 'art',
        label: 'album art',
        isEmpty: isEmptyMusicArt,
        isEmptyWishlist: isEmptyMusicArt,
      },
      musicDetails: {
        key: 'musicDetails',
        category: 'Music',
        mode: 'details',
        label: 'album details',
        isEmpty: isEmptyMusicDetails,
        isEmptyWishlist: isEmptyMusicDetails,
      },
      musicPrice: {
        key: 'musicPrice',
        category: 'Music',
        mode: 'price',
        label: 'album prices',
        isEmpty: isEmptyPriceData,
        isEmptyWishlist: isEmptyPriceData,
      },
    };

    const spec = specs[key];
    if (!spec) return;
    const consoleScope = spec.category === 'Games' ? (fetchToolConsoleScopes[key] ?? 'all') : 'all';

    fetchToolsCancelRequested = false;
    fetchToolsBusy = true;
    resetFetchToolState(key);

    const libraryTargets = allMedia.filter((item) => item.category === spec.category)
      .filter((item) => spec.category !== 'Games' || consoleScope === 'all' || item.platform === consoleScope)
      .filter((item) => includePopulated || spec.isEmpty(item));
    const wishlistPool = spec.category === 'Games' ? gameWishlist : musicWishlist;
    const wishlistTargets = (consoleScope === 'all' ? wishlistPool : [])
      .filter((item) => includePopulated || spec.isEmptyWishlist(item));
    const total = libraryTargets.length + wishlistTargets.length;

    if (total === 0) {
      updateFetchToolState(key, {
        running: false,
        total: 0,
        processed: 0,
        progress: 100,
        showProgress: false,
        statusText: `No ${includePopulated ? '' : 'empty '}${spec.label} targets found.`,
        errorText: '',
      });
      fetchToolsBusy = false;
      return;
    }

    updateFetchToolState(key, {
      running: true,
      runningAction: includePopulated ? 'all' : 'empty',
      total,
      processed: 0,
      progress: 0,
      showProgress: true,
      statusText: `Preparing ${total} ${spec.label} item${total === 1 ? '' : 's'}...`,
      errorText: '',
      updatedCount: 0,
      activity: [],
    });

    let processed = 0;
    let updatedCount = 0;
    let errors = 0;

    for (const item of libraryTargets) {
      if (fetchToolsCancelRequested || !fetchToolsOpen) break;
      const activityKey = `library-${item.id}`;
      upsertFetchToolActivity(key, activityKey, item.title, 'running', `Processing ${processed + 1}/${total}...`);
      let activityStatus: FetchToolActivityEntry['status'] = 'success';
      let activityMessage = `No updates needed (${processed + 1}/${total}).`;
      try {
        const response = await fetch(apiPath(
          spec.mode === 'price'
            ? `/api/pricing/fetch/${item.id}`
            : `${spec.category === 'Games' ? '/api/fetch-tools/game/' : '/api/fetch-tools/music/'}${item.id}`,
        ), {
          method: 'POST',
          headers: mediaHeaders(),
          body: spec.mode === 'price' ? undefined : JSON.stringify({ mode: spec.mode, force: includePopulated }),
        });
        if (response.status === 401) {
          adminToken = '';
          localStorage.removeItem('ps2-admin-token');
          updateFetchToolState(key, { errorText: 'Session expired. Log in again.' });
          break;
        }
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          errors += 1;
          const message = payload?.detail || `Could not fetch ${spec.label} for ${item.title}.`;
          updateFetchToolState(key, { errorText: message });
          activityStatus = 'error';
          activityMessage = message;
        } else if (spec.mode === 'price') {
          updatedCount += 1;
          upsertMediaItem(payload as MediaItem);
          activityMessage = `Updated (${processed + 1}/${total}).`;
        } else if (payload?.changed) {
          updatedCount += 1;
          activityMessage = `Updated (${processed + 1}/${total}).`;
        }
      } catch {
        errors += 1;
        const message = `Could not fetch ${spec.label} for ${item.title}.`;
        updateFetchToolState(key, { errorText: message });
        activityStatus = 'error';
        activityMessage = message;
      }
      upsertFetchToolActivity(key, activityKey, item.title, activityStatus, activityMessage);
      processed += 1;
      updateFetchToolState(key, {
        processed,
        progress: Math.round((processed / total) * 100),
        updatedCount,
        statusText: `Processing ${processed}/${total}... Updated ${updatedCount}.`,
      });
      if (fetchToolsCancelRequested || !fetchToolsOpen) break;
      await sleep(1100);
    }

    if (fetchToolsCancelRequested || processed < total) {
      updateFetchToolState(key, {
        running: false,
        runningAction: null,
        statusText: `Stopped at ${processed}/${total}.`,
      });
      fetchToolsBusy = false;
      await Promise.all([loadAllMedia(), loadMedia()]);
      return;
    }

    if (wishlistTargets.length) {
      const wishlistKind = spec.category === 'Games' ? 'games' : 'music';
      for (const item of wishlistTargets) {
        if (fetchToolsCancelRequested || !fetchToolsOpen) break;
        const activityKey = `wishlist-${item.wishlistId}`;
        upsertFetchToolActivity(key, activityKey, item.title, 'running', `Processing ${processed + 1}/${total}...`);
        let activityStatus: FetchToolActivityEntry['status'] = 'success';
        let activityMessage = `No updates needed (${processed + 1}/${total}).`;
        try {
          if (wishlistKind === 'games') {
            const response = await fetch(apiPath(spec.mode === 'price' ? '/api/pricing/game-data' : '/api/launchbox/game-data'), {
              method: 'POST',
              headers: mediaHeaders(),
              body: JSON.stringify(
                spec.mode === 'price'
                  ? { title: item.title, platform: item.platform ?? selectedConsole ?? '' }
                  : { title: item.title, platform: item.platform ?? selectedConsole ?? '', item_id: null },
              ),
            });
            if (response.status === 401) {
              adminToken = '';
              localStorage.removeItem('ps2-admin-token');
              updateFetchToolState(key, { errorText: 'Session expired. Log in again.' });
              break;
            }
            const payload = await response.json().catch(() => null);
            if (response.ok) {
              const nextItem = spec.mode === 'price'
                ? applyPriceFetchToWishlistItem(item, payload)
                : applyGameFetchToWishlistItem(item, payload, spec.mode, includePopulated);
              if (JSON.stringify(nextItem) !== JSON.stringify(item)) {
                updatedCount += 1;
                gameWishlist = gameWishlist.map((entry) => entry.wishlistId === item.wishlistId ? nextItem : entry);
                if (selectedWishlistItem?.wishlistId === item.wishlistId) selectedWishlistItem = nextItem;
                persistGameWishlist();
                activityMessage = `Updated (${processed + 1}/${total}).`;
              }
            } else {
              errors += 1;
              const message = payload?.detail || `Could not fetch ${spec.label} for ${item.title} wish list entry.`;
              updateFetchToolState(key, { errorText: message });
              activityStatus = 'error';
              activityMessage = message;
            }
          } else {
            const response = await fetch(apiPath(spec.mode === 'price' ? '/api/pricing/music-data' : '/api/deezer/music-data'), {
              method: 'POST',
              headers: mediaHeaders(),
              body: JSON.stringify({ title: item.title, artist: item.artist ?? '' }),
            });
            if (response.status === 401) {
              adminToken = '';
              localStorage.removeItem('ps2-admin-token');
              updateFetchToolState(key, { errorText: 'Session expired. Log in again.' });
              break;
            }
            const payload = await response.json().catch(() => null);
            if (response.ok) {
              const nextItem = spec.mode === 'price'
                ? applyPriceFetchToWishlistItem(item, payload)
                : applyMusicFetchToWishlistItem(item, payload, spec.mode, includePopulated);
              if (JSON.stringify(nextItem) !== JSON.stringify(item)) {
                updatedCount += 1;
                musicWishlist = musicWishlist.map((entry) => entry.wishlistId === item.wishlistId ? nextItem : entry);
                if (selectedWishlistItem?.wishlistId === item.wishlistId) selectedWishlistItem = nextItem;
                persistMusicWishlist();
                activityMessage = `Updated (${processed + 1}/${total}).`;
              }
            } else {
              errors += 1;
              const message = payload?.detail || `Could not fetch ${spec.label} for ${item.title} wish list entry.`;
              updateFetchToolState(key, { errorText: message });
              activityStatus = 'error';
              activityMessage = message;
            }
          }
        } catch {
          errors += 1;
          const message = `Could not fetch ${spec.label} for ${item.title} wish list entry.`;
          updateFetchToolState(key, { errorText: message });
          activityStatus = 'error';
          activityMessage = message;
        }
        upsertFetchToolActivity(key, activityKey, item.title, activityStatus, activityMessage);
        processed += 1;
        updateFetchToolState(key, {
          processed,
          progress: Math.round((processed / total) * 100),
          updatedCount,
          statusText: `Processing ${processed}/${total}... Updated ${updatedCount}.`,
        });
        if (fetchToolsCancelRequested || !fetchToolsOpen) break;
        await sleep(1100);
      }
    }

    updateFetchToolState(key, {
      running: false,
      runningAction: null,
      progress: 100,
      updatedCount,
      statusText: `Done. Updated ${updatedCount}/${total}.`,
      errorText: errors > 0 ? `${errors} item${errors === 1 ? '' : 's'} failed. See latest error above.` : fetchToolStates[key].errorText,
    });
    fetchToolsBusy = false;
    await Promise.all([loadAllMedia(), loadMedia()]);
  }

  function getRunningFetchToolKey() {
    return (Object.entries(fetchToolStates).find(([, state]) => state.running)?.[0] ?? null) as FetchToolKey | null;
  }

  function cancelFetchToolsOperation() {
    if (!fetchToolsBusy) return;
    fetchToolsCancelRequested = true;
    const runningKey = getRunningFetchToolKey();
    if (runningKey) {
      updateFetchToolState(runningKey, { statusText: 'Cancelling...' });
    }
  }

  function upsertMediaItem(updated: MediaItem) {
    allMedia = allMedia.map((entry) => entry.id === updated.id ? updated : entry);
    media = media.map((entry) => entry.id === updated.id ? updated : entry);
    if (selectedItem?.id === updated.id) {
      selectedItem = updated;
    }
  }

  async function fetchDetailPriceData() {
    if (!detailItem || detailIsWishlist || !detailItem.id || detailPriceFetchBusy) return;

    detailPriceFetchError = '';
    detailPriceFetchStatus = 'Fetching latest pricing data...';
    detailPriceFetchProgress = 12;
    detailPriceFetchBusy = true;
    try {
      const response = await fetch(apiPath(`/api/pricing/fetch/${detailItem.id}`), {
        method: 'POST',
        headers: mediaHeaders(),
      });
      detailPriceFetchProgress = 62;

      if (response.status === 401) {
        adminToken = '';
        localStorage.removeItem('ps2-admin-token');
        detailPriceFetchError = 'Session expired. Log in again.';
        detailPriceFetchStatus = 'Fetch failed.';
        detailPriceFetchProgress = 100;
        return;
      }

      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        detailPriceFetchError = payload?.detail || 'Could not fetch price data.';
        detailPriceFetchStatus = 'Fetch failed.';
        detailPriceFetchProgress = 100;
        return;
      }

      upsertMediaItem(payload as MediaItem);
      detailPriceFetchStatus = 'Price data updated.';
      detailPriceFetchProgress = 100;
    } catch {
      detailPriceFetchError = 'Could not fetch price data.';
      detailPriceFetchStatus = 'Fetch failed.';
      detailPriceFetchProgress = 100;
    } finally {
      detailPriceFetchBusy = false;
    }
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

  function renderStars(value: number | null, max = 5): string {
    if (value == null) return '';
    const filled = Math.max(0, Math.min(max, Math.round(value)));
    return '★'.repeat(filled) + '☆'.repeat(max - filled);
  }

  async function saveDetailRatingChanges() {
    if (!detailItem || !detailRatingDirty || detailRatingSaving) return;

    detailRatingSaving = true;
    detailRatingMessage = '';
    const nextRating = normalizeStarRating(detailEditedStarRating);

    try {
      if (detailIsWishlist && selectedWishlistItem) {
        updateWishlistItemStarRating(selectedWishlistItem, nextRating);
        detailInitialStarRating = nextRating;
        detailRatingMessage = 'Saved.';
        return;
      }

      if (!detailItem.id) {
        detailRatingMessage = 'Could not save changes.';
        return;
      }

      if (adminToken) {
        const payload = {
          ...detailItem,
          star_rating: nextRating,
        };
        const response = await fetch(apiPath(`/api/media/${detailItem.id}`), {
          method: 'PUT',
          headers: mediaHeaders(),
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          detailRatingMessage = 'Could not save changes.';
          return;
        }
        updateLibraryItemStarRating(detailItem.id, nextRating);
      } else {
        localStarRatingOverrides[String(detailItem.id)] = nextRating;
        persistLocalStarRatingOverrides();
        updateLibraryItemStarRating(detailItem.id, nextRating);
      }

      detailInitialStarRating = nextRating;
      detailRatingMessage = 'Saved.';
    } catch {
      detailRatingMessage = 'Could not save changes.';
    } finally {
      detailRatingSaving = false;
    }
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
    starDropdownOpen = false;
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

  function canFetchMusicAlbumData() {
    const title = (adminForm.title ?? '').trim();
    const artist = (adminForm.artist ?? '').trim();
    return title.length > 0 && artist.length > 0;
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
    if (source === 'libretro') return 'Libretro';
    if (source === 'wikidata') return 'Wikidata';
    if (source === 'cache') return 'cache';
    return 'backup source';
  }

  function unavailableArtLabel(resource: string, platform: string) {
    const normalized = resource.trim().toLowerCase();
    if (normalized === 'cover') return 'Box Art';
    if (normalized === 'spine') return 'Spine Art';
    if (normalized === 'cart') return 'Cart Art';
    if (normalized === 'disc') {
      const platformKey = platform.trim().toLowerCase();
      if (platformKey.includes('nintendo ds') || platformKey.includes('3ds') || platformKey.includes('game boy')) {
        return 'Cart Art';
      }
      return 'Disc Art';
    }
    return '';
  }

  function formatLaunchboxUnavailableStatus(resources: unknown, platform: string) {
    if (!Array.isArray(resources)) return '';
    const labels = resources
      .filter((entry): entry is string => typeof entry === 'string')
      .map((entry) => unavailableArtLabel(entry, platform))
      .filter((entry) => entry.trim().length > 0);
    if (!labels.length) return '';
    return `LaunchBox did not have ${labels.join(', ')} for this game. Missing fields were left unchanged.`;
  }

  function closeLaunchboxArtPicker() {
    launchboxArtPickerOpen = false;
    launchboxArtPickerBusy = false;
    launchboxArtPickerError = '';
    launchboxArtPickerStatus = '';
    launchboxArtOptions = [];
    launchboxArtOptionsBySource = { discogs: [], deezer: [] };
    launchboxArtPickerField = null;
    launchboxArtPickerSource = 'launchbox';
  }

  function clearAdminArtField(field: GameArtField) {
    adminForm = {
      ...adminForm,
      [field]: null,
    } as AdminForm;
    adminMessage = `${adminArtLabel(field)} cleared.`;
    adminError = '';
    launchboxFetchError = '';
  }

  function adminArtPickerSource(): ArtPickerSource {
    return libraryAdminTab === 'music' ? 'music' : 'launchbox';
  }

  function adminArtPickerLabel(field: GameArtField) {
    if (libraryAdminTab === 'music' && field === 'cover_image') return 'Album Art';
    return adminArtLabel(field);
  }

  async function openLaunchboxArtPicker(field: GameArtField) {
    if (launchboxArtPickerBusy) return;

    launchboxFetchError = '';
    adminError = '';
    adminMessage = '';

    const pickerSource = adminArtPickerSource();
    if (pickerSource === 'music') {
      if (!canFetchMusicAlbumData()) {
        launchboxFetchError = 'Enter an album title and artist first.';
        return;
      }
    } else if (!canFetchLaunchBoxGameData()) {
      launchboxFetchError = 'Enter a game title and select a platform first.';
      return;
    }

    launchboxArtPickerOpen = true;
    launchboxArtPickerBusy = true;
    launchboxArtPickerError = '';
    launchboxArtPickerStatus = '';
    launchboxArtPickerField = field;
    launchboxArtPickerSource = pickerSource;
    launchboxArtOptions = [];
    launchboxArtOptionsBySource = { discogs: [], deezer: [] };

    try {
      const isMusicPicker = launchboxArtPickerSource === 'music';
      const response = await fetch(apiPath(isMusicPicker ? '/api/discogs/music-art-options' : '/api/launchbox/game-art-options'), {
        method: 'POST',
        headers: mediaHeaders(),
        body: JSON.stringify(isMusicPicker
          ? {
              title: (adminForm.title ?? '').trim(),
              artist: (adminForm.artist ?? '').trim(),
            }
          : {
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
        launchboxArtPickerError = data?.detail ?? 'Could not find art options for this item from any source.';
        return;
      }

      const statusMessage = typeof data?.status_message === 'string' ? data.status_message.trim() : '';

      launchboxArtOptions = Array.isArray(data?.options)
        ? data.options.filter((entry: unknown) => typeof entry === 'string' && entry.trim())
        : [];

      if (isMusicPicker) {
        const sourceGroups = (data && typeof data === 'object' ? data.options_by_source : null) as
          | { discogs?: unknown; deezer?: unknown }
          | null;

        const discogsOptions = Array.isArray(sourceGroups?.discogs)
          ? sourceGroups.discogs.filter((entry: unknown) => typeof entry === 'string' && entry.trim()) as string[]
          : [];
        const deezerOptions = Array.isArray(sourceGroups?.deezer)
          ? sourceGroups.deezer.filter((entry: unknown) => typeof entry === 'string' && entry.trim()) as string[]
          : [];

        launchboxArtOptionsBySource = {
          discogs: discogsOptions,
          deezer: deezerOptions,
        };

        if (!launchboxArtOptions.length) {
          launchboxArtOptions = [...discogsOptions, ...deezerOptions];
        }
      }

      if (!launchboxArtOptions.length) {
        launchboxArtPickerError = statusMessage || 'No art options were returned for this item.';
      } else if (statusMessage) {
        launchboxArtPickerStatus = statusMessage;
      }
    } catch {
      launchboxArtPickerError = 'Could not fetch art options from any source.';
    } finally {
      launchboxArtPickerBusy = false;
    }
  }

  function chooseLaunchboxArtOption(imageData: string) {
    if (!launchboxArtPickerField || !imageData) return;
    const label = adminArtPickerLabel(launchboxArtPickerField);
    adminForm = {
      ...adminForm,
      [launchboxArtPickerField]: imageData,
    } as AdminForm;
    adminMessage = `${label} selected from available sources.`;
    adminError = '';
    launchboxFetchError = '';
    closeLaunchboxArtPicker();
  }

  function setLibraryAdminTab(tab: AdminLibraryTab) {
    libraryAdminTab = tab;
    adminListPage = 0;
    adminSearchCategory = tab === 'music' ? 'Music' : 'Games';
    adminSearchPlatform = tab === 'games' ? (selectedConsole ?? 'All') : 'All';
    if (adminEditingId === null) {
      resetAdminForm(tab === 'music' ? 'Music' : 'Games');
    }
  }

  function setWishlistAdminSection(section: WishlistAdminSection) {
    wishlistAdminSection = section;
    adminListPage = 0;
    adminSearchCategory = section === 'music' ? 'Music' : 'Games';
    adminSearchPlatform = section === 'games' ? (selectedConsole ?? 'All') : 'All';
    if (section === 'console') {
      resetWishlistSystemForm();
    } else if (adminEditingId === null) {
      resetAdminForm(section === 'music' ? 'Music' : 'Games');
    }
  }

  function activeBulkUploadSection(): BulkUploadSection {
    return libraryAdminTab === 'wishlists' ? wishlistAdminSection : libraryAdminTab;
  }

  function resetBulkUploadState(clearText = true) {
    bulkResults = [];
    if (clearText) bulkText = '';
    bulkTotalCount = 0;
    bulkProcessedCount = 0;
    bulkProgressPercent = 0;
    bulkStatusText = '';
    bulkErrorText = '';
  }

  function bulkUploadHintText() {
    const section = activeBulkUploadSection();
    if (section === 'console') {
      return 'One console per line. Optional: System Name | Short Name | Logo URL | disc|cartridge|hybrid';
    }
    if (section === 'games') {
      return 'One game title per line. Platform comes from the filter above.';
    }
    return 'One album per line: Album Title - Artist';
  }

  function bulkUploadPlaceholder() {
    const section = activeBulkUploadSection();
    if (section === 'console') {
      return 'PlayStation 5\nNintendo Switch | NSW\nSega Saturn | SAT | https://example.com/logo.png | disc';
    }
    if (section === 'games') {
      return 'Final Fantasy VII\nShadow of the Colossus';
    }
    return 'Nevermind - Nirvana\nAbbey Road - The Beatles';
  }

  function bulkUploadActionLabel() {
    const section = activeBulkUploadSection();
    if (section === 'console') return 'Upload Consoles';
    if (section === 'games') return 'Upload Games';
    return 'Upload Albums';
  }

  function normalizeBulkKey(...parts: Array<string | null | undefined>) {
    return parts.map((part) => (part ?? '').trim().toLowerCase()).join('::');
  }

  function buildWishlistConsoleFromBulkLine(line: string) {
    const segments = line.split('|').map((segment) => segment.trim());
    const name = segments[0] ?? '';
    if (!name) {
      return { error: 'System name is required.' } as const;
    }

    const rawCaseType = (segments[3] ?? '').toLowerCase();
    const caseType = rawCaseType === 'disc' || rawCaseType === 'cartridge' || rawCaseType === 'hybrid'
      ? rawCaseType
      : undefined;

    const shortName = (segments[1] || name.slice(0, 3)).trim().toUpperCase();
    return {
      item: {
        id: name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || createWishlistId('console'),
        wishlistId: createWishlistId('console'),
        wishlistKind: 'console' as const,
        name,
        shortName,
        logo: shortName,
        logoImage: segments[2] || null,
        caseType,
        appearancePreset: null,
      },
    } as const;
  }

  function splitBulkMusicLine(line: string) {
    if (line.includes('|')) {
      const parts = line.split('|').map((part) => part.trim()).filter(Boolean);
      if (parts.length >= 2) {
        return { title: parts[0], artist: parts.slice(1).join(' | ') };
      }
    }

    const separatorIndex = line.lastIndexOf(' - ');
    if (separatorIndex <= 0) return null;

    const title = line.slice(0, separatorIndex).trim();
    const artist = line.slice(separatorIndex + 3).trim();
    if (!title || !artist) return null;
    return { title, artist };
  }

  function buildWishlistMediaFromBulkLine(kind: 'games' | 'music', line: string, platform: string) {
    if (kind === 'games') {
      const title = normalizeGameTitle(line);
      if (!title) {
        return { error: 'Game title is required.' } as const;
      }

      return {
        item: {
          id: createWishlistMediaId(),
          wishlistId: createWishlistId('games'),
          wishlistKind: 'games' as const,
          title,
          category: 'Games',
          platform,
          genre: '',
          genres: null,
          year_released: null,
          release_date: null,
          rating: null,
          players: null,
          cooperative: null,
          artist: null,
          publisher: null,
          format: null,
          region: null,
          cover_image: null,
          spine_image: null,
          disc_image: null,
          tags: null,
          notes: null,
          star_rating: null,
        },
      } as const;
    }

    const parsed = splitBulkMusicLine(line);
    if (!parsed) {
      return { error: 'Use Album Title - Artist or Album Title | Artist.' } as const;
    }

    return {
      item: {
        id: createWishlistMediaId(),
        wishlistId: createWishlistId('music'),
        wishlistKind: 'music' as const,
        title: parsed.title,
        category: 'Music',
        platform: null,
        genre: '',
        genres: null,
        year_released: null,
        release_date: null,
        rating: null,
        players: null,
        cooperative: null,
        artist: parsed.artist,
        publisher: null,
        format: null,
        region: null,
        cover_image: null,
        spine_image: null,
        disc_image: null,
        tags: null,
        notes: null,
        star_rating: null,
      },
    } as const;
  }

  async function bulkUploadWishlist(lines: string[], bulkPlatform: string) {
    const nextResults: { line: string; status: 'success' | 'error'; message: string }[] = [];
    let successCount = 0;
    let errorCount = 0;
    const section = wishlistAdminSection;
    const seenKeys = new Set<string>();
    const existingKeys = new Set(
      (section === 'console'
        ? consoleWishlist.map((item) => normalizeBulkKey(item.name))
        : section === 'games'
          ? gameWishlist.map((item) => normalizeBulkKey(item.title, item.platform))
          : musicWishlist.map((item) => normalizeBulkKey(item.title, item.artist)))
    );

    for (const line of lines) {
      let uploadError = '';

      if (section === 'console') {
        const built = buildWishlistConsoleFromBulkLine(line);
        if ('error' in built) {
          uploadError = built.error;
        } else {
          const dedupeKey = normalizeBulkKey(built.item.name);
          if (existingKeys.has(dedupeKey) || seenKeys.has(dedupeKey)) {
            uploadError = 'Console is already on the wish list.';
          } else {
            seenKeys.add(dedupeKey);
            consoleWishlist = [built.item, ...consoleWishlist];
            persistConsoleWishlist();
            successCount += 1;
            nextResults.push({ line, status: 'success', message: `Added: ${built.item.name}` });
          }
        }
      } else {
        const built = buildWishlistMediaFromBulkLine(section, line, bulkPlatform);
        if ('error' in built) {
          uploadError = built.error;
        } else {
          const dedupeKey = section === 'games'
            ? normalizeBulkKey(built.item.title, built.item.platform)
            : normalizeBulkKey(built.item.title, built.item.artist);
          if (existingKeys.has(dedupeKey) || seenKeys.has(dedupeKey)) {
            uploadError = section === 'games'
              ? 'Game is already on the wish list for this platform.'
              : 'Album is already on the wish list.';
          } else {
            seenKeys.add(dedupeKey);
            if (section === 'games') {
              gameWishlist = [built.item, ...gameWishlist];
              persistGameWishlist();
            } else {
              musicWishlist = [built.item, ...musicWishlist];
              persistMusicWishlist();
            }
            successCount += 1;
            nextResults.push({ line, status: 'success', message: `Added: ${built.item.title}` });
          }
        }
      }

      if (uploadError) {
        errorCount += 1;
        nextResults.push({ line, status: 'error', message: `Error: ${uploadError}` });
      }

      bulkProcessedCount += 1;
      bulkProgressPercent = Math.round((bulkProcessedCount / bulkTotalCount) * 100);
      bulkResults = [...nextResults];
      const remaining = Math.max(0, bulkTotalCount - bulkProcessedCount);
      bulkStatusText = `Processed ${bulkProcessedCount}/${bulkTotalCount}. ${remaining} remaining. ${successCount} succeeded, ${errorCount} failed.`;
    }

    if (errorCount > 0) {
      bulkErrorText = `${errorCount} item${errorCount === 1 ? '' : 's'} failed. See details below.`;
    }
    adminMessage = successCount > 0
      ? `Added ${successCount} ${successCount === 1 ? 'item' : 'items'} to the wish list.`
      : '';

    if (libraryView === 'wishlist') {
      await loadMedia(category, selectedConsole);
    }
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
    const fallbackBulkPlatform = (selectedConsole ?? activeConsole?.name ?? '').trim();
    const bulkPlatform = activeBulkUploadSection() === 'games'
      ? (adminSearchPlatform === 'All' ? fallbackBulkPlatform : adminSearchPlatform.trim())
      : '';
    if (activeBulkUploadSection() === 'games' && !bulkPlatform) {
      adminError = 'Select a platform filter above before bulk uploading games.';
      bulkErrorText = adminError;
      bulkStatusText = 'Upload blocked: select a platform first.';
      bulkBusy = false;
      return;
    }

    if (libraryAdminTab === 'wishlists') {
      try {
        await bulkUploadWishlist(lines, bulkPlatform);
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
      return;
    }

    const endpointCandidates = libraryAdminTab === 'games'
      ? ['/api/bulk/games', '/api/bulk-games', '/api/games/bulk']
      : ['/api/bulk/music', '/api/bulk-music', '/api/music/bulk'];
    const nextResults: { line: string; status: 'success' | 'error'; message: string }[] = [];
    let successCount = 0;
    let errorCount = 0;
    let unavailableResourceCount = 0;

    try {
      for (const line of lines) {
        try {
          let response: Response | null = null;
          const platformCandidates = libraryAdminTab === 'games'
            ? (() => {
              const aliases = launchboxPlatformCandidates(bulkPlatform);
              return aliases.length ? aliases : [bulkPlatform];
            })()
            : [''];

          endpointLoop: for (let endpointIndex = 0; endpointIndex < endpointCandidates.length; endpointIndex += 1) {
            const endpoint = endpointCandidates[endpointIndex];
            for (const attemptedPlatform of platformCandidates) {
              const nextResponse = await fetch(apiPath(endpoint), {
                method: 'POST',
                headers: mediaHeaders(),
                body: JSON.stringify(
                  libraryAdminTab === 'games'
                    ? { items: [line], platform: attemptedPlatform }
                    : { items: [line] }
                ),
              });

              response = nextResponse;
              // Retry legacy routes and platform aliases only for likely route/match issues.
              if (![404, 405, 409].includes(nextResponse.status)) {
                break endpointLoop;
              }
            }
          }

          if (!response) {
            throw new Error('No bulk endpoint response received.');
          }

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
            const statusNote = typeof singleResult?.status_note === 'string' ? singleResult.status_note.trim() : '';
            const unavailableResources = Array.isArray(singleResult?.unavailable_resources)
              ? singleResult.unavailable_resources.filter((entry: unknown) => typeof entry === 'string' && entry.trim())
              : [];
            if (status === 'success') {
              successCount += 1;
              if (statusNote || unavailableResources.length) {
                unavailableResourceCount += 1;
              }
            } else {
              errorCount += 1;
            }
            nextResults.push({
              line: singleResult?.line ?? line,
              status,
              message: status === 'success'
                ? (statusNote
                  ? `Added: ${singleResult?.title ?? 'Created item'} (${statusNote})`
                  : `Added: ${singleResult?.title ?? 'Created item'}`)
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
      if (unavailableResourceCount > 0) {
        bulkErrorText = `${unavailableResourceCount} successful item${unavailableResourceCount === 1 ? '' : 's'} had missing LaunchBox artwork resources. See details below.`;
      } else if (errorCount > 0) {
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

  async function fetchLaunchBoxGameData(launchboxUrlOverride?: string | Event) {
    launchboxFetchError = '';
    adminError = '';
    adminMessage = '';
    const manualLaunchboxUrl = typeof launchboxUrlOverride === 'string'
      ? launchboxUrlOverride.trim()
      : '';
    if (!manualLaunchboxUrl && !canFetchLaunchBoxGameData()) {
      launchboxFetchError = 'Enter a game title and select a platform first.';
      return;
    }

    if (manualLaunchboxUrl && !manualLaunchboxUrl.includes('launchbox-app.com')) {
      launchboxFetchError = 'Enter a valid LaunchBox game details URL.';
      return;
    }

    launchboxFetchBusy = true;
    try {
      const title = (adminForm.title ?? '').trim();
      const requestedPlatform = ((adminForm.platform ?? '').trim() || (selectedConsole ?? '').trim());
      if (!requestedPlatform) {
        launchboxFetchError = 'Select a platform first.';
        return;
      }

      const platformCandidates = manualLaunchboxUrl ? [requestedPlatform] : launchboxPlatformCandidates(requestedPlatform);
      const endpointCandidates = ['/api/launchbox/game-data'];

      let response: Response | null = null;
      let data: any = null;
      let lastErrorDetail = '';

      outer: for (const endpoint of endpointCandidates) {
        for (const platform of platformCandidates) {
          const nextResponse = await fetch(apiPath(endpoint), {
            method: 'POST',
            headers: mediaHeaders(),
            body: JSON.stringify({
              title,
              platform,
              item_id: adminForm.id ?? null,
              launchbox_url: manualLaunchboxUrl || null,
            }),
          });

          if (nextResponse.status === 401) {
            adminToken = '';
            localStorage.removeItem('ps2-admin-token');
            adminError = 'Session expired. Log in again.';
            return;
          }

          const nextData = await nextResponse.json().catch(() => null);
          response = nextResponse;
          data = nextData;

          if (nextResponse.ok) {
            break outer;
          }

          lastErrorDetail = typeof nextData?.detail === 'string' ? nextData.detail : '';

          // Continue trying aliases/endpoints only for match/path issues.
          if (![404, 405, 502].includes(nextResponse.status)) {
            break outer;
          }
        }
      }

      if (!response) {
        launchboxFetchError = 'Could not fetch game data from available sources.';
        return;
      }

      if (!response.ok) {
        launchboxFetchError = lastErrorDetail || data?.detail || `LaunchBox request failed (${response.status}).`;
        return;
      }

      const sourceLabel = formatDataSourceLabel(data?.data_source);
      const unavailableStatus = formatLaunchboxUnavailableStatus(
        data?.launchbox_unavailable_resources,
        requestedPlatform,
      );

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
      launchboxFetchError = unavailableStatus;
    } catch {
      launchboxFetchError = 'Could not fetch game data from available sources.';
    } finally {
      launchboxFetchBusy = false;
    }
  }

  async function fetchLaunchBoxGameDataFromUrl() {
    const manualLaunchboxUrl = (launchboxManualUrl ?? '').trim();
    if (!manualLaunchboxUrl) {
      launchboxFetchError = 'Enter a LaunchBox game details URL first.';
      return;
    }
    await fetchLaunchBoxGameData(manualLaunchboxUrl);
  }

  async function fetchMusicAlbumData() {
    musicFetchError = '';
    adminError = '';
    adminMessage = '';
    if (!canFetchMusicAlbumData()) {
      musicFetchError = 'Enter an album title and artist first.';
      return;
    }

    musicFetchBusy = true;
    try {
      const response = await fetch(apiPath('/api/deezer/music-data'), {
        method: 'POST',
        headers: mediaHeaders(),
        body: JSON.stringify({
          title: (adminForm.title ?? '').trim(),
          artist: (adminForm.artist ?? '').trim(),
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
        musicFetchError = data?.detail || `Deezer request failed (${response.status}).`;
        return;
      }

      const nextGenre = typeof data?.genre === 'string' ? data.genre.trim() : '';
      adminForm = {
        ...adminForm,
        title: data?.title ?? adminForm.title,
        artist: data?.artist ?? adminForm.artist,
        musicGenre: nextGenre || adminForm.musicGenre,
        release_date: normalizeDateForInput(data?.release_date) || adminForm.release_date,
        year_released: data?.year_released ? String(data.year_released) : adminForm.year_released,
        cover_image: data?.coverImage ?? adminForm.cover_image,
      };
      if (nextGenre) {
        adminMusicGenreChoice = nextGenre;
      }
      adminMessage = 'Music data loaded from Deezer.';
    } catch {
      musicFetchError = 'Could not fetch music data from Deezer.';
    } finally {
      musicFetchBusy = false;
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
    const response = await fetch(apiPath('/api/media'));
    if (!response.ok) return;
    const data = await response.json();
    allMedia = applyLocalStarRatingOverrides(data);
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

    if (libraryView === 'wishlist') {
      media = nextCategory === 'Music'
        ? [...musicWishlist]
        : gameWishlist.filter((item) => item.platform === nextConsole);
      libraryLoading = false;
      page = 0;
      librarySearch = '';
      librarySearchOpen = false;
      libraryPlayersFilter = null;
      playersDropdownOpen = false;
      libraryStarFilter = null;
      starDropdownOpen = false;
      return;
    }

    const params = new URLSearchParams();
    params.set('category', nextCategory);
    if (nextCategory === 'Games' && nextConsole) {
      params.set('platform', nextConsole);
    }

    const response = await fetch(apiPath(`/api/media?${params.toString()}`));
    if (requestId !== mediaLoadRequestId) return;

    if (!response.ok) {
      libraryLoading = false;
      media = [];
      return;
    }

    const data = await response.json();
    if (requestId !== mediaLoadRequestId) return;

    media = applyLocalStarRatingOverrides(data);
    libraryLoading = false;
    page = 0;
    librarySearch = '';
    librarySearchOpen = false;
    libraryPlayersFilter = null;
    playersDropdownOpen = false;
    libraryStarFilter = null;
    starDropdownOpen = false;
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

  function revealBootOptions(options: { markError?: boolean; resetStarted?: boolean } = {}) {
    if (options.markError) {
      bootError = true;
    }
    if (options.resetStarted) {
      bootStarted = false;
    }
    bootTextVisible = true;
    bootResumeAtSix = false;
    clearBootRescueTimer();
    clearBootPlaybackRetry();
    clearBootHardFailTimer();
  }

  function tryBootVideoFailover() {
    if (stage !== 'boot' || bootTextVisible) return false;
    if (bootSourceIndex >= BOOT_VIDEO_SOURCES.length - 1) return false;

    bootSourceIndex += 1;
    bootVideoSource = BOOT_VIDEO_SOURCES[bootSourceIndex] ?? bootVideoSource;
    bootError = false;
    bootStarted = false;

    clearBootRescueTimer();
    clearBootPlaybackRetry();
    clearBootHardFailTimer();

    if (bootVideoRef) {
      bootVideoRef.load();
    }

    void queueBootStart();
    return true;
  }

  function armBootHardFailTimer() {
    clearBootHardFailTimer();
    bootHardFailTimeout = setTimeout(() => {
      if (stage !== 'boot' || bootTextVisible) return;
      bootError = !bootVideoRef || bootVideoRef.readyState < 1;
      if (tryBootVideoFailover()) return;
      revealBootOptions({ resetStarted: true });
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
      if (tryBootVideoFailover()) return;
      revealBootOptions({ resetStarted: true });
    }, BOOT_RESCUE_TIMEOUT_MS);
  }

  function armBootPlaybackRetry() {
    clearBootPlaybackRetry();
    bootPlaybackRetryInterval = setInterval(() => {
      if (stage !== 'boot' || bootTextVisible || !bootVideoRef) {
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
      video.setAttribute('webkit-playsinline', 'true');
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
    bootResumeAtSix = true;
    bootStartAt = BOOT_SKIP_TIME;

    if (!bootVideoRef) {
      revealBootOptions();
      return;
    }

    bootVideoRef.currentTime = BOOT_SKIP_TIME;
    revealBootOptions();

    if (bootVideoRef.paused) {
      void bootVideoRef.play().catch(() => {
        revealBootOptions({ markError: true, resetStarted: true });
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
      if (tryBootVideoFailover()) return;
      revealBootOptions({ markError: true, resetStarted: true });
    }
  }

  function isBootSpaceKey(event: KeyboardEvent) {
    return event.code === 'Space' || event.key === ' ' || event.key === 'Spacebar';
  }

  function isBootMuteKey(event: KeyboardEvent) {
    return event.key.toLowerCase() === 'm';
  }

  async function handleBootPick(categoryName: Category) {
    bootHover = categoryName;
    libraryView = 'owned';
    selectedWishlistConsole = null;
    selectedWishlistItem = null;

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
    hoveredConsole = consoleName;
    consoleHeaderIdleVisible = false;
    consoleHeaderHoverVisible = true;
    clearConsoleHeaderSwapTimeout();
    selectedConsole = consoleName;
    if (libraryView === 'wishlist') {
      void loadMedia('Games', consoleName);
      return;
    }

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
    detailPriceExpanded = false;
    selectedWishlistItem = isWishlistMediaItem(item) ? item : null;
    selectedItem = item;
    launchItemId = item.id;
    void transitionTo(
      { stage: 'details', category, console: selectedConsole, itemId: item.id, page },
      { fadeMs: 900, zoomItemId: item.id },
    );
  }

  function closeDetails() {
    closeConfirm();
    selectedWishlistItem = null;
    detailPriceExpanded = false;
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
    if (selectedWishlistConsole) {
      closeWishlistConsoleDetails();
      return;
    }

    if (libraryView === 'wishlist') {
      closeWishlistView();
      return;
    }

    if (stage === 'console') {
      void returnToBootSmooth();
      return;
    }

    if (stage === 'library' && category === 'Music') {
      void returnToBootSmooth();
      return;
    }

    if (stage === 'library' && category === 'Games') {
      hoveredConsole = selectedConsole;
      consoleHeaderIdleVisible = false;
      consoleHeaderHoverVisible = true;
      clearConsoleHeaderSwapTimeout();

      // Go directly back to console select, skipping any pagination history entries
      void transitionTo(
        { stage: 'console', category: 'Games', console: selectedConsole, itemId: null, page: 0 },
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
    launchboxManualUrl = '';
    adminForm = emptyAdminForm(category);
    wishlistEditingId = null;
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
      const response = await fetch(apiPath('/api/systems'));
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

  function normalizeSystemId(name: string) {
    return name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
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
    const id = normalizeSystemId(name);
    if (!id) {
      systemError = 'System name must contain letters or numbers.';
      return;
    }
    
    try {
      const response = await fetch(apiPath('/api/systems'), {
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
      const response = await fetch(apiPath(`/api/systems/${encodeURIComponent(systemId)}`), {
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
        const error = await response.json().catch(() => null);
        const detail = typeof error?.detail === 'string' && error.detail.trim()
          ? error.detail
          : response.statusText || `Request failed (${response.status})`;
        systemError = detail;
      }
    } catch (error) {
      systemError = `Error deleting system: ${error}`;
    }
  }

  async function updateSystem(systemId: string, updates: Partial<EditableSystem> & { caseType?: EditableSystem['caseType'] | '' }) {
    try {
      const system = editableSystems.find((s) => s.id === systemId);
      if (!system) return;

      const response = await fetch(apiPath(`/api/systems/${encodeURIComponent(systemId)}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${adminToken}` },
        body: JSON.stringify({
          name: updates.name || system.name,
          shortName: updates.shortName || system.shortName,
          logo: updates.logo || system.logo,
          logoImageUrl: updates.logoImage || '',
          caseType: updates.caseType ? updates.caseType : 'auto',
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
      await fetch(apiPath('/api/systems/reorder'), {
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
      caseType: editingSystemCaseType || undefined,
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
        const response = await fetch(apiPath(endpoint), {
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
      musicFetchError = '';
      if (field === 'cover_image') {
        adminMessage = adminForm.category === 'Music' ? 'Custom album art loaded.' : 'Custom box art loaded.';
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
    libraryAdminTab = libraryView === 'wishlist' ? 'wishlists' : (category === 'Music' ? 'music' : 'games');
    wishlistAdminSection = stage === 'console' ? 'console' : category === 'Music' ? 'music' : 'games';
    adminSearchCategory = category === 'Music' ? 'Music' : 'Games';
    adminSearchPlatform = category === 'Games' ? (selectedConsole ?? 'All') : 'All';
    adminListPage = 0;
    if (libraryAdminTab === 'wishlists' && wishlistAdminSection === 'console') {
      resetWishlistSystemForm();
      wishlistEditingId = 'new';
      return;
    }

    resetAdminForm(category === 'Music' ? 'Music' : 'Games');
    adminForm = {
      ...adminForm,
      platform: category === 'Music' ? '' : (selectedConsole ?? 'PlayStation 2'),
    };
    if (libraryAdminTab === 'wishlists') {
      wishlistEditingId = 'new';
    } else {
      adminEditingId = -1;
    }
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

  function openAdminMode(mode: 'systems' | 'library', tab?: AdminLibraryTab, contextItem?: MediaItem) {
    adminOpen = true;
    adminMode = mode;
    adminError = '';
    adminMessage = '';
    if (tab) {
      if (mode === 'library') {
        setLibraryAdminTab(tab);
      } else {
        libraryAdminTab = tab;
      }
    }

    if (mode === 'library' && contextItem) {
      if (tab === 'wishlists' && isWishlistMediaItem(contextItem)) {
        startEditWishlistMedia(contextItem);
      } else {
        startEditItem(contextItem);
      }
      return;
    }

    resetAdminForm(tab === 'music' ? 'Music' : 'Games');
  }

    function backToAdminHub() {
      adminMode = 'hub';
      adminContextItem = null;
      adminEditingId = null;
      adminError = '';
      adminMessage = '';
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
      starRating: item.star_rating ?? null,
    };
    adminPublisherChoice = '';
    adminGameGenreChoice = '';
    adminMusicGenreChoice = item.category === 'Music' ? item.genre : '';
    launchboxManualUrl = '';
    wishlistEditingId = null;
  }

  async function adminLogin() {
    adminBusy = true;
    adminError = '';
    adminMessage = '';
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(apiPath('/api/admin/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: adminPassword }),
        signal: controller.signal,
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
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        adminError = 'Admin login timed out. Please try again.';
      } else {
        adminError = 'Admin login failed.';
      }
    } finally {
      clearTimeout(timeoutId);
      adminBusy = false;
    }
  }

  async function adminLogout() {
    try {
      await fetch(apiPath('/api/admin/logout'), {
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
    if (libraryAdminTab === 'wishlists') {
      await saveWishlistItem();
      return;
    }

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
    if (isGames && !adminForm.platform.trim()) {
      adminError = 'Select a platform for the game.';
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
      cover_image: adminForm.cover_image ?? existingItem?.cover_image ?? null,
      spine_image: isGames ? adminForm.spine_image ?? existingItem?.spine_image ?? null : existingItem?.spine_image ?? null,
      disc_image: isGames ? adminForm.disc_image ?? existingItem?.disc_image ?? null : existingItem?.disc_image ?? null,
      tags: existingItem?.tags ?? null,
      notes: adminForm.notes.trim() || null,
      star_rating: adminForm.starRating,
    };

    try {
      const response = await fetch(apiPath(adminForm.id ? `/api/media/${adminForm.id}` : '/api/media'), {
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
      const savedItem = await response.json().catch(() => null);
      adminMessage = adminForm.id ? 'Item updated.' : 'Item added.';
      const wasDetailsEdit = detailsEditMode;
      const savedId = adminForm.id;
      resetAdminForm();
      detailsEditMode = false;
      if (savedItem && typeof savedItem === 'object') {
        upsertMediaItem(savedItem as MediaItem);
        if (wasDetailsEdit) {
          selectedItem = savedItem as MediaItem;
        }
      }
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
      const response = await fetch(apiPath(`/api/media/${item.id}`), {
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
    if (stage !== 'boot' || bootTextVisible) return;
    if (isBootMuteKey(event)) {
      event.preventDefault();
      toggleBootMute();
      return;
    }
    if (isBootSpaceKey(event)) {
      event.preventDefault();
      unlockBootAudio();
      skipBootIntro();
    }
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

    if (starDropdownOpen) {
      event.preventDefault();
      starDropdownOpen = false;
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

  onMount(() => {
    void (async () => {
    const savedToken = localStorage.getItem('ps2-admin-token');
    if (savedToken) {
      adminToken = savedToken;
    }
      darkModeEnabled = localStorage.getItem(DARK_MODE_KEY) === 'true';
      loadWishlistsFromStorage();
      loadLocalStarRatingOverrides();
      await loadSystemsFromAPI();

      await loadAllMedia();
      history.replaceState(currentHistoryState(), '');
      window.addEventListener('popstate', handlePopState);
      window.addEventListener('keydown', handleGlobalBootKeydown);
      window.addEventListener('keydown', handleGlobalEscapeKeydown);
      void queueBootStart();
    })();

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
      if (bootSkipTapTimeout) {
        clearTimeout(bootSkipTapTimeout);
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
    selectedWishlistItem = null;
    selectedWishlistConsole = null;
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
      bootSourceIndex = 0;
      bootVideoSource = BOOT_VIDEO_SOURCES[0] ?? BOOT_VIDEO_SRC;
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

<svelte:window bind:innerWidth={viewportWidth} />

{#if stage === 'boot'}
  <div
    class="boot-screen"
    role="button"
    tabindex="0"
    aria-label={isMobile ? 'Double tap to toggle boot audio' : 'Press M to toggle boot audio'}
    on:click={handleBootScreenClick}
    on:touchend={handleBootScreenTouchEnd}
    on:keydown={(event) => {
      if (event.key.toLowerCase() === 'm') {
        event.preventDefault();
        toggleBootMute();
        return;
      }
      if (event.code === 'Space' || event.key === ' ' || event.key === 'Spacebar') {
        event.preventDefault();
        skipBootIntro();
      }
    }}
  >
    <video
      bind:this={bootVideoRef}
      class="boot-video"
      src={bootVideoSource}
      autoplay
      preload={BOOT_VIDEO_PRELOAD}
      muted={bootMuted}
      playsinline
      on:loadedmetadata={() => {
        if (bootVideoRef) {
          bootVideoRef.setAttribute('webkit-playsinline', 'true');
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
            revealBootOptions();
          }
        } else {
          if (bootVideoRef.currentTime >= bootRevealAt) {
            revealBootOptions();
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
        revealBootOptions();
      }}
      on:error={() => {
        if (tryBootVideoFailover()) return;
        revealBootOptions({ markError: true, resetStarted: true });
      }}
    >
      <track kind="captions" srclang="en" label="English" src="/ps2-intro.en.vtt" />
    </video>

    <div class="boot-vignette"></div>
    {#if transitionOverlay}
      <div class="transition-overlay" class:to-black={transitionToBlack} style="opacity: {transitionOpacity};" aria-hidden="true"></div>
    {/if}

    {#if bootSoundIndicatorVisible}
      <div class="boot-sound-indicator" transition:fade={{ duration: 260 }}>{bootSoundIndicator}</div>
    {/if}

    {#if !bootTextVisible}
      <div class="boot-skip-hint" transition:fade={{ duration: 600 }}>
        <div>{bootSkipHintText}</div>
        <div class="boot-mute-hint">{bootMuteHintText}</div>
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
  <div
    class="ps2-screen"
    class:transitioning={isTransitioning}
    class:dark-mode={darkModeEnabled && (stage === 'console' || stage === 'library' || stage === 'details')}
  >
    <div class="screen-fog"></div>
    {#if transitionOverlay}
      <div class="transition-overlay" class:to-black={transitionToBlack} style="opacity: {transitionOpacity};" aria-hidden="true"></div>
    {/if}

    {#if stage === 'console'}
      <section class="console-screen">
        <div class="console-hud" class:hovering-console-header={hoveredConsole !== null}>
          <div class="library-hud-left console-header-shell">
            <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="site-brand-logo site-brand-logo--header" draggable="false" />
            <span class="wishlist-context-copy">{wishlistToggleContextLabel}</span>
            <button
              type="button"
              class="wishlist-toggle wishlist-toggle--library wishlist-toggle--library-header"
              class:is-active={libraryView === 'wishlist'}
              on:click={toggleWishlistView}
              aria-label={wishlistIconLabel()}
              transition:fade={{ duration: 320, easing: cubicOut }}
            >
              <span class="wishlist-toggle-toprow">
                <span class="wishlist-toggle-icon wishlist-toggle-icon--header" aria-hidden="true">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 6.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Z M9.75 7.25h6.5v1.5h-6.5Zm0 5h6.5v1.5h-6.5Zm0 5h5v1.5h-5Z" fill="currentColor"></path>
                    <path d="M18.15 4.7c-1.04 0-1.82.64-2.16 1.28-.34-.64-1.12-1.28-2.16-1.28-1.32 0-2.38 1.02-2.38 2.31 0 2.35 4.54 4.88 4.54 4.88s4.54-2.53 4.54-4.88c0-1.29-1.06-2.31-2.38-2.31Z" fill="currentColor"></path>
                  </svg>
                  <span class="wishlist-toggle-footer wishlist-toggle-footer--under-icon">WISH LIST</span>
                </span>
                <span class="wishlist-toggle-label">{wishlistToggleContextLabel}</span>
              </span>
            </button>
          </div>
          <div class="console-toolbar" transition:fade={{ duration: 320, easing: cubicOut }}>
            <button
              type="button"
              class="wishlist-toggle wishlist-toggle--library wishlist-toggle--library-toolbar filter-icon-label-host"
              data-hover-label="WISH LIST"
              class:is-active={libraryView === 'wishlist'}
              on:click={toggleWishlistView}
              aria-label={wishlistIconLabel()}
              transition:fade={{ duration: 320, easing: cubicOut }}
            >
              <span class="wishlist-toggle-toprow">
                <span class="wishlist-toggle-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 6.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Z M9.75 7.25h6.5v1.5h-6.5Zm0 5h6.5v1.5h-6.5Zm0 5h5v1.5h-5Z" fill="currentColor"></path>
                    <path d="M18.15 4.7c-1.04 0-1.82.64-2.16 1.28-.34-.64-1.12-1.28-2.16-1.28-1.32 0-2.38 1.02-2.38 2.31 0 2.35 4.54 4.88 4.54 4.88s4.54-2.53 4.54-4.88c0-1.29-1.06-2.31-2.38-2.31Z" fill="currentColor"></path>
                  </svg>
                </span>
                <span class="wishlist-toggle-label">{wishlistToggleContextLabel}</span>
              </span>
              <span class="wishlist-toggle-footer">WISH LIST</span>
            </button>
            <span class="toolbar-divider" aria-hidden="true">|</span>
            <button
              type="button"
              class="collection-total-icon filter-icon-label-host"
              data-hover-label={consoleOwnedGamesCostLabel}
              aria-label={consoleOwnedGamesCostLabel}
            >
              <span class="collection-total-icon-inner" aria-hidden="true">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12.04 3.2c2.57 0 4.48 1.1 5.6 2.88l-2.05 1.23c-.65-1.08-1.84-1.76-3.55-1.76-1.8 0-2.94.73-2.94 1.9 0 1.04.93 1.62 2.85 1.97l1.51.27c3.11.56 4.9 1.9 4.9 4.49 0 2.97-2.46 4.88-6.2 5.07v1.65h-2.17v-1.7c-2.76-.28-4.87-1.51-6.01-3.43l2.1-1.31c.7 1.29 2.16 2.29 4.17 2.29 2.1 0 3.44-.83 3.44-2.16 0-1.09-.88-1.75-2.82-2.11l-1.5-.27c-3.02-.55-4.93-1.9-4.93-4.39 0-2.72 2.15-4.58 5.55-4.87V3.2h2.17v1.43Z" fill="currentColor"></path>
                </svg>
              </span>
            </button>
            <span class="toolbar-divider" aria-hidden="true">|</span>
            <button
              type="button"
              class="dark-mode-toggle filter-icon-label-host"
              data-hover-label="DARK MODE"
              class:is-active={darkModeEnabled}
              on:click={toggleDarkMode}
              aria-label={darkModeToggleLabel()}
              transition:fade={{ duration: 320, easing: cubicOut }}
            >
              <span class="dark-mode-toggle-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 3.4a.8.8 0 0 1 .8.8v1.65a.8.8 0 1 1-1.6 0V4.2a.8.8 0 0 1 .8-.8Zm0 14.75a.8.8 0 0 1 .8.8v1.65a.8.8 0 1 1-1.6 0V18.95a.8.8 0 0 1 .8-.8ZM5.82 6.95a.8.8 0 0 1 1.13 0l1.17 1.17a.8.8 0 1 1-1.13 1.13L5.82 8.08a.8.8 0 0 1 0-1.13Zm10.06 10.06a.8.8 0 0 1 1.13 0l1.17 1.17a.8.8 0 0 1-1.13 1.13l-1.17-1.17a.8.8 0 0 1 0-1.13ZM3.4 12a.8.8 0 0 1 .8-.8h1.65a.8.8 0 1 1 0 1.6H4.2a.8.8 0 0 1-.8-.8Zm14.75 0a.8.8 0 0 1 .8-.8h1.65a.8.8 0 1 1 0 1.6h-1.65a.8.8 0 0 1-.8-.8ZM6.95 18.18a.8.8 0 0 1 0-1.13l1.17-1.17a.8.8 0 0 1 1.13 1.13l-1.17 1.17a.8.8 0 0 1-1.13 0Zm10.06-10.06a.8.8 0 0 1 0-1.13l1.17-1.17a.8.8 0 1 1 1.13 1.13l-1.17 1.17a.8.8 0 0 1-1.13 0Z" fill="currentColor"></path>
                  <path d="M12 7.05a4.95 4.95 0 1 0 0 9.9 4.95 4.95 0 0 0 0-9.9Zm0 1.6a3.35 3.35 0 0 1 0 6.7 3.35 3.35 0 0 1 0-6.7Z" fill="currentColor"></path>
                </svg>
              </span>
            </button>
          </div>
          {#if consoleHeaderIdleVisible}
            <span
              class="console-header-inline-count console-header-copy console-header-count-copy library-header-subcopy"
              class:console-header-inline-count--visible={consoleHeaderIdleVisible}
            >
              {consoleCountCopy}
            </span>
          {/if}
          <div
            class="library-hud-right console-header-right console-header-right--console"
            class:console-header-right--active={consoleHeaderHoverVisible}
          >
            <div class="console-header-swap">
              <div class="console-header-state console-header-state--idle" class:console-header-state--visible={consoleHeaderIdleVisible}>
                <span class="console-header-copy console-header-count-copy library-header-subcopy">{consoleCountCopy}</span>
              </div>
              <div class="console-header-state console-header-state--hover" class:console-header-state--visible={consoleHeaderHoverVisible}>
                {#if consoleHeaderOption?.logoImage}
                  <img
                    src={consoleHeaderOption.logoImage}
                    alt={consoleHeaderOption.name}
                    class="console-header-logo"
                    draggable="false"
                  />
                {/if}
                <span class="console-header-copy console-header-count-copy library-header-subcopy">{hoveredConsoleCountLabel}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="console-grid">
          {#each consolePageItems as console, index}
            <button
              type="button"
              class="console-card"
              class:launching={launchConsoleName === console.name}
              style="--delay: {consoleDelay(index)}ms;"
              on:pointerenter={(event) => handleConsolePointerEnter(event, console.name)}
              on:mousemove={handleIconMove}
              on:pointerleave={handleConsolePointerLeave}
              on:click={() => libraryView === 'wishlist' ? openWishlistConsoleDetails(console as WishlistSystemItem) : onConsoleSelect(console.name)}
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

        {#if consoleTotalPages > 1}
          <div class="pager">
            <button type="button" on:click={() => setPage(page - 1)} disabled={page === 0} aria-label="Previous page">←</button>
            <div class="pager-info">{page + 1} / {consoleTotalPages}</div>
            <button type="button" on:click={() => setPage(page + 1)} disabled={page >= consoleTotalPages - 1} aria-label="Next page">→</button>
          </div>
        {/if}
      </section>
    {/if}

    {#if stage === 'library' || stage === 'details'}
      <section class="library-screen">
        <div class="library-hud">
          <div class="library-hud-left">
            <img src={SITE_LOGO_SRC} alt="The Avenoir Collection" class="site-brand-logo site-brand-logo--header" draggable="false" />
            {#if stage !== 'console'}
              <span class="wishlist-context-copy">{wishlistToggleContextLabel}</span>
            {/if}
            {#if stage !== 'console'}
              <button
                type="button"
                class="wishlist-toggle wishlist-toggle--library wishlist-toggle--library-header"
                class:is-active={libraryView === 'wishlist'}
                on:click={toggleWishlistView}
                aria-label={wishlistIconLabel()}
                transition:fade={{ duration: 320, easing: cubicOut }}
              >
                <span class="wishlist-toggle-toprow">
                  <span class="wishlist-toggle-icon wishlist-toggle-icon--header" aria-hidden="true">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M6 6.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Z M9.75 7.25h6.5v1.5h-6.5Zm0 5h6.5v1.5h-6.5Zm0 5h5v1.5h-5Z" fill="currentColor"></path>
                      <path d="M18.15 4.7c-1.04 0-1.82.64-2.16 1.28-.34-.64-1.12-1.28-2.16-1.28-1.32 0-2.38 1.02-2.38 2.31 0 2.35 4.54 4.88 4.54 4.88s4.54-2.53 4.54-4.88c0-1.29-1.06-2.31-2.38-2.31Z" fill="currentColor"></path>
                    </svg>
                    <span class="wishlist-toggle-footer wishlist-toggle-footer--under-icon">WISH LIST</span>
                  </span>
                  <span class="wishlist-toggle-label">{wishlistToggleContextLabel}</span>
                </span>
              </button>
            {/if}
          </div>

          {#if stage !== 'console'}
            <div class="library-toolbar" class:library-toolbar--music={category === 'Music'} transition:fade={{ duration: 320, easing: cubicOut }}>
              <button
                type="button"
                class="wishlist-toggle wishlist-toggle--library wishlist-toggle--library-toolbar filter-icon-label-host"
                data-hover-label="WISH LIST"
                class:is-active={libraryView === 'wishlist'}
                on:click={toggleWishlistView}
                aria-label={wishlistIconLabel()}
                transition:fade={{ duration: 320, easing: cubicOut }}
              >
                <span class="wishlist-toggle-toprow">
                  <span class="wishlist-toggle-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M6 6.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm0 4.75a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Z M9.75 7.25h6.5v1.5h-6.5Zm0 5h6.5v1.5h-6.5Zm0 5h5v1.5h-5Z" fill="currentColor"></path>
                      <path d="M18.15 4.7c-1.04 0-1.82.64-2.16 1.28-.34-.64-1.12-1.28-2.16-1.28-1.32 0-2.38 1.02-2.38 2.31 0 2.35 4.54 4.88 4.54 4.88s4.54-2.53 4.54-4.88c0-1.29-1.06-2.31-2.38-2.31Z" fill="currentColor"></path>
                    </svg>
                  </span>
                  <span class="wishlist-toggle-label">{wishlistToggleContextLabel}</span>
                </span>
                <span class="wishlist-toggle-footer">WISH LIST</span>
              </button>
              <span class="toolbar-divider toolbar-divider--wishlist" aria-hidden="true">|</span>
              {#if category === 'Games'}
                <div class="players-filter">
                  <button
                    type="button"
                    class="players-filter-btn filter-icon-label-host"
                    data-hover-label="PLAYERS"
                    class:is-active={libraryPlayersFilter !== null}
                    on:click={() => { playersDropdownOpen = !playersDropdownOpen; starDropdownOpen = false; }}
                    aria-label="Filter by player count"
                  >
                    <span class="players-filter-inner">
                      <img src="/controller-icon.svg" alt="" class="controller-icon" aria-hidden="true" />
                      {#if libraryPlayersFilter !== null}
                        <span class="players-filter-num">{libraryPlayersFilter}+</span>
                      {/if}
                      <span class="players-filter-caret">▾</span>
                    </span>
                  </button>
                  {#if playersDropdownOpen}
                    <button class="players-dropdown-backdrop" type="button" tabindex="-1" on:click={() => (playersDropdownOpen = false)} aria-label="Close player filter"></button>
                    <div class="players-dropdown" role="menu">
                      <button
                        type="button"
                        class:selected={libraryPlayersFilter === null}
                        on:click={() => { libraryPlayersFilter = null; playersDropdownOpen = false; page = 0; }}
                        role="menuitem"
                      >All</button>
                      {#each availablePlayerCounts as count}
                        <button
                          type="button"
                          class:selected={libraryPlayersFilter === count}
                          on:click={() => { libraryPlayersFilter = count; playersDropdownOpen = false; page = 0; }}
                          role="menuitem"
                        >{count}+ players</button>
                      {/each}
                    </div>
                  {/if}
                </div>
                <span class="toolbar-divider" aria-hidden="true">|</span>
              {/if}
              <div class="star-filter">
                <button
                  type="button"
                  class="star-filter-btn filter-icon-label-host"
                  data-hover-label="STAR RATING"
                  class:is-active={libraryStarFilter !== null}
                  on:click={() => { starDropdownOpen = !starDropdownOpen; playersDropdownOpen = false; }}
                  aria-label="Filter by star rating"
                >
                  <span class="star-filter-inner">
                    {#if libraryStarFilter !== null}
                      <span class="star-filter-num">{libraryStarFilter}+</span>
                    {/if}
                    <span class="star-filter-icon">★</span>
                    <span class="players-filter-caret">▾</span>
                  </span>
                </button>
                {#if starDropdownOpen}
                  <button class="players-dropdown-backdrop" type="button" tabindex="-1" on:click={() => (starDropdownOpen = false)} aria-label="Close star filter"></button>
                  <div class="players-dropdown star-dropdown" role="menu">
                    <button
                      type="button"
                      class:selected={libraryStarFilter === null}
                      on:click={() => { libraryStarFilter = null; starDropdownOpen = false; page = 0; }}
                      role="menuitem"
                    >All Ratings</button>
                    {#each [1, 2, 3, 4, 5] as n}
                      <button
                        type="button"
                        class:selected={libraryStarFilter === n}
                        on:click={() => { libraryStarFilter = n; starDropdownOpen = false; page = 0; }}
                        role="menuitem"
                      >{n}★+</button>
                    {/each}
                  </div>
                {/if}
              </div>
              <span class="toolbar-divider" aria-hidden="true">|</span>
              <div class="library-search-shell" class:is-open={librarySearchOpen}>
                <button
                  type="button"
                  class="library-search-toggle filter-icon-label-host"
                  data-hover-label="SEARCH"
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
                      starDropdownOpen = false;
                    }
                  }}
                  autocomplete="off"
                  spellcheck="false"
                />
              </div>
              <span class="toolbar-divider" aria-hidden="true">|</span>
              <button
                type="button"
                class="collection-total-icon filter-icon-label-host"
                data-hover-label={libraryCostLabel}
                aria-label={libraryCostLabel}
              >
                <span class="collection-total-icon-inner" aria-hidden="true">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12.04 3.2c2.57 0 4.48 1.1 5.6 2.88l-2.05 1.23c-.65-1.08-1.84-1.76-3.55-1.76-1.8 0-2.94.73-2.94 1.9 0 1.04.93 1.62 2.85 1.97l1.51.27c3.11.56 4.9 1.9 4.9 4.49 0 2.97-2.46 4.88-6.2 5.07v1.65h-2.17v-1.7c-2.76-.28-4.87-1.51-6.01-3.43l2.1-1.31c.7 1.29 2.16 2.29 4.17 2.29 2.1 0 3.44-.83 3.44-2.16 0-1.09-.88-1.75-2.82-2.11l-1.5-.27c-3.02-.55-4.93-1.9-4.93-4.39 0-2.72 2.15-4.58 5.55-4.87V3.2h2.17v1.43Z" fill="currentColor"></path>
                  </svg>
                </span>
              </button>
              <span class="toolbar-divider" aria-hidden="true">|</span>
              <button
                type="button"
                class="dark-mode-toggle filter-icon-label-host"
                data-hover-label="DARK MODE"
                class:is-active={darkModeEnabled}
                on:click={toggleDarkMode}
                aria-label={darkModeToggleLabel()}
              >
                <span class="dark-mode-toggle-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 3.4a.8.8 0 0 1 .8.8v1.65a.8.8 0 1 1-1.6 0V4.2a.8.8 0 0 1 .8-.8Zm0 14.75a.8.8 0 0 1 .8.8v1.65a.8.8 0 1 1-1.6 0V18.95a.8.8 0 0 1 .8-.8ZM5.82 6.95a.8.8 0 0 1 1.13 0l1.17 1.17a.8.8 0 1 1-1.13 1.13L5.82 8.08a.8.8 0 0 1 0-1.13Zm10.06 10.06a.8.8 0 0 1 1.13 0l1.17 1.17a.8.8 0 0 1-1.13 1.13l-1.17-1.17a.8.8 0 0 1 0-1.13ZM3.4 12a.8.8 0 0 1 .8-.8h1.65a.8.8 0 1 1 0 1.6H4.2a.8.8 0 0 1-.8-.8Zm14.75 0a.8.8 0 0 1 .8-.8h1.65a.8.8 0 1 1 0 1.6h-1.65a.8.8 0 0 1-.8-.8ZM6.95 18.18a.8.8 0 0 1 0-1.13l1.17-1.17a.8.8 0 0 1 1.13 1.13l-1.17 1.17a.8.8 0 0 1-1.13 0Zm10.06-10.06a.8.8 0 0 1 0-1.13l1.17-1.17a.8.8 0 1 1 1.13 1.13l-1.17 1.17a.8.8 0 0 1-1.13 0Z" fill="currentColor"></path>
                    <path d="M12 7.05a4.95 4.95 0 1 0 0 9.9 4.95 4.95 0 0 0 0-9.9Zm0 1.6a3.35 3.35 0 0 1 0 6.7 3.35 3.35 0 0 1 0-6.7Z" fill="currentColor"></path>
                  </svg>
                </span>
              </button>
            </div>
          {/if}

          {#if stage !== 'console' && category === 'Games' && selectedLibraryConsole?.logoImage}
            <div class="library-hud-right console-header-right">
              <div class="console-hover-meta">
                <img src={selectedLibraryConsole.logoImage} alt={selectedLibraryConsole.name} class="console-header-logo" draggable="false" />
                {#key `${selectedLibraryConsole.name}-${libraryCountCopy}`}
                  <span class="console-header-copy console-header-count-copy library-header-subcopy">{libraryCountCopy}</span>
                {/key}
              </div>
            </div>
          {:else if libraryHeaderRight}
            <div class="library-hud-right console-header-right console-header-right--text-only">
              <span class="console-header-copy console-header-count-copy library-header-subcopy">{libraryCountCopy}</span>
            </div>
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
                <p class="library-empty-text">{libraryView === 'wishlist' ? 'No games on this wish list yet...' : 'No games found on memory card...'}</p>
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
            <button type="button" on:click={() => setPage(page - 1)} disabled={page === 0} aria-label="Previous page">←</button>
            <div class="pager-info">{page + 1} / {filteredTotalPages}</div>
            <button type="button" on:click={() => setPage(page + 1)} disabled={page >= filteredTotalPages - 1} aria-label="Next page">→</button>
          </div>
        {/if}
      </section>
    {/if}

    {#if stage === 'details' && detailItem}
      <button
        type="button"
        class="details-overlay"
        aria-label="Close details"
        on:click={closeDetails}
        transition:popupOverlayTransition
      ></button>
      <section class="details-screen" class:dark-mode={darkModeEnabled} transition:popupPanelTransition>
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
              {#if detailItem.category === 'Games'}
                {#if isCartridgePlatform(detailItem.platform)}
                  <div class="details-cart-flipper">
                    <div class="details-disc-flip-face details-disc-flip-face--front">
                      <div class={`details-cartridge ${discBackingClass(detailItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if detailItem.disc_image && !brokenDiscIds.has(detailItem.id)}
                          <img src={detailItem.disc_image} alt={detailItem.title} class="details-cartridge-art" draggable="false" on:error={() => markDiscBroken(detailItem.id)} />
                        {:else if detailItem.cover_image && !brokenCoverIds.has(detailItem.id)}
                          <img src={detailItem.cover_image} alt={detailItem.title} class="details-cartridge-art" draggable="false" on:error={() => markCoverBroken(detailItem.id)} />
                        {:else}
                          <div class="details-cartridge-fallback">{iconInitials(detailItem.title)}</div>
                        {/if}
                      </div>
                    </div>
                    <div class="details-disc-flip-face details-disc-flip-face--back" aria-hidden="true">
                      <div class={`details-cartridge details-cartridge--back ${discBackingClass(detailItem)}`}>
                        <span class="disc-shell-backing"></span>
                        <span class="details-cartridge-back-panel"></span>
                        <span class="details-cartridge-contacts"></span>
                      </div>
                    </div>
                  </div>
                {:else}
                  <div class="details-disc-flipper">
                    <div class="details-disc-flip-face details-disc-flip-face--front">
                      <div class={`details-game-disc ${discBackingClass(detailItem)}`}>
                        <span class="disc-shell-backing"></span>
                        {#if detailItem.disc_image && !brokenDiscIds.has(detailItem.id)}
                          <img src={detailItem.disc_image} alt={detailItem.title} class="details-game-disc-art" draggable="false" on:error={() => markDiscBroken(detailItem.id)} />
                        {:else}
                          <div class="details-game-disc-fallback">{iconInitials(detailItem.title)}</div>
                        {/if}
                        <span class="disc-hole"></span>
                        <span class="details-game-disc-shine"></span>
                      </div>
                    </div>
                    <div class="details-disc-flip-face details-disc-flip-face--back" aria-hidden="true">
                      <div class={`details-game-disc ${discBackingClass(detailItem)}`}>
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
                    {#if detailItem.cover_image}
                      <img src={detailItem.cover_image} alt={detailItem.title} class="library-art" draggable="false" />
                    {:else}
                      <span class="library-fallback">{iconInitials(detailItem.title)}</span>
                    {/if}
                  </span>
                </span>
              {/if}
            </button>
          </div>
        </div>

        <div class="details-right">
          <p class="details-line-2">{detailItem.title}</p>
          <div class="details-tags" aria-label="Details tags">
            {#each detailTags(detailItem) as tag}
              <button
                type="button"
                class={`details-tag details-tag--${tag.tone}`}
                on:click={() => applyDetailTagFilter(tag.query)}
              >
                {tag.label}
              </button>
            {/each}
          </div>
          {#if detailItem.category === 'Games' || detailItem.category === 'Music'}
            <div class="details-star-ratings" aria-label="Star rating">
              <div class="details-star-row">
                <span class="details-star-label">MY RATING</span>
                {#if isAdmin}
                  <div class="details-star-picker" role="group" aria-label="Set star rating">
                    {#each [1, 2, 3, 4, 5] as n}
                      <button
                        type="button"
                        class="star-btn details-star-btn"
                        class:filled={detailEditedStarRating !== null && n <= detailEditedStarRating}
                        aria-label="{n} star{n !== 1 ? 's' : ''}"
                        on:click={() => setDetailStarRating(n)}
                      >★</button>
                    {/each}
                  </div>
                {:else}
                  <span class="details-stars details-stars--readonly" aria-label={detailEditedStarRating != null ? `${detailEditedStarRating} out of 5 stars` : 'No star rating assigned'}>
                    {starDisplay(detailEditedStarRating)}
                  </span>
                {/if}
                {#if detailRatingMessage}
                  <span class="details-rating-message">{detailRatingMessage}</span>
                {/if}
              </div>
            </div>
          {/if}
          <p class="details-line-5">{detailItem.notes?.trim() || 'No description available.'}</p>

          <section class="details-price" aria-label="Price details" class:details-price--expanded={detailPriceExpanded}>
            <div class="details-price-header">
              <div class="details-price-header-main">
                <h3 class="details-price-title">PRICE</h3>
                <div class="details-price-summary" aria-label="Price summary">
                  {#each detailPriceSummary as entry, index}
                    {#if index > 0}
                      <span class="details-price-summary-divider" aria-hidden="true"></span>
                    {/if}
                    <button type="button" class="details-price-summary-chip" on:click={() => openPriceSource(entry.url)} disabled={!entry.url}>
                      <span class="details-price-summary-label">{entry.label}</span>
                      <span class="details-price-summary-value price-color--{entry.colorClass}">{formatPrice(entry.value)}</span>
                    </button>
                  {/each}
                </div>
              </div>
              <button
                type="button"
                class="details-price-toggle"
                aria-expanded={detailPriceExpanded}
                aria-label={detailPriceExpanded ? 'Collapse price details' : 'Expand price details'}
                on:click={() => (detailPriceExpanded = !detailPriceExpanded)}
              ><span class="details-price-toggle-icon" class:is-expanded={detailPriceExpanded}>▼</span></button>
            </div>

            {#if detailPriceExpanded}
              <div class="details-price-body">
                <div class="details-price-row">
                  <div class="details-price-metric">
                    <p class="details-price-metric-label">AVERAGE</p>
                    {#if detailItem.category === 'Games'}
                      <div class="details-price-conditions details-price-conditions--game">
                        <button type="button" class="price-chip price-chip--loose" on:click={() => openPriceSource(detailPriceData.averageLoose.url)}>
                          <span class="price-chip-value">{formatPrice(detailPriceData.averageLoose.value)}</span>
                          <span class="price-chip-label">LOOSE</span>
                        </button>
                        <button type="button" class="price-chip price-chip--cib" on:click={() => openPriceSource(detailPriceData.averageCib.url)}>
                          <span class="price-chip-value">{formatPrice(detailPriceData.averageCib.value)}</span>
                          <span class="price-chip-label">CIB</span>
                        </button>
                        <button type="button" class="price-chip price-chip--new" on:click={() => openPriceSource(detailPriceData.averageNew.url)}>
                          <span class="price-chip-value">{formatPrice(detailPriceData.averageNew.value)}</span>
                          <span class="price-chip-label">NEW</span>
                        </button>
                      </div>
                    {:else}
                      <div class="details-price-conditions details-price-conditions--music">
                        <button type="button" class="price-chip price-chip--standard" on:click={() => openPriceSource(detailPriceData.averageStandard.url)}>
                          <span class="price-chip-value">{formatPrice(detailPriceData.averageStandard.value)}</span>
                          <span class="price-chip-label">STANDARD</span>
                        </button>
                        <button type="button" class="price-chip price-chip--limited" on:click={() => openPriceSource(detailPriceData.averageLimited.url)}>
                          <span class="price-chip-value">{formatPrice(detailPriceData.averageLimited.value)}</span>
                          <span class="price-chip-label">LIMITED ED.</span>
                        </button>
                      </div>
                    {/if}
                  </div>

                  <div class="details-price-divider" aria-hidden="true"></div>

                  <div class="details-price-metric">
                    <p class="details-price-metric-label">AVERAGE CHANGE</p>
                    <div class="details-price-change-list">
                      {#each detailPriceChangeEntries(detailItem, detailPriceData) as cEntry, ci}
                        {#if ci > 0}
                          <span class="details-price-change-divider" aria-hidden="true"></span>
                        {/if}
                        <div class="details-price-change-row">
                          <span class="details-price-change-row-label price-color--{cEntry.colorClass}">{cEntry.label}</span>
                          <span
                            class="details-price-change-row-value"
                            class:is-up={cEntry.percent !== null && cEntry.percent >= 0}
                            class:is-down={cEntry.percent !== null && cEntry.percent < 0}
                          >{cEntry.percent === null ? '—' : formatPercentChange(cEntry.percent)}</span>
                        </div>
                      {/each}
                    </div>
                  </div>

                  <div class="details-price-divider" aria-hidden="true"></div>

                  <div class="details-price-metric">
                    <p class="details-price-metric-label">SOLD RANGE</p>
                    {#if detailItem.category === 'Games'}
                      <div class="details-price-conditions details-price-conditions--game">
                        <div class="price-chip price-chip--loose">
                          <span class="price-chip-value">{soldRangeByConditionDisplay(detailPriceData, 'loose')}</span>
                          <span class="price-chip-label">LOOSE</span>
                        </div>
                        <div class="price-chip price-chip--cib">
                          <span class="price-chip-value">{soldRangeByConditionDisplay(detailPriceData, 'cib')}</span>
                          <span class="price-chip-label">CIB</span>
                        </div>
                        <div class="price-chip price-chip--new">
                          <span class="price-chip-value">{soldRangeByConditionDisplay(detailPriceData, 'new')}</span>
                          <span class="price-chip-label">NEW</span>
                        </div>
                      </div>
                    {:else if detailItem.category === 'Music'}
                      <div class="details-price-conditions details-price-conditions--music">
                        <div class="price-chip price-chip--standard">
                          <span class="price-chip-value">{soldRangeByConditionDisplay(detailPriceData, 'standard')}</span>
                          <span class="price-chip-label">STANDARD</span>
                        </div>
                        <div class="price-chip price-chip--limited">
                          <span class="price-chip-value">{soldRangeByConditionDisplay(detailPriceData, 'limited')}</span>
                          <span class="price-chip-label">LIMITED ED.</span>
                        </div>
                      </div>
                    {:else}
                      <p class="details-price-range">{soldRangeDisplay(detailPriceData.soldRangeMin, detailPriceData.soldRangeMax)}</p>
                    {/if}
                  </div>
                </div>

                {#if isAdmin && !detailIsWishlist}
                  <div class="details-price-admin">
                    <button
                      type="button"
                      class="details-price-fetch details-price-action"
                      on:click={fetchDetailPriceData}
                      disabled={detailPriceFetchBusy}
                    >{detailPriceFetchBusy ? 'Fetching...' : 'Fetch Price Data'}</button>
                    <p class="details-price-last-fetch">LAST PRICE DATA FETCH: {formatFetchDate(detailItem.price_last_fetched_at)}</p>
                  </div>
                {/if}

                {#if detailPriceFetchStatus || detailPriceFetchError || detailPriceFetchBusy}
                  <div class="details-price-fetch-state" class:has-error={Boolean(detailPriceFetchError)} aria-live="polite">
                    <p class="details-price-fetch-state-text">{detailPriceFetchError || detailPriceFetchStatus}</p>
                    <div class="details-progress-track" aria-hidden="true">
                      <span class="details-progress-fill" style={`width: ${Math.max(0, Math.min(100, detailPriceFetchProgress))}%;`}></span>
                    </div>
                  </div>
                {/if}
              </div>
            {/if}
          </section>

          <div class="details-actions">
            <div class="details-actions-right">
              {#if detailRatingDirty}
                <button
                  type="button"
                  class="details-save-rating"
                  on:click={saveDetailRatingChanges}
                  disabled={detailRatingSaving}
                  transition:fade={{ duration: 240 }}
                >{detailRatingSaving ? 'Saving...' : 'Save Changes'}</button>
              {/if}
              {#if isAdmin}
                <div class="details-admin-actions">
                  {#if detailIsWishlist && selectedWishlistItem}
                    <button type="button" on:click={() => selectedWishlistItem && addWishlistMediaToLibrary(selectedWishlistItem)}>Add to Library</button>
                    <button type="button" on:click={() => selectedWishlistItem && startEditWishlistMedia(selectedWishlistItem)}>Edit</button>
                    <button type="button" class="danger" on:click={() => selectedWishlistItem && deleteWishlistSelection(selectedWishlistItem.wishlistKind, selectedWishlistItem.wishlistId)}>Delete</button>
                  {:else}
                    <button type="button" on:click={() => openEditConfirm(detailItem, true)}>Edit</button>
                    <button type="button" class="danger" on:click={() => openDeleteConfirm(detailItem)}>Delete</button>
                  {/if}
                </div>
              {/if}
            </div>
          </div>
        </div>
      </section>
    {/if}

    {#if stage === 'console' && selectedWishlistConsole}
      <button
        type="button"
        class="details-overlay"
        aria-label="Close console details"
        on:click={closeWishlistConsoleDetails}
        transition:popupOverlayTransition
      ></button>
      <section class="details-screen details-screen--console-wishlist" class:dark-mode={darkModeEnabled} transition:popupPanelTransition>
        <button type="button" class="popup-close details-close" aria-label="Close console details" on:click={closeWishlistConsoleDetails}>×</button>
        <div class="details-left details-left--console-wishlist">
          <div class="systems-logo-container systems-logo-container--detail">
            {#if selectedWishlistConsole.logoImage}
              <img src={selectedWishlistConsole.logoImage} alt={selectedWishlistConsole.name} class="systems-logo" draggable="false" />
            {:else}
              <span class="systems-fallback">{selectedWishlistConsole.shortName}</span>
            {/if}
          </div>
        </div>
        <div class="details-right">
          <p class="details-line-2">{selectedWishlistConsole.name}</p>
          <p class="details-line-5">{selectedWishlistConsole.caseType ? `${selectedWishlistConsole.caseType[0].toUpperCase()}${selectedWishlistConsole.caseType.slice(1)} system` : 'Wish list console'}</p>
          <div class="details-actions">
            {#if isAdmin}
              <div class="details-admin-actions">
                <button type="button" on:click={() => selectedWishlistConsole && addWishlistConsoleToLibrary(selectedWishlistConsole)}>Add to Library</button>
                <button type="button" on:click={() => selectedWishlistConsole && startEditWishlistConsole(selectedWishlistConsole)}>Edit</button>
                <button type="button" class="danger" on:click={() => selectedWishlistConsole && deleteWishlistSelection('console', selectedWishlistConsole.wishlistId)}>Delete</button>
              </div>
            {/if}
          </div>
        </div>
      </section>
    {/if}

    {#if launchboxArtPickerOpen}
      <div class="launchbox-art-picker-overlay" role="dialog" aria-modal="true" aria-labelledby="launchbox-art-picker-title" transition:popupOverlayTransition>
        <button type="button" class="launchbox-art-picker-backdrop" aria-label="Close art selector" on:click={closeLaunchboxArtPicker}></button>
        <div class="launchbox-art-picker-panel" transition:popupPanelTransition>
          <button type="button" class="popup-close" aria-label="Close art selector" on:click={closeLaunchboxArtPicker}>×</button>
          <div class="launchbox-art-picker-header">
            <h3 id="launchbox-art-picker-title">Choose {adminArtPickerLabel(launchboxArtPickerField ?? 'cover_image')}</h3>
          </div>
          {#if launchboxArtPickerBusy}
            <p class="launchbox-art-picker-state">Loading art options from available sources...</p>
          {:else if launchboxArtPickerError}
            <p class="admin-error launchbox-art-picker-state">{launchboxArtPickerError}</p>
          {:else if launchboxArtPickerSource === 'music' && (launchboxArtOptionsBySource.discogs.length || launchboxArtOptionsBySource.deezer.length)}
            {#if launchboxArtPickerStatus}
              <p class="launchbox-art-picker-state">{launchboxArtPickerStatus}</p>
            {/if}

            {#if launchboxArtOptionsBySource.discogs.length}
              <section class="launchbox-art-picker-source-section" aria-label="Discogs results">
                <h4 class="launchbox-art-picker-source-title">Discogs</h4>
                <div class="launchbox-art-picker-grid">
                  {#each launchboxArtOptionsBySource.discogs as artOption, index}
                    <button
                      type="button"
                      class="launchbox-art-picker-option"
                      on:click={() => chooseLaunchboxArtOption(artOption)}
                      aria-label={`Select Discogs ${adminArtPickerLabel(launchboxArtPickerField ?? 'cover_image')} option ${index + 1}`}
                    >
                      <img src={artOption} alt={`Discogs art option ${index + 1}`} loading="lazy" />
                    </button>
                  {/each}
                </div>
              </section>
            {/if}

            {#if launchboxArtOptionsBySource.deezer.length}
              <section class="launchbox-art-picker-source-section" aria-label="Deezer results">
                <h4 class="launchbox-art-picker-source-title">Deezer</h4>
                <div class="launchbox-art-picker-grid">
                  {#each launchboxArtOptionsBySource.deezer as artOption, index}
                    <button
                      type="button"
                      class="launchbox-art-picker-option"
                      on:click={() => chooseLaunchboxArtOption(artOption)}
                      aria-label={`Select Deezer ${adminArtPickerLabel(launchboxArtPickerField ?? 'cover_image')} option ${index + 1}`}
                    >
                      <img src={artOption} alt={`Deezer art option ${index + 1}`} loading="lazy" />
                    </button>
                  {/each}
                </div>
              </section>
            {/if}
          {:else if launchboxArtOptions.length}
            {#if launchboxArtPickerStatus}
              <p class="launchbox-art-picker-state">{launchboxArtPickerStatus}</p>
            {/if}
            <div class="launchbox-art-picker-grid">
              {#each launchboxArtOptions as artOption, index}
                <button
                  type="button"
                  class="launchbox-art-picker-option"
                  on:click={() => chooseLaunchboxArtOption(artOption)}
                  aria-label={`Select ${adminArtPickerLabel(launchboxArtPickerField ?? 'cover_image')} option ${index + 1}`}
                >
                  <img src={artOption} alt={`Art option ${index + 1}`} loading="lazy" />
                </button>
              {/each}
            </div>
          {:else}
            <p class="launchbox-art-picker-state">No options available.</p>
          {/if}
        </div>
      </div>
    {/if}

    {#if confirmOpen && (confirmItem || confirmSystem)}
      <div class="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title" transition:popupOverlayTransition>
        <button type="button" class="confirm-backdrop" aria-label="Close confirmation" on:click={closeConfirm}></button>
        <div class="confirm-panel" transition:popupPanelTransition>
          <button type="button" class="popup-close" aria-label="Close confirmation" on:click={closeConfirm}>×</button>
          <h3 id="confirm-title">{confirmMode === 'delete-system' ? 'Delete System?' : confirmMode === 'delete' ? 'Delete Item?' : 'Edit Item?'}</h3>
          <p>
            {#if confirmMode === 'delete-system'}
              Delete "{confirmSystem?.name}" from the system manager? This cannot be undone.
            {:else if confirmMode === 'delete'}
              Delete "{confirmItem.title}" from the library? This cannot be undone.
            {:else}
              Open "{confirmItem.title}" in the editor?
            {/if}
          </p>
          <div class="confirm-actions">
            <button type="button" class="ghost" on:click={closeConfirm}>Cancel</button>
            <button type="button" class:danger={confirmMode !== 'edit'} on:click={confirmAction}>
              {confirmMode === 'edit' ? 'Edit' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    {/if}

    {#if stage !== 'details'}
      <button type="button" class="back-button" on:click={backAction} transition:fade={{ duration: 240, easing: cubicOut }}>Back</button>
    {/if}

    <button type="button" class="admin-launch" on:click={toggleAdminPanel}>{adminOpen ? 'Close' : 'Admin'}</button>

    {#if isAdmin}
      <div class="admin-toolbar">
        {#if stage === 'console'}
          <button type="button" on:click={() => openAdminMode('systems')} transition:fade={{ duration: 320, easing: cubicOut }}>Manage Systems</button>
        {/if}
        {#if stage === 'library'}
          <button type="button" on:click={startAddItem} transition:fade={{ duration: 320, easing: cubicOut }}>Add {category === 'Music' ? 'Album' : 'Game'}</button>
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
          <button type="button" disabled={adminBusy} on:click={adminLogin}>{adminBusy ? 'Logging In...' : 'Log In'}</button>
          {#if adminError}
            <p class="admin-error">{adminError}</p>
          {/if}
          {#if adminMessage}
            <p class="admin-status">{adminMessage}</p>
          {/if}
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
            <button
              type="button"
              class="admin-hub-card"
              on:click={() => {
                wishlistAdminSection = 'console';
                adminListPage = 0;
                resetWishlistSystemForm();
                openAdminMode('library', 'wishlists');
              }}
            >
              <h3>Wish List Manager</h3>
              <p>Manage console, game, and music wish lists</p>
            </button>
            <button type="button" class="admin-hub-card" on:click={openFetchToolsPopup}>
              <h3>Fetch Tools</h3>
              <p>Run art/details fetch jobs for libraries and wish lists with progress and error tracking.</p>
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
                      <button type="button" class="danger" on:click={() => openDeleteSystemConfirm(system)}>Remove</button>
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
              on:click={() => setLibraryAdminTab('games')}
            >
              Games
            </button>
            <button 
              type="button" 
              class:active={libraryAdminTab === 'music'}
              on:click={() => setLibraryAdminTab('music')}
            >
              Music
            </button>
            <button
              type="button"
              class:active={libraryAdminTab === 'wishlists'}
              on:click={() => {
                libraryAdminTab = 'wishlists';
                setWishlistAdminSection('console');
              }}
            >
              Wish Lists
            </button>
          </div>

          {#if libraryAdminTab === 'wishlists'}
            <div class="admin-tabs admin-subtabs">
              <button type="button" class:active={wishlistAdminSection === 'console'} on:click={() => setWishlistAdminSection('console')}>Consoles</button>
              <button type="button" class:active={wishlistAdminSection === 'games'} on:click={() => setWishlistAdminSection('games')}>Games</button>
              <button type="button" class:active={wishlistAdminSection === 'music'} on:click={() => setWishlistAdminSection('music')}>Music</button>
            </div>
          {/if}

          <div class="admin-layout">
            <!-- Library List (Left) -->
            <div class="admin-list-pane">
              <div class="admin-list-filters">
                <input type="search" class="search-input-unified" bind:value={adminSearchQuery} placeholder={libraryAdminTab === 'wishlists' && wishlistAdminSection === 'console' ? 'Search by console...' : 'Search by title...'} />
                {#if libraryAdminTab === 'games' || (libraryAdminTab === 'wishlists' && wishlistAdminSection === 'games')}
                  <select bind:value={adminSearchPlatform} on:change={() => (adminListPage = 0)}>
                    <option value="All">All Platforms</option>
                    {#each adminConsoleOptions as platform}
                      <option value={platform}>{platform}</option>
                    {/each}
                  </select>
                {/if}
              </div>

              <div class="admin-list">
                {#if libraryAdminTab === 'wishlists'}
                  {#each activeAdminWishlistPageItems as item}
                    <div
                      class="admin-row"
                      class:active={wishlistEditingId === item.wishlistId}
                      role="button"
                      tabindex="0"
                      on:click={() => wishlistAdminSection === 'console' ? startEditWishlistConsole(item as WishlistSystemItem) : startEditWishlistMedia(item as WishlistMediaItem)}
                      on:keydown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          if (wishlistAdminSection === 'console') {
                            startEditWishlistConsole(item as WishlistSystemItem);
                          } else {
                            startEditWishlistMedia(item as WishlistMediaItem);
                          }
                        }
                      }}
                    >
                      {#if wishlistAdminSection === 'console' && (item as WishlistSystemItem).logoImage}
                        <img src={(item as WishlistSystemItem).logoImage ?? ''} alt="" class="admin-row-thumb" draggable="false" />
                      {:else if wishlistAdminSection !== 'console' && (item as WishlistMediaItem).cover_image}
                        <img src={(item as WishlistMediaItem).cover_image ?? ''} alt="" class="admin-row-thumb" draggable="false" />
                      {/if}
                      <div class="admin-row-content">
                        <strong>{wishlistAdminSection === 'console' ? (item as WishlistSystemItem).name : (item as WishlistMediaItem).title}</strong>
                        <small>
                          {#if wishlistAdminSection === 'console'}
                            {(item as WishlistSystemItem).shortName}
                          {:else}
                            {(item as WishlistMediaItem).platform ?? (item as WishlistMediaItem).artist ?? 'Unknown'}
                          {/if}
                        </small>
                      </div>
                      <div class="admin-row-actions">
                        <button type="button" on:click|stopPropagation={() => wishlistAdminSection === 'console' ? startEditWishlistConsole(item as WishlistSystemItem) : startEditWishlistMedia(item as WishlistMediaItem)}>Edit</button>
                        <button type="button" class="danger" on:click|stopPropagation={() => deleteWishlistSelection(wishlistAdminSection === 'console' ? 'console' : wishlistAdminSection, item.wishlistId)}>Delete</button>
                      </div>
                    </div>
                  {/each}
                {:else}
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
                {/if}
              </div>

              {#if adminActiveTotalPages > 1}
                <div class="admin-list-pager">
                  <button type="button" on:click={() => (adminListPage = Math.max(0, adminListPage - 1))} disabled={adminListPage === 0} aria-label="Previous page">←</button>
                  <div class="admin-pager-info">{adminListPage + 1} / {adminActiveTotalPages}</div>
                  <button type="button" on:click={() => (adminListPage = Math.min(adminActiveTotalPages - 1, adminListPage + 1))} disabled={adminListPage >= adminActiveTotalPages - 1} aria-label="Next page">→</button>
                </div>
              {/if}

              <!-- Bulk Upload -->
              <div class="bulk-upload-section">
                <button
                  type="button"
                  class="bulk-upload-toggle"
                  on:click={() => {
                    bulkOpen = !bulkOpen;
                      resetBulkUploadState();
                  }}
                >
                  {bulkOpen ? '▲ Hide Bulk Upload' : '▼ Bulk Upload'}
                </button>
                <div class="bulk-upload-body" class:open={bulkOpen}>
                  <p class="bulk-format-hint">
                      {bulkUploadHintText()}
                  </p>
                  <textarea
                    class="bulk-upload-textarea"
                    bind:value={bulkText}
                      placeholder={bulkUploadPlaceholder()}
                    rows="6"
                    disabled={bulkBusy}
                  ></textarea>
                  <button
                    type="button"
                    class="bulk-submit-button"
                    disabled={!bulkText.trim() || bulkBusy}
                    on:click={bulkUpload}
                  >
                      {bulkBusy ? 'Uploading...' : bulkUploadActionLabel()}
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

              <!-- Bulk Add Wishlist to Library -->
              {#if libraryAdminTab === 'wishlists' && (consoleWishlist.length > 0 || gameWishlist.length > 0 || musicWishlist.length > 0)}
                <div class="bulk-add-section">
                  <button
                    type="button"
                    class="bulk-add-toggle"
                    on:click={() => {
                      bulkAddWishlistBusy = false;
                      bulkAddWishlistResults = [];
                      bulkAddWishlistStatusText = '';
                    }}
                  >
                    {wishlistAdminSection === 'console'
                      ? `Add All Consoles (${consoleWishlist.length})`
                      : wishlistAdminSection === 'games'
                        ? `Add All Games (${gameWishlist.length})`
                        : `Add All Albums (${musicWishlist.length})`}
                  </button>
                  <div class="bulk-add-body">
                    <p class="bulk-add-description">
                      {wishlistAdminSection === 'console'
                        ? `Add all ${consoleWishlist.length} console${consoleWishlist.length !== 1 ? 's' : ''} from your wish list to the library.`
                        : wishlistAdminSection === 'games'
                          ? `Add all ${gameWishlist.length} game${gameWishlist.length !== 1 ? 's' : ''} from your wish list to the library.`
                          : `Add all ${musicWishlist.length} album${musicWishlist.length !== 1 ? 's' : ''} from your wish list to the library.`}
                    </p>
                    <button
                      type="button"
                      class="bulk-add-button"
                      disabled={bulkAddWishlistBusy}
                      on:click={bulkAddWishlistToLibrary}
                    >
                      {bulkAddWishlistBusy ? 'Adding...' : 'Add to Library'}
                    </button>
                    {#if bulkAddWishlistStatusText}
                      <div class="bulk-add-status" role="status" aria-live="polite">
                        <p class="bulk-add-status-text">{bulkAddWishlistStatusText}</p>
                        {#if bulkAddWishlistResults.length}
                          <div class="bulk-result-list">
                            {#each bulkAddWishlistResults as result}
                              <div class="bulk-result-item" class:bulk-success={result.status === 'success'} class:bulk-error={result.status === 'error'}>
                                <span class="bulk-result-line">{result.title}</span>
                                <span class="bulk-result-msg">{result.message}</span>
                              </div>
                            {/each}
                          </div>
                        {/if}
                      </div>
                    {/if}
                  </div>
                </div>
              {/if}
            </div>

            <!-- Library Editor (Right) -->
            <div class="admin-form-pane">
              {#if libraryAdminTab === 'wishlists' && wishlistAdminSection === 'console' && wishlistEditingId !== null}
                <form class="admin-form" on:submit|preventDefault={saveWishlistItem} novalidate>
                  <h3>{wishlistSystemForm.name || 'Edit Console Wish List Item'}</h3>
                  <div class="form-field">
                    <label for="wishlist-console-name">System Name</label>
                    <input id="wishlist-console-name" type="text" bind:value={wishlistSystemForm.name} placeholder="System name" required />
                  </div>
                  <div class="form-field">
                    <label for="wishlist-console-short-name">Short Name</label>
                    <input id="wishlist-console-short-name" type="text" bind:value={wishlistSystemForm.shortName} placeholder="PS5" />
                  </div>
                  <div class="form-field">
                    <label for="wishlist-console-logo">Logo Text</label>
                    <input id="wishlist-console-logo" type="text" bind:value={wishlistSystemForm.logo} placeholder="PS5" />
                  </div>
                  <div class="form-field">
                    <label for="wishlist-console-case">Case Type</label>
                    <select id="wishlist-console-case" bind:value={wishlistSystemForm.caseType}>
                      <option value="">Auto-detect</option>
                      <option value="cartridge">Cartridge</option>
                      <option value="disc">Disc</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                  </div>
                  <div class="form-field">
                    <label for="wishlist-console-logo-image">Logo Image URL</label>
                    <input id="wishlist-console-logo-image" type="text" bind:value={wishlistSystemForm.logoImage} placeholder="https://..." />
                  </div>
                  <div class="form-actions">
                    <button type="submit">Save Wish List Item</button>
                    <button type="button" on:click={resetWishlistSystemForm}>Clear</button>
                  </div>
                  {#if adminError}
                    <p class="admin-error">{adminError}</p>
                  {/if}
                  {#if adminMessage}
                    <p class="admin-status">{adminMessage}</p>
                  {/if}
                </form>
              {:else if libraryAdminTab === 'wishlists' && wishlistAdminSection !== 'console' && wishlistEditingId !== null}
                <form class="admin-form" on:submit|preventDefault={saveWishlistItem} novalidate>
                  <h3>{adminForm.title || 'Edit Wish List Item'}</h3>
                  {#if wishlistAdminSection === 'games'}
                    <section class="admin-loaded-art" aria-label="Loaded Art">
                      <p class="admin-loaded-art-title">Loaded Art</p>
                      <div class="admin-loaded-art-grid">
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Box Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-cover-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('cover_image')} disabled={!adminForm.cover_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-cover-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'cover_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.cover_image} on:click={() => openLaunchboxArtPicker('cover_image')} aria-label="Choose box art from available sources">
                              {#if adminForm.cover_image}
                                <img src={adminForm.cover_image} alt="Fetched box art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No box art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Disc/Cart Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-disc-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('disc_image')} disabled={!adminForm.disc_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-disc-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'disc_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.disc_image} on:click={() => openLaunchboxArtPicker('disc_image')} aria-label="Choose disc or cart art from available sources">
                              {#if adminForm.disc_image}
                                <img src={adminForm.disc_image} alt="Fetched disc/cart art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No disc/cart art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Spine Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-spine-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('spine_image')} disabled={!adminForm.spine_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-spine-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'spine_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.spine_image} on:click={() => openLaunchboxArtPicker('spine_image')} aria-label="Choose spine art from available sources">
                              {#if adminForm.spine_image}
                                <img src={adminForm.spine_image} alt="Fetched spine art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No spine art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                      </div>
                    </section>
                  {:else}
                    <section class="admin-loaded-art" aria-label="Loaded Album Art">
                      <p class="admin-loaded-art-title">Loaded Art</p>
                      <div class="admin-loaded-art-grid">
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Album Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-album-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('cover_image')} disabled={!adminForm.cover_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-album-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'cover_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.cover_image} on:click={() => openLaunchboxArtPicker('cover_image')} aria-label="Choose album art from Discogs and Deezer">
                              {#if adminForm.cover_image}
                                <img src={adminForm.cover_image} alt="Fetched album art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No album art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                      </div>
                    </section>
                  {/if}
                  <div class="form-field">
                    <label for="admin-item-title">Title</label>
                    <input id="admin-item-title" type="text" bind:value={adminForm.title} placeholder="Title" required />
                  </div>

                  {#if wishlistAdminSection === 'games'}
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
                    <div class="form-field">
                      <label for="admin-launchbox-url">Manual Fetch - LaunchBox Link (Optional)</label>
                      <div class="launchbox-url-fetch-row">
                        <input
                          id="admin-launchbox-url"
                          type="url"
                          bind:value={launchboxManualUrl}
                          placeholder="https://gamesdb.launchbox-app.com/games/details/..."
                        />
                        <button
                          type="button"
                          class="launchbox-fetch-button"
                          disabled={launchboxFetchBusy}
                          on:click={fetchLaunchBoxGameDataFromUrl}
                        >
                          {launchboxFetchBusy ? 'Fetching...' : 'Fetch'}
                        </button>
                      </div>
                    </div>
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
                    <div class="form-field">
                      <span class="star-field-label">Star Rating</span>
                      <div class="star-picker" role="group" aria-label="Star rating out of 5">
                        {#each [1, 2, 3, 4, 5] as n}
                          <button
                            type="button"
                            class="star-btn"
                            class:filled={adminForm.starRating !== null && n <= adminForm.starRating}
                            aria-label="{n} star{n !== 1 ? 's' : ''}"
                            on:click={() => { adminForm = { ...adminForm, starRating: adminForm.starRating === n ? null : n }; }}
                          >★</button>
                        {/each}
                        {#if adminForm.starRating !== null}
                          <button type="button" class="star-clear" on:click={() => { adminForm = { ...adminForm, starRating: null }; }} aria-label="Clear star rating">×</button>
                        {/if}
                      </div>
                      <p class="star-picker-preview" aria-live="polite">
                        {starDisplay(adminForm.starRating)}{adminForm.starRating !== null ? ` (${adminForm.starRating}/5)` : ''}
                      </p>
                    </div>
                  {:else}
                    <div class="form-field">
                      <label for="admin-artist">Artist</label>
                      <input id="admin-artist" type="text" bind:value={adminForm.artist} placeholder="Artist" />
                    </div>
                    <button
                      type="button"
                      class="launchbox-fetch-button"
                      class:pulse={canFetchMusicAlbumData() && !musicFetchBusy}
                      disabled={musicFetchBusy}
                      on:click={fetchMusicAlbumData}
                    >
                      {musicFetchBusy ? 'Fetching Music Data...' : 'Fetch Music Data'}
                    </button>
                    {#if musicFetchError}
                      <p class="admin-error launchbox-fetch-error">{musicFetchError}</p>
                    {/if}
                    <div class="form-field">
                      <label for="admin-music-genre">Genre</label>
                      <select id="admin-music-genre" bind:value={adminMusicGenreChoice} required on:change={() => { adminForm = { ...adminForm, musicGenre: adminMusicGenreChoice }; }}>
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
                    <div class="form-field">
                      <span class="star-field-label">Star Rating</span>
                      <div class="star-picker" role="group" aria-label="Album star rating out of 5">
                        {#each [1, 2, 3, 4, 5] as n}
                          <button
                            type="button"
                            class="star-btn"
                            class:filled={adminForm.starRating !== null && n <= adminForm.starRating}
                            aria-label="{n} star{n !== 1 ? 's' : ''}"
                            on:click={() => { adminForm = { ...adminForm, starRating: adminForm.starRating === n ? null : n }; }}
                          >★</button>
                        {/each}
                        {#if adminForm.starRating !== null}
                          <button type="button" class="star-clear" on:click={() => { adminForm = { ...adminForm, starRating: null }; }} aria-label="Clear star rating">×</button>
                        {/if}
                      </div>
                      <p class="star-picker-preview" aria-live="polite">
                        {starDisplay(adminForm.starRating)}{adminForm.starRating !== null ? ` (${adminForm.starRating}/5)` : ''}
                      </p>
                    </div>
                  {/if}
                  <div class="form-field">
                    <label for="admin-notes">Overview</label>
                    <textarea id="admin-notes" bind:value={adminForm.notes} rows="3" placeholder="Overview"></textarea>
                  </div>
                  <div class="form-actions">
                    <button type="submit" disabled={adminBusy}>{wishlistEditingId === 'new' ? 'Create Wish List Item' : 'Save Changes'}</button>
                    <button type="button" on:click={() => { wishlistEditingId = null; adminContextItem = null; }}>Clear</button>
                  </div>
                  {#if adminError}
                    <p class="admin-error">{adminError}</p>
                  {/if}
                  {#if adminMessage}
                    <p class="admin-status">{adminMessage}</p>
                  {/if}
                </form>
              {:else if adminEditingId !== null}
                <form class="admin-form" on:submit|preventDefault={saveAdminItem} novalidate>
                  <h3>{adminContextItem?.title ?? 'Edit Item'}</h3>
                  {#if libraryAdminTab === 'games'}
                    <section class="admin-loaded-art" aria-label="Loaded Art">
                      <p class="admin-loaded-art-title">Loaded Art</p>
                      <div class="admin-loaded-art-grid">
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Box Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-cover-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('cover_image')} disabled={!adminForm.cover_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-cover-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'cover_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.cover_image} on:click={() => openLaunchboxArtPicker('cover_image')} aria-label="Choose box art from available sources">
                              {#if adminForm.cover_image}
                                <img src={adminForm.cover_image} alt="Fetched box art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No box art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Disc/Cart Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-disc-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('disc_image')} disabled={!adminForm.disc_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-disc-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'disc_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.disc_image} on:click={() => openLaunchboxArtPicker('disc_image')} aria-label="Choose disc or cart art from available sources">
                              {#if adminForm.disc_image}
                                <img src={adminForm.disc_image} alt="Fetched disc/cart art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No disc/cart art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Spine Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-spine-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('spine_image')} disabled={!adminForm.spine_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-spine-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'spine_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.spine_image} on:click={() => openLaunchboxArtPicker('spine_image')} aria-label="Choose spine art from available sources">
                              {#if adminForm.spine_image}
                                <img src={adminForm.spine_image} alt="Fetched spine art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No spine art loaded</div>
                              {/if}
                            </button>
                          </div>
                        </div>
                      </div>
                    </section>
                  {:else if libraryAdminTab === 'music'}
                    <section class="admin-loaded-art" aria-label="Loaded Album Art">
                      <p class="admin-loaded-art-title">Loaded Art</p>
                      <div class="admin-loaded-art-grid">
                        <div class="admin-loaded-art-item">
                          <div class="admin-loaded-art-item-header">
                            <span>Album Art</span>
                            <div class="admin-art-item-actions">
                              <label for="admin-upload-album-art" class="admin-art-upload-button">Upload</label>
                              <button type="button" class="admin-art-delete-button" on:click={() => clearAdminArtField('cover_image')} disabled={!adminForm.cover_image}>Delete</button>
                            </div>
                            <input
                              id="admin-upload-album-art"
                              class="admin-art-upload-input"
                              type="file"
                              accept="image/*"
                              on:change={(e) => handleGameArtUpload(e, 'cover_image')}
                            />
                          </div>
                          <div class="admin-loaded-art-media">
                            <button type="button" class="admin-loaded-art-preview" class:admin-loaded-art-preview--empty={!adminForm.cover_image} on:click={() => openLaunchboxArtPicker('cover_image')} aria-label="Choose album art from Discogs and Deezer">
                              {#if adminForm.cover_image}
                                <img src={adminForm.cover_image} alt="Fetched album art" />
                              {:else}
                                <div class="admin-loaded-art-empty">No album art loaded</div>
                              {/if}
                            </button>
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
                    <div class="form-field">
                      <label for="admin-launchbox-url">Manual Fetch - LaunchBox Link (Optional)</label>
                      <div class="launchbox-url-fetch-row">
                        <input
                          id="admin-launchbox-url"
                          type="url"
                          bind:value={launchboxManualUrl}
                          placeholder="https://gamesdb.launchbox-app.com/games/details/..."
                        />
                        <button
                          type="button"
                          class="launchbox-fetch-button"
                          disabled={launchboxFetchBusy}
                          on:click={fetchLaunchBoxGameDataFromUrl}
                        >
                          {launchboxFetchBusy ? 'Fetching...' : 'Fetch'}
                        </button>
                      </div>
                    </div>
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
                    <div class="form-field">
                      <span class="star-field-label">Star Rating</span>
                      <div class="star-picker" role="group" aria-label="Star rating out of 5">
                        {#each [1, 2, 3, 4, 5] as n}
                          <button
                            type="button"
                            class="star-btn"
                            class:filled={adminForm.starRating !== null && n <= adminForm.starRating}
                            aria-label="{n} star{n !== 1 ? 's' : ''}"
                            on:click={() => { adminForm = { ...adminForm, starRating: adminForm.starRating === n ? null : n }; }}
                          >★</button>
                        {/each}
                        {#if adminForm.starRating !== null}
                          <button type="button" class="star-clear" on:click={() => { adminForm = { ...adminForm, starRating: null }; }} aria-label="Clear star rating">×</button>
                        {/if}
                      </div>
                      <p class="star-picker-preview" aria-live="polite">
                        {starDisplay(adminForm.starRating)}{adminForm.starRating !== null ? ` (${adminForm.starRating}/5)` : ''}
                      </p>
                    </div>
                  {:else}
                    <div class="form-field">
                      <label for="admin-artist">Artist</label>
                      <input id="admin-artist" type="text" bind:value={adminForm.artist} placeholder="Artist" />
                    </div>
                    <button
                      type="button"
                      class="launchbox-fetch-button"
                      class:pulse={canFetchMusicAlbumData() && !musicFetchBusy}
                      disabled={musicFetchBusy}
                      on:click={fetchMusicAlbumData}
                    >
                      {musicFetchBusy ? 'Fetching Music Data...' : 'Fetch Music Data'}
                    </button>
                    {#if musicFetchError}
                      <p class="admin-error launchbox-fetch-error">{musicFetchError}</p>
                    {/if}
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
                    <div class="form-field">
                      <span class="star-field-label">Star Rating</span>
                      <div class="star-picker" role="group" aria-label="Album star rating out of 5">
                        {#each [1, 2, 3, 4, 5] as n}
                          <button
                            type="button"
                            class="star-btn"
                            class:filled={adminForm.starRating !== null && n <= adminForm.starRating}
                            aria-label="{n} star{n !== 1 ? 's' : ''}"
                            on:click={() => { adminForm = { ...adminForm, starRating: adminForm.starRating === n ? null : n }; }}
                          >★</button>
                        {/each}
                        {#if adminForm.starRating !== null}
                          <button type="button" class="star-clear" on:click={() => { adminForm = { ...adminForm, starRating: null }; }} aria-label="Clear star rating">×</button>
                        {/if}
                      </div>
                      <p class="star-picker-preview" aria-live="polite">
                        {starDisplay(adminForm.starRating)}{adminForm.starRating !== null ? ` (${adminForm.starRating}/5)` : ''}
                      </p>
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

                  {#if adminError}
                    <p class="admin-error">{adminError}</p>
                  {/if}
                  {#if adminMessage}
                    <p class="admin-status">{adminMessage}</p>
                  {/if}
                </form>
              {:else}
                <div class="admin-form-empty">
                  <p>
                    {#if libraryAdminTab === 'wishlists'}
                      Select a wish list item to edit, or create a new one.
                    {:else}
                      Select an item from the list to edit, or click the button below to create a new one.
                    {/if}
                  </p>
                  <button type="button" on:click={() => {
                    if (libraryAdminTab === 'wishlists') {
                      if (wishlistAdminSection === 'console') {
                        resetWishlistSystemForm();
                      } else {
                        resetAdminForm(wishlistAdminSection === 'music' ? 'Music' : 'Games');
                      }
                      wishlistEditingId = 'new';
                      return;
                    }
                    resetAdminForm(libraryAdminTab === 'music' ? 'Music' : 'Games');
                    adminEditingId = -1;
                  }}>Create New {libraryAdminTab === 'wishlists' ? (wishlistAdminSection === 'console' ? 'Console' : wishlistAdminSection === 'games' ? 'Game' : 'Album') : libraryAdminTab === 'games' ? 'Game' : 'Album'}</button>
                </div>
              {/if}
            </div>
          </div>
        {/if}

        {#if isAdmin && adminMode !== 'library' && adminError}
          <p class="admin-error">{adminError}</p>
        {/if}
        {#if isAdmin && adminMode !== 'library' && adminMessage}
          <p class="admin-status">{adminMessage}</p>
        {/if}
      {/if}
    </div>
  </div>
{/if}

{#if fetchToolsOpen}
  <div class="fetch-tools-overlay" role="dialog" aria-modal="true" aria-label="Fetch tools">
    <button type="button" class="fetch-tools-backdrop" aria-label="Close fetch tools" on:click={closeFetchToolsPopup}></button>
    <div class="fetch-tools-panel">
      <div class="admin-header">
        <h2>Fetch Tools</h2>
        {#if fetchToolsBusy}
          <button type="button" class="ghost" on:click={cancelFetchToolsOperation}>Cancel</button>
        {/if}
        <button type="button" class="popup-close" aria-label="Close fetch tools" on:click={closeFetchToolsPopup}>×</button>
      </div>
      <div class="fetch-tools-list">
        {#each fetchToolEntries as tool}
          <section class="fetch-tool-row" aria-label={tool.title}>
            <div class="fetch-tool-copy">
              <h3>{tool.title}</h3>
              <p>{tool.description}</p>
            </div>
            <div class="fetch-tool-actions">
              {#if tool.key === 'gameArt' || tool.key === 'gameDetails' || tool.key === 'gamePrice'}
                <label class="fetch-tool-scope">
                  <span>Library</span>
                  <select bind:value={fetchToolConsoleScopes[tool.key]} disabled={fetchToolsBusy || fetchToolStates[tool.key].running}>
                    <option value="all">All game libraries + wishlist</option>
                    <optgroup label="Single Console">
                      {#each adminConsoleOptions as consoleName}
                        <option value={consoleName}>{consoleName} library only</option>
                      {/each}
                    </optgroup>
                  </select>
                </label>
              {/if}
              <button
                type="button"
                class="fetch-tool-button fetch-tool-button--empty"
                on:click={() => runFetchTool(tool.key, false)}
                disabled={fetchToolsBusy || fetchToolStates[tool.key].running}
              >{fetchToolStates[tool.key].running && fetchToolStates[tool.key].runningAction === 'empty' ? 'Running' : 'Fetch Empty Only'}</button>
              <button
                type="button"
                class="fetch-tool-button fetch-tool-button--all ghost"
                on:click={() => runFetchTool(tool.key, true)}
                disabled={fetchToolsBusy || fetchToolStates[tool.key].running}
              >{fetchToolStates[tool.key].running && fetchToolStates[tool.key].runningAction === 'all' ? 'Running' : 'Re-fetch All'}</button>
            </div>
            <div class="fetch-tool-state" aria-live="polite">
              <p class="fetch-tool-status">{fetchToolStates[tool.key].statusText || 'Idle.'}</p>
              {#if fetchToolStates[tool.key].running || fetchToolStates[tool.key].showProgress}
                <div class="fetch-tool-progress-track" aria-hidden="true">
                  <span class="fetch-tool-progress-fill" style={`width: ${fetchToolStates[tool.key].progress}%;`}></span>
                </div>
              {/if}
              {#if fetchToolStates[tool.key].errorText}
                <p class="fetch-tool-error">{fetchToolStates[tool.key].errorText}</p>
              {/if}
              {#if fetchToolStates[tool.key].activity.length}
                <div class="bulk-result-list fetch-tool-result-list">
                  {#each fetchToolStates[tool.key].activity as result (result.key)}
                    <div
                      class="bulk-result-item fetch-tool-result-item"
                      class:bulk-success={result.status === 'success'}
                      class:bulk-error={result.status === 'error'}
                      class:fetch-tool-result-running={result.status === 'running'}
                    >
                      <span class="bulk-result-line">{result.line}</span>
                      <span class="bulk-result-msg">{result.message}</span>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          </section>
        {/each}
      </div>
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
