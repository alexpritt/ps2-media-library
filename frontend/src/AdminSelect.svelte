<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { cubicOut } from 'svelte/easing';
  import { fade } from 'svelte/transition';
  import type { TransitionConfig } from 'svelte/transition';

  export let value: string | number = '';
  export let options: Array<{ value: string | number; label: string }> = [];
  export let id: string = '';
  export let required: boolean = false;
  export let disabled: boolean = false;
  export let solidUnderline: boolean = false;

  const dispatch = createEventDispatcher();

  let isOpen = false;
  let trigger: HTMLButtonElement | null = null;
  let prefersReducedMotion = false;

  function reducedMotionTransition(css: (t: number) => string): TransitionConfig {
    return {
      duration: prefersReducedMotion ? 0 : 1,
      easing: cubicOut,
      css,
    };
  }

  function dropdownTransition(_node: Element): TransitionConfig {
    if (prefersReducedMotion) {
      return reducedMotionTransition((t) => `opacity: ${t};`);
    }

    return {
      duration: 160,
      easing: cubicOut,
      css: (t) => {
        const scale = 0.985 + (0.015 * t);
        const y = (1 - t) * 6;
        return `opacity: ${t}; transform: translateY(${y}px) scale(${scale}); transform-origin: top center;`;
      },
    };
  }

  function handleSelect(optionValue: string | number) {
    value = optionValue;
    isOpen = false;
    dispatch('change', { value: optionValue });
  }

  function handleClickOutside(e: MouseEvent) {
    if (trigger && !trigger.contains(e.target as Node) && !(e.target as HTMLElement).closest('.admin-select-dropdown')) {
      isOpen = false;
    }
  }

  onMount(() => {
    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncReducedMotionPreference = () => {
      prefersReducedMotion = reducedMotionQuery.matches;
    };

    syncReducedMotionPreference();

    document.addEventListener('click', handleClickOutside);
    reducedMotionQuery.addEventListener('change', syncReducedMotionPreference);
    return () => {
      document.removeEventListener('click', handleClickOutside);
      reducedMotionQuery.removeEventListener('change', syncReducedMotionPreference);
    };
  });

  $: selectedLabel = options.find((o) => o.value === value)?.label || 'Select...';
</script>

<div class="admin-select-wrapper">
  <button
    bind:this={trigger}
    type="button"
    class="admin-select-trigger"
    class:admin-select-trigger--solid-underline={solidUnderline}
    {id}
    {disabled}
    data-required={required ? 'true' : undefined}
    on:click={() => (isOpen = !isOpen)}
    aria-haspopup="listbox"
    aria-expanded={isOpen}
  >
    <span class="admin-select-label">{selectedLabel}</span>
    <span class="admin-select-caret">▾</span>
  </button>

  {#if isOpen}
    <button
      type="button"
      class="admin-select-backdrop"
      aria-label="Close dropdown"
      transition:fade={{ duration: prefersReducedMotion ? 0 : 120 }}
      on:click={() => (isOpen = false)}
    ></button>
    <div class="admin-select-dropdown" role="listbox" transition:dropdownTransition>
      {#each options as option (option.value)}
        <button
          type="button"
          role="option"
          aria-selected={value === option.value}
          class:selected={value === option.value}
          on:click={() => handleSelect(option.value)}
        >
          {option.label}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .admin-select-wrapper {
    position: relative;
    width: 100%;
  }

  .admin-select-trigger {
    position: relative;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--hud-white);
    border: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0;
    padding: 8px 0;
    background: transparent;
    box-shadow: none;
    backdrop-filter: none;
    transition: border-bottom-color 180ms ease;
    text-shadow: none;
    letter-spacing: 0.04em;
    outline: none;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }

  .admin-select-trigger:hover .admin-select-label,
  .admin-select-trigger:focus-visible .admin-select-label {
    color: #5eb3ff;
  }

  .admin-select-trigger:hover,
  .admin-select-trigger:focus-visible {
    border-bottom-color: rgba(255, 255, 255, 0.6);
  }

  .admin-select-trigger--solid-underline {
    border-bottom-color: rgba(255, 255, 255, 0.2);
  }

  .admin-select-trigger--solid-underline:hover,
  .admin-select-trigger--solid-underline:focus-visible {
    border-bottom-color: rgba(255, 255, 255, 0.6);
  }

  .admin-select-trigger:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .admin-select-label {
    flex: 1;
    text-align: left;
    transition: color 180ms ease;
  }

  .admin-select-caret {
    margin-left: 8px;
    font-size: 0.7em;
    opacity: 0.7;
  }

  .admin-select-backdrop {
    position: fixed;
    inset: 0;
    background: transparent;
    z-index: 99;
    border: 0;
    cursor: default;
    padding: 0;
  }

  .admin-select-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    background: linear-gradient(120deg, rgba(172, 172, 172, 0.92), rgba(133, 133, 133, 0.94));
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 6px;
    z-index: 100;
    overflow: hidden;
    min-width: 100%;
    box-shadow: 0 12px 24px rgba(0, 0, 0, 0.42);
    display: flex;
    flex-direction: column;
    max-height: 280px;
    overflow-y: auto;
  }

  .admin-select-dropdown button {
    display: block;
    width: 100%;
    padding: 8px 12px;
    background: transparent;
    border: 0;
    color: rgba(245, 246, 251, 0.96);
    font-size: 0.84rem;
    letter-spacing: 0.04em;
    text-align: left;
    cursor: pointer;
    transition: background 150ms ease, color 150ms ease;
    text-shadow: 1px 1px 0 rgba(0, 0, 0, 0.55);
    opacity: 1;
    font-family: inherit;
    font-weight: 400;
  }

  .admin-select-dropdown button:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #5eb3ff;
  }

  .admin-select-dropdown button.selected {
    color: #5eb3ff;
    font-weight: 700;
    background: rgba(255, 255, 255, 0.1);
  }

  .admin-select-dropdown button + button {
    border-top: 1px solid rgba(255, 255, 255, 0.07);
  }
</style>
