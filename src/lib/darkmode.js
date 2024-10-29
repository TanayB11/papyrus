import { writable } from 'svelte/store';

function createDarkModeStore() {
    const { subscribe, set, update } = writable(false);

    return {
        subscribe,
        toggle: () => {
            update(darkMode => {
                const newValue = !darkMode;
                document.documentElement.classList.toggle('dark', newValue);
                localStorage.setItem('darkMode', newValue.toString());
                return newValue;
            });
        },
        init: () => {
            const savedMode = localStorage.getItem('darkMode');
            const initialValue = savedMode === 'true' || 
                (savedMode === null && 
                window.matchMedia && 
                window.matchMedia('(prefers-color-scheme: dark)').matches);
            
            document.documentElement.classList.toggle('dark', initialValue);
            set(initialValue);
        }
    };
}

export const darkMode = createDarkModeStore();