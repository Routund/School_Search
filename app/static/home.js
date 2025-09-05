document.addEventListener("DOMContentLoaded", function() {
    // Find the container element
    const container = document.getElementById('g_id_onload');
    if (container) {
        // Show the container after the page has loaded
        container.style.visibility = 'visible';
    }
    const button = document.getElementById('gsi');
    if (button) {
        // Show the container after the page has loaded
        button.style.visibility = 'visible';
    }
});