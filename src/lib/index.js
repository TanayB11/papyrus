import { get, writable } from 'svelte/store';

export const feeds = writable([]);
export const server_url = import.meta.env.VITE_BACKEND_URL;

// pagination for articles
export const feed_items = writable([]);
const ITEMS_PER_PAGE = 20;
export const current_page = writable(0);
export const total_pages = writable(0);

export const get_feed_page = async () => {
    const response = await fetch(`${server_url}/all_articles?page_num=${get(current_page)}&items_per_page=${ITEMS_PER_PAGE}`);
    if (response.ok) {
        const data = await response.json();
        feed_items.set(data.items);
        total_pages.set(data.total_pages);
    }
}

export const nextPage = async () => {
    if (get(current_page) < get(total_pages) - 1) {
        current_page.update(n => n + 1);
        await get_feed_page();
    }
}

export const prevPage = async () => {
    if (get(current_page) > 0) {
        current_page.update(n => n - 1);
        await get_feed_page();
    }
}

export const firstPage = async () => {
    current_page.set(0);
    await get_feed_page();
}
