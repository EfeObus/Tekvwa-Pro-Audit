/* Tekvwa Pro Audit - Main JavaScript */

// HTMX Configuration
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Add CSRF token to all HTMX requests
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (csrfToken) {
        evt.detail.headers['X-CSRF-Token'] = csrfToken;
    }
});

// Handle HTMX errors
document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX Error:', evt.detail);
    // Show error notification
    showNotification('An error occurred. Please try again.', 'error');
});

// Notification system
function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container') || createNotificationContainer();
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type} p-4 mb-2 rounded-md shadow-lg`;
    notification.textContent = message;
    
    container.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

function createNotificationContainer() {
    const container = document.createElement('div');
    container.id = 'notification-container';
    container.className = 'fixed top-4 right-4 z-50 space-y-2';
    document.body.appendChild(container);
    return container;
}

// Format currency (Nigerian Naira)
function formatNaira(amount) {
    return new Intl.NumberFormat('en-NG', {
        style: 'currency',
        currency: 'NGN'
    }).format(amount);
}

// Format date
function formatDate(dateString) {
    return new Intl.DateTimeFormat('en-NG', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    }).format(new Date(dateString));
}

// Alpine.js global data
document.addEventListener('alpine:init', () => {
    Alpine.store('app', {
        sidebarOpen: true,
        toggleSidebar() {
            this.sidebarOpen = !this.sidebarOpen;
        }
    });
});

console.log('Tekvwa Pro Audit initialized');
