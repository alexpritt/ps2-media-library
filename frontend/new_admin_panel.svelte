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
                <input type="text" bind:value={adminSearchQuery} placeholder="Search by title..." />
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
                    <div class="admin-row" class:active={adminEditingId === item.id} on:click={() => openAdminMode('library', libraryAdminTab, item)}>
                      <div class="admin-row-content">
                        <strong>{item.title}</strong>
                        <small>{item.platform ?? item.format ?? item.artist ?? 'Unknown'}</small>
                      </div>
                      <div class="admin-row-actions" on:click|stopPropagation>
                        <button type="button" on:click={() => openAdminMode('library', libraryAdminTab, item)}>Edit</button>
                        <button type="button" class="danger" on:click={() => openDeleteConfirm(item)}>Delete</button>
                      </div>
                    </div>
                  {/if}
                {/each}
              </div>

              {#if adminListTotalPages > 1}
                <div class="admin-list-pager">
                  <button type="button" on:click={() => (adminListPage = Math.max(0, adminListPage - 1))} disabled={adminListPage === 0} aria-label="Previous page">←</button>
                  <div class="admin-pager-info">{adminListPage + 1} / {adminListTotalPages}</div>
                  <button type="button" on:click={() => (adminListPage = Math.min(adminListTotalPages - 1, adminListPage + 1))} disabled={adminListPage >= adminListTotalPages - 1} aria-label="Next page">→</button>
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

                  <select bind:value={adminForm.genre} required>
                    <option value="" disabled>Select genre</option>
                    {#each adminGenreOptions as genreName}
                      <option value={genreName}>{genreName}</option>
                    {/each}
                  </select>
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
