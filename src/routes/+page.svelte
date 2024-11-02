<script>
	import { onMount } from 'svelte';
    import { darkMode } from '$lib/darkmode';
    import { get_feed_page, current_page, total_pages, nextPage, prevPage, firstPage, feed_items, server_url } from '$lib/index';
    import Header from '../components/header.svelte';


    onMount(async () => {
        await get_feed_page();
    });

    async function toggle_like_article(url) {
        await fetch(`${server_url}/toggle_like_article?url=${encodeURIComponent(url)}`, { method: 'POST' });
        await get_feed_page(false);
    }

    onMount(darkMode.init);
</script>


<div>
    <Header />

    <div class="feed-list">
        {#if $feed_items.length === 0}
            <p style="text-align: center;">no articles found</p>
        {/if}
        {#each $feed_items as feed}
            <p>
                <strong>
                    <a href={feed.url} target="_blank" rel="noopener noreferrer">{feed.title}</a>
                </strong>
                <br>
                <small>{feed.name} • {feed.date} • {feed.svm_prob.toFixed(2)} • <button onclick={() => toggle_like_article(feed.url)} class="more_like_this">{feed.is_liked ? 'unlike' : 'like'}</button></small>
            </p>
        {/each}
    </div>

    <hr>

    <footer>
        <div>
            <button onclick={prevPage}>&larr;</button>
            <small>page {$current_page + 1}/{$total_pages}</small>
            <button onclick={nextPage}>&rarr;</button>
        </div>
        <div>
            <button onclick={firstPage}>view latest</button>
        </div>
    </footer>
</div>

<style>
    .feed-list {
        margin: 0;
        padding-bottom: 1rem;
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

    .more_like_this {
        color: var(--link-color);
        opacity: 100%;
        transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
        transition-duration: 100ms;
        text-decoration: none;
        padding: 0;
    }

    .more_like_this:hover {
        color: var(--link-hover-color);
        transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
        transition-duration: 100ms;
    }
</style>