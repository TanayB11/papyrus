<script>
	import { onMount } from 'svelte';
    import { darkMode } from '$lib/darkmode';
    import { get_feed_page, current_page, nextPage, prevPage, firstPage, feed_items } from '$lib/index';
    import Header from '../components/header.svelte';


    onMount(async () => {
        await get_feed_page();
    });

    onMount(darkMode.init);
</script>


<div>
    <Header />

    <div class="feed-list">
        {#each $feed_items as feed}
            <p>
                <strong>
                    <a href={feed.link} target="_blank" rel="noopener noreferrer">{feed.title}</a>
                </strong>
                <br>
                <small>{feed.feed_name} • {feed.date}</small>
                <!-- <br> <small>{feed.description}</small>
                <br> <small>{feed.summary}</small> -->
            </p>
        {/each}
    </div>

    <hr>

    <footer>
        <div>
            <button onclick={prevPage}>&larr;</button>
            <small>page {$current_page + 1}</small>
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
</style>