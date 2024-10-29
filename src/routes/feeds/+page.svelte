<script>
	import { onMount } from 'svelte';
    import { darkMode } from '$lib/darkmode';
    import { feeds, server_url } from '$lib/index';
    import Header from '../../components/header.svelte';

    onMount(async () => {
        const response = await fetch(`${server_url}/get_feeds`);
        const data = await response.json();
        feeds.set(data);
    });

    let newFeedUrl = '';
    let newFeedName = '';

    function deleteFeed(id) {
        fetch(`${server_url}/delete_feed/${id}`, {
            method: 'DELETE'
        }).then(() => {
            feeds.set(feeds.filter(feed => feed[0] !== id));
        });
    }

    async function handleSubmit() {
        const response = await fetch(
            `${server_url}/create_feed?feed_url=${encodeURIComponent(newFeedUrl)}&feed_name=${encodeURIComponent(newFeedName)}`,
            {
                method: 'POST'
            }
        );

        if (response.ok) {
            const getFeeds = await fetch(`${server_url}/get_feeds`);
            const data = await getFeeds.json();
            feeds.set(data);
            newFeedUrl = '';
            newFeedName = '';
        }
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

    <div>
        {#each $feeds as feed}
            <p>
                <strong>
                    <a href={feed[1]} target="_blank" rel="noopener noreferrer">{feed[2]}</a>
                </strong>

                <button on:click={() => deleteFeed(feed[0])} aria-label="Delete Feed">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-trash"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                </button>
            </p>
        {/each}
    </div>
</div>

<style>
    svg {
        color: var(--flexoki-red-400);
    }

    button {
        color: var(--text-color);
        background: none;
        border: none;
    }

    button:hover {
        color: var(--link-color);
        transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
        transition-duration: 100ms;
        cursor: pointer;
    }

    button:has(svg) {
        width: 1.1rem;
        height: 1.1rem;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        vertical-align: middle;
        transform: translateY(-1px);
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