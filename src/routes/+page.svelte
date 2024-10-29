<script>
	import { onMount } from 'svelte';
    import { darkMode } from '$lib/darkmode';
    import { server_url } from '$lib/index';
    import Header from '../components/header.svelte';

    let ITEMS_PER_PAGE = 50;
    let currentPage = 0;
    let totalPages = 0;

    let feed_items = [];

    let get_feed_page = async () => {
        const response = await fetch(`${server_url}/get_feed_items?page_num=${currentPage}&items_per_page=${ITEMS_PER_PAGE}`);
        if (response.ok) {
            const data = await response.json();
            feed_items = data.items;
            totalPages = data.total_pages;
        }
    }

    onMount(async () => {
        await get_feed_page();
    });

    async function nextPage() {
        if (currentPage < totalPages - 1) {
            currentPage++;
            await get_feed_page();
        }
    }

    async function prevPage() {
        if (currentPage > 0) {
            currentPage--;
            await get_feed_page();
        }
    }

    async function firstPage() {
        currentPage = 0;
        await get_feed_page();
    }

    onMount(darkMode.init);
</script>


<div>
    <Header />

    <div class="feed-list">
        {#each feed_items as feed}
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
            <button on:click={prevPage}>&larr;</button>
            <small>page {currentPage + 1}</small>
            <button on:click={nextPage}>&rarr;</button>
        </div>
        <div>
            <button on:click={firstPage}>view latest</button>
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