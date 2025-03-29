// Online status tracking
let onlineStatusEnabled = false;

document.addEventListener('DOMContentLoaded', function() {
    // For now, just initialize without checking the server
    // In production, this would check user preferences
    setupOnlineTracking();
});

function setupOnlineTracking() {
    // Only run if user is authenticated
    if (!document.querySelector('meta[name="user-authenticated"]')) return;
    
    // Set up activity tracking
    let lastActivity = new Date();
    let activityTimeout;
    
    // Update last activity timestamp on user actions
    const updateActivity = () => {
        lastActivity = new Date();
        
        // Clear any existing timeout
        if (activityTimeout) {
            clearTimeout(activityTimeout);
        }
        
        // Set status to active (in a real app, we'd update the server)
        console.log('User activity detected, status: active');
        
        // Set timeout to check inactivity after 5 minutes
        activityTimeout = setTimeout(() => {
            // If no activity for 5 minutes, set to away
            const inactiveTime = (new Date() - lastActivity) / 1000 / 60; // in minutes
            
            if (inactiveTime >= 5) {
                console.log('User inactive for 5+ minutes, status: away');
            }
        }, 5 * 60 * 1000); // 5 minutes
    };
    
    // Track user activity
    ['mousemove', 'keypress', 'click', 'scroll'].forEach(event => {
        document.addEventListener(event, updateActivity, { passive: true });
    });
    
    // Initialize as active
    updateActivity();
    
    // Update status on page visibility changes
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            updateActivity();
        } else {
            console.log('Page not visible, status: away');
        }
    });
    
    // Handle page unload
    window.addEventListener('beforeunload', () => {
        console.log('Page unloading, status: offline');
    });
}