<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { MediaItem } from './types';

  let media: MediaItem[] = [];
  let stage: 'boot' | 'menu' | 'console' | 'library' = 'boot';
  let bootError = false;
  let bootNeedsClick = false;
  let bootVideoRef: HTMLVideoElement | null = null;
  let bootMuted = true;
  let bootShowOptions = false;
  let bootHoveredOption: string | null = null;

  let categories: string[] = [];
  let selectedCategory: string | null = null;
  let selectedConsole: string | null = null;
  let filtersLoaded = false;
  let search = '';
  let platform = '';
  let genre = '';
  let yearMin: number | null = null;
  let yearMax: number | null = null;
  let players: number | null = null;
  let selected: MediaItem | null = null;
  let filters = {
    platforms: [] as string[],
    genres: [] as string[],
    years: [] as number[],
  };
  const playerOptions = [1, 2, 3, 4];
  const playerIcons = {
    1: '1P',
    2: '2P',
    3: '3P',
    4: '4P',
  };
  const consoles = ['PS2', 'PS3', 'PS4', 'Nintendo DS', 'GameBoy'];
  let isTransitioning = false;
  let transitionOverlay = false;
  let hoverStates: Record<string, { rotateX: number; rotateY: number; glowX: number; glowY: number }> = {};

  function playerLabel(value: number | null) {
    return value ? playerIcons[value] ?? `${value}P` : 'P';
  }

  function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function fadeOutBootAudio(duration = 480) {
    if (!bootVideoRef || bootVideoRef.paused) return;
    const steps = 12;
    const interval = duration / steps;
    let volume = bootVideoRef.volume || 1;
    for (let i = 0; i < steps; i += 1) {
      volume = Math.max(0, volume - 1 / steps);
      bootVideoRef.volume = volume;
      await sleep(interval);
    }
    bootVideoRef.volume = 0;
  }

  async function transitionTo(nextStage: typeof stage) {
    isTransitioning = true;
    transitionOverlay = true;
    await tick();
    await fadeOutBootAudio();
    await sleep(320);
    stage = nextStage;
    await tick();
    await sleep(260);
    transitionOverlay = false;
    isTransitioning = false;
  }

  function getIconHoverStyle(itemId: string | number) {
    const state = hoverStates[String(itemId)];
    return state
      ? `--hover-rotatex: ${state.rotateX}deg; --hover-rotatey: ${state.rotateY}deg; --hover-glowx: ${state.glowX}px; --hover-glowy: ${state.glowY}px;`
      : '';
  }

  function updateIconHover(itemId: string | number, event: MouseEvent) {
    const element = event.currentTarget as HTMLElement | null;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const relX = event.clientX - rect.left - rect.width / 2;
    const relY = event.clientY - rect.top - rect.height / 2;
    const rotateX = Math.max(-8, Math.min(8, -(relY / (rect.height / 2)) * 6));
    const rotateY = Math.max(-8, Math.min(8, (relX / (rect.width / 2)) * 6));
    hoverStates = {
      ...hoverStates,
      [String(itemId)]: {
        rotateX,
        rotateY,
        glowX: event.clientX - rect.left,
        glowY: event.clientY - rect.top,
      },
    };
  }

  function clearIconHover(itemId: string | number) {
    const key = String(itemId);
    if (!(key in hoverStates)) return;
    const { [key]: removed, ...rest } = hoverStates;
    hoverStates = rest;
  }

  async function tryStartBoot() {
    if (!bootVideoRef) return;
    try {
      bootNeedsClick = false;
      bootError = false;
      bootMuted = false;
      bootVideoRef.muted = false;
      bootVideoRef.volume = 1;
      await bootVideoRef.play();
    } catch {
      bootNeedsClick = false;
      bootError = true;
      bootShowOptions = true;
    }
  }

  function handleBootTimeUpdate() {
    if (!bootVideoRef) return;
    const currentTime = bootVideoRef.currentTime;
    if ((currentTime >= 9 || currentTime >= (bootVideoRef.duration - 0.5)) && !bootShowOptions) {
      bootShowOptions = true;
    }
  }

  function handleBootEnded() {
    bootShowOptions = true;
  }

  function handleBootError() {
    bootError = true;
    bootNeedsClick = false;
    bootShowOptions = true;
  }

  async function loadMedia() {
    const params = new URLSearchParams();
    if (selectedCategory) params.set('category', selectedCategory);
    if (selectedConsole && selectedCategory === 'Games') params.set('platform', selectedConsole);
    if (platform) params.set('platform', platform);
    if (genre) params.set('genre', genre);
    if (yearMin !== null) params.set('year_min', String(yearMin));
    if (yearMax !== null) params.set('year_max', String(yearMax));
    if (players !== null) params.set('players', String(players));
    if (search) params.set('search', search);

    const response = await fetch(`/api/media?${params.toString()}`);
    media = await response.json();
  }

  async function loadFilters() {
    filtersLoaded = false;
    try {
      const response = await fetch('/api/filters');
      const data = await response.json();
      categories = data.categories && data.categories.length ? data.categories.map((name: string) => {
        if (name === 'Browser') return 'Games';
        if (name === 'System Configuration') return 'Music';
        return name;
      }) : ['Games', 'Music'];
      filters.platforms = data.platforms || [];
      filters.genres = data.genres || [];
      filters.years = data.years || [];
    } catch (error) {
      console.error('Failed to load filters', error);
      categories = ['Games', 'Music'];
    } finally {
      filtersLoaded = true;
    }
  }

  async function setCategory(value: string) {
    selectedCategory = value;
    selected = null;
    selectedConsole = null;
    const nextStage = value === 'Games' ? 'console' : 'library';
    await transitionTo(nextStage);
    await loadFilters();
    await loadMedia();
  }

  function clearFilters() {
    platform = '';
    genre = '';
    yearMin = null;
    yearMax = null;
    players = null;
    search = '';
    loadMedia();
  }

  async function chooseBootCategory(categoryName: string) {
    selectedCategory = categoryName;
    selected = null;
    selectedConsole = null;
    const nextStage = categoryName === 'Games' ? 'console' : 'library';
    await transitionTo(nextStage);
    await loadFilters();
    await loadMedia();
  }

  async function chooseConsole(consoleName: string) {
    selectedConsole = consoleName;
    selected = null;
    await transitionTo('library');
    await loadMedia();
  }

  function selectItem(item: MediaItem) {
    selected = item;
  }

  function closeDetails() {
    selected = null;
  }

  async function goBack() {
    if (stage === 'library') {
      if (selectedCategory === 'Games') {
        selected = null;
        await transitionTo('console');
        return;
      }
      selectedCategory = null;
      selected = null;
      await transitionTo('menu');
      return;
    }

    if (stage === 'console') {
      selectedCategory = null;
      selectedConsole = null;
      selected = null;
      await transitionTo('menu');
    }
  }

  onMount(() => {
    setTimeout(tryStartBoot, 80);
  });
</script>

{#if stage === 'boot'}
  <div
    class="boot-screen"
    role="button"
    tabindex="0"
    on:click={tryStartBoot}
    on:keydown={(event) => event.key === 'Enter' && tryStartBoot()}
  >
    {#if !bootError}
      <video
        bind:this={bootVideoRef}
        class="boot-video"
        src="/suggestions/ps2-intro.mp4"
        preload="auto"
        autoplay
        playsinline
        muted={bootMuted}
        on:timeupdate={handleBootTimeUpdate}
        on:ended={handleBootEnded}
        on:error={handleBootError}
      />
    {/if}

    <div class="boot-overlay">
      {#if bootShowOptions}
        <div class="boot-options" transition:fade>
          <button
            type="button"
            class="boot-option"
            class:hovered={bootHoveredOption === 'Games'}
            on:click={() => chooseBootCategory('Games')}
            on:mouseenter={() => (bootHoveredOption = 'Games')}
            on:mouseleave={() => (bootHoveredOption = null)}
          >
            <span>Games</span>
            <small>Browser</small>
          </button>
          <button
            type="button"
            class="boot-option"
            class:hovered={bootHoveredOption === 'Music'}
            on:click={() => chooseBootCategory('Music')}
            on:mouseenter={() => (bootHoveredOption = 'Music')}
            on:mouseleave={() => (bootHoveredOption = null)}
          >
            <span>Music</span>
            <small>System Configuration</small>
          </button>
        </div>
      {/if}
      {#if bootNeedsClick}
        <div class="boot-prompt">Click or tap to enable sound</div>
      {:else if bootError && !bootShowOptions}
        <div class="boot-prompt">Boot video cannot play on this browser. Choose an option to continue.</div>
      {/if}
    </div>

    {#if bootError}
      <div class="boot-panel fallback">
        <div class="ps2-logo"></div>
        <div class="boot-text">PS2 Boot Video Problem</div>
        <div class="boot-prompt">This browser cannot play the supplied boot video. Choose Games or Music to continue.</div>
      </div>
    {/if}
  </div>
{:else}
  {#key stage}
    <div class="screen" class:transitioning={isTransitioning} transition:fade={{ duration: 260 }}>
      {#if transitionOverlay}
        <div class="transition-overlay"></div>
      {/if}
      <div class="header">
      <div class="title-block">
        <h1>MEMORY CARD</h1>
        <p>PLAYSTATION 2 BROWSER</p>
      </div>
      {#if stage !== 'menu'}
        <button class="back-btn" type="button" on:click={goBack}>
          Back
        </button>
      {/if}
    </div>

    {#if stage === 'menu'}
      <div class="menu-grid">
        {#each categories as categoryName}
          <button type="button" class="browser-card" on:click={() => setCategory(categoryName)}>
            <div class="browser-label">CARD</div>
            <h2>{categoryName}</h2>
            <p>Load your {categoryName} files from the PS2 browser.</p>
          </button>
        {/each}
      </div>
    {:else if stage === 'console'}
      <div class="console-grid">
        {#each consoles as consoleName}
          <button type="button" class="console-card" on:click={() => chooseConsole(consoleName)}>
            <div class="console-icon">{consoleName}</div>
          </button>
        {/each}
      </div>
    {:else}
      <div class="library-shell">
        <div class="library-header">
          <div>
            <div class="library-title">Memory Card ({selectedConsole ?? 'PS2'}) / 1</div>
            <div class="library-subtitle">{media.length} items · 2,138 KB Free</div>
          </div>
          <div class="library-selected-name">{selected?.title ?? (selectedCategory === 'Music' ? 'Your System Configuration' : 'Game Browser')}</div>
        </div>

        <div class="filter-toolbar">
          <input class="search-input" type="text" placeholder="Search title, artist, genre, tags" bind:value={search} on:input={loadMedia} />
          <select class="player-select" bind:value={players} on:change={loadMedia}>
            <option value="">P</option>
            {#each playerOptions as option}
              <option value={option}>{playerLabel(option)}</option>
            {/each}
          </select>
          <select class="compact-select" bind:value={platform} on:change={loadMedia}>
            <option value="">Platform</option>
            {#each filters.platforms as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
          <select class="compact-select" bind:value={genre} on:change={loadMedia}>
            <option value="">Genre</option>
            {#each filters.genres as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
          <button type="button" class="clear-button" on:click={clearFilters}>Clear</button>
        </div>

        <div class="icon-grid">
          {#each media as item, index}
            <button
              type="button"
              class="icon-slot"
              class:selected={selected?.id === item.id}
              on:click={() => selectItem(item)}
              on:mouseenter={(event) => updateIconHover(item.id, event)}
              on:mousemove={(event) => updateIconHover(item.id, event)}
              on:mouseleave={() => clearIconHover(item.id)}
              style="animation-delay: {index * 80}ms; {getIconHoverStyle(item.id)}"
            >
              <div class="icon-bg"></div>
              {#if item.cover_image}
                <img src={item.cover_image} alt={item.title} class="icon-image" style="animation-delay: {index * 100 + 100}ms;" />
              {:else}
                <div class="icon-fallback">{item.title.slice(0, 3).toUpperCase()}</div>
              {/if}
              <span class="icon-label">{item.title}</span>
            </button>
          {/each}
        </div>

        {#if selected}
          <div class="details-overlay" role="dialog" tabindex="0" on:click|self={closeDetails}>
            <div class="details-card">
              <div class="details-header">
                <div>
                  <div class="detail-title">Memory Card ({selectedConsole ?? selectedCategory}) / 1</div>
                  <div class="detail-subtitle">{selected.category} • {selected.platform ?? selected.format ?? 'Unknown'}</div>
                </div>
                <button class="close-btn" type="button" on:click={closeDetails}>×</button>
              </div>
              <div class="details-content">
                <h3>{selected.title}</h3>
                <p>{selected.artist ?? selected.publisher ?? 'No additional subtitle available'}</p>
                <div class="details-metadata">
                  <div><span>Date Saved</span><strong>11/29/2009 12:27:35 PM</strong></div>
                  <div><span>Size</span><strong>20KB</strong></div>
                  <div><span>Genre</span><strong>{selected.genre}</strong></div>
                  <div><span>Region</span><strong>{selected.region ?? 'N/A'}</strong></div>
                  <div><span>Players</span><strong>{selected.players ?? 'N/A'}</strong></div>
                </div>
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/if}
    </div>
  {/key}
{/if}
