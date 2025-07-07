<script>
	import { onMount } from 'svelte';
    import { darkMode } from '$lib/darkmode';
    import { feeds, server_url, get_feed_page, updateArticlesForFeedVisibility } from '$lib/index';
    import Header from '../../components/header.svelte';

    onMount(async () => {
        const response = await fetch(`${server_url}/get_feeds`);
        const data = await response.json();
        feeds.set(data);
    });

    let newFeedUrl = '';
    let newFeedName = '';

    async function refreshFeeds() {
        const getFeeds = await fetch(`${server_url}/get_feeds`, {
            headers: {
                'Cache-Control': 'no-cache'
            }
        });
        const data = await getFeeds.json();
        feeds.set(data);
        newFeedUrl = '';
        newFeedName = '';
    }

    async function deleteFeed(url) {
        const response = await fetch(`${server_url}/delete_feed/${encodeURIComponent(url)}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            await refreshFeeds();
        }

        get_feed_page(false); // run in background
    }

    async function toggleFeedVisibility(url) {
        // Get current visibility state before toggling
        const currentFeed = $feeds.find(feed => feed[1] === url);
        const newVisibility = !currentFeed[4];

        // Optimistically update the UI
        feeds.update(feedList => 
            feedList.map(feed => 
                feed[1] === url 
                    ? [feed[0], feed[1], feed[2], feed[3], newVisibility]
                    : feed
            )
        );

        // Immediately update articles page
        updateArticlesForFeedVisibility(url, newVisibility);

        try {
            const response = await fetch(`${server_url}/toggle_feed_visibility?feed_url=${encodeURIComponent(url)}`, {
                method: 'POST'
            });

            if (!response.ok) {
                // Revert on error
                feeds.update(feedList => 
                    feedList.map(feed => 
                        feed[1] === url 
                            ? [feed[0], feed[1], feed[2], feed[3], !newVisibility]
                            : feed
                    )
                );
                // Revert articles page too
                updateArticlesForFeedVisibility(url, !newVisibility);
            }
        } catch (error) {
            // Revert on error
            feeds.update(feedList => 
                feedList.map(feed => 
                    feed[1] === url 
                        ? [feed[0], feed[1], feed[2], feed[3], !newVisibility]
                        : feed
                )
            );
            // Revert articles page too
            updateArticlesForFeedVisibility(url, !newVisibility);
        }
    }

    async function handleSubmit() {
        const response = await fetch(`${server_url}/create_feed?feed_url=${encodeURIComponent(newFeedUrl)}&feed_name=${encodeURIComponent(newFeedName)}`, {
            method: 'POST',
        });

        if (response.ok) {
            await refreshFeeds();
        }

        get_feed_page(false);
    }

    // Set dark theme
    onMount(darkMode.init);
</script>


<div>
    <Header />

    <form class="add-feed-form" on:submit|preventDefault={handleSubmit}>
        <strong>new feed</strong>
        <div>
            <input
                type="url"
                bind:value={newFeedUrl}
                placeholder="URL"
                required
            />
            <input
                type="text"
                bind:value={newFeedName}
                placeholder="Name"
                required
            />
        </div>
        
        <button type="submit">add feed</button>
    </form>

    <div class="feeds-list">
        {#each $feeds as feed}
            <div class="feed-item">
                <div class="feed-info" class:hidden={!feed[4]}>
                    <strong>
                        <a href={feed[1]} target="_blank" rel="noopener noreferrer">{feed[2]}</a>
                    </strong>
                </div>
                
                <div class="feed-actions">
                    <button 
                        on:click|preventDefault={() => toggleFeedVisibility(feed[1])} 
                        aria-label={feed[4] ? "Hide Feed" : "Show Feed"}
                        class="visibility-btn"
                    >
                        {#if feed[4]}
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-eye"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                        {:else}
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-eye-off"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>
                        {/if}
                    </button>

                    <button 
                        on:click|preventDefault={() => deleteFeed(feed[1])} 
                        aria-label="Delete Feed"
                        class="delete-btn"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-trash"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>
        {/each}
    </div>
</div>

<style>
    .feeds-list {
        margin-top: 1.5rem;
    }

    .feed-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.75rem 0;
    }

    .feed-info {
        flex: 1;
    }

    .feed-info.hidden {
        opacity: 0.4;
    }

    .feed-info.hidden a {
        color: var(--flexoki-400);
        text-decoration: line-through;
    }

    .feed-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    button {
        color: var(--text-color);
        background: none;
        border: none;
        cursor: pointer;
    }

    button:hover {
        color: var(--link-color);
        transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
        transition-duration: 100ms;
    }

    .visibility-btn svg {
        color: var(--flexoki-blue-400);
    }

    .visibility-btn:hover svg {
        color: var(--flexoki-blue-600);
    }

    .delete-btn svg {
        color: var(--flexoki-red-400);
    }

    .delete-btn:hover svg {
        color: var(--flexoki-red-600);
    }

    button:has(svg) {
        width: 1.1rem;
        height: 1.1rem;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        vertical-align: middle;
        padding: 0;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .add-feed-form > button {
        padding-left: 0rem;
    }

    input {
        padding: 0.5rem;
        color: var(--text-color);
        border: 1px solid var(--text-color);
        border-radius: 4px;
        background: var(--background-color);
    }

    .add-feed-form > div {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        display: flex;
        flex-wrap: wrap;
        width: 100%;
        gap: 0.5rem;
    }

    .add-feed-form > div > input {
        padding: 0.5rem;
        flex: 1 1 200px;
    }

    .add-feed-form > button {
        padding: 0.5rem;
        color: var(--flexoki-white);
        border-radius: 4px;
        border: 1px solid var(--text-color);
    }

    .add-feed-form > button:hover {
        background-color: var(--flexoki-300);
        color: var(--flexoki-black);
        .dark & {
            background-color: var(--flexoki-500);
        }
        transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
        transition-duration: 100ms;
    }
</style>