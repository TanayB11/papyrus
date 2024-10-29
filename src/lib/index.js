import { writable } from 'svelte/store';

export const feeds = writable([]);

const backend_port = import.meta.env.VITE_BACKEND_PORT;
export const server_url = `http://localhost:${backend_port}`;
