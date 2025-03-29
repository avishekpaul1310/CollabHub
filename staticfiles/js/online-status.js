// Add this to static/js/online-status.js

// Online status tracking
let onlineStatusEnabled = false;

document.addEventListener('DOMContentLoaded', function() {
    // Check if user has enabled online status
    fetch('/api/user/preferences/online-status/')
        .then(response => response.json())
        .then(data => {
            onlineStatusEnabled = data.show_online_status;
            
            if (onlineStatusEnabled) {
                // Initialize online status tracking
                setupOnlineTracking();
            } else {
                // Hide any online status indicators
                document.querySelectorAll('.online-status-indicator').forEach(indicator => {
                    indicator.style.display = 'none';
                });
            }
        })
        .catch(error => {
            console.error('Error checking online status preferences:', error);
        });
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
        
        // Set status to active
        updateOnlineStatus('active');
        
        // Set timeout to check inactivity after 5 minutes
        activityTimeout = setTimeout(() => {
            // If no activity for 5 minutes, set to away
            const inactiveTime = (new Date() - lastActivity) / 1000 / 60; // in minutes
            
            if (inactiveTime >= 5) {
                updateOnlineStatus('away');
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
            updateOnlineStatus('away');
        }
    });
    
    // Handle page unload
    window.addEventListener('beforeunload', () => {
        updateOnlineStatus('offline');
    });
}

function updateOnlineStatus(status) {
    if (!onlineStatusEnabled) return;
    
    // Send status update to server
    fetch('/api/user/online-status/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ status })
    })
    .catch(error => {
        console.error('Error updating online status:', error);
    });
}

// Helper function to get CSRF token
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}