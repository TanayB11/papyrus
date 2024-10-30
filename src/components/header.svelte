<script>
	import { onMount } from 'svelte';
    import { darkMode } from '$lib/darkmode';
    import { firstPage } from '$lib/index';

    onMount(darkMode.init);
</script>


<header>
    <a href="/" class="title" onclick={firstPage}>
        <h1 id="header-name">papyrus</h1>
    </a>
    <div class="header-links">
        <a href="/feeds" style="margin-left: 20px;">feeds</a>
        <button class="theme-toggle" onclick={darkMode.toggle} aria-label="Toggle theme">
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
        </button>
    </div>
</header>