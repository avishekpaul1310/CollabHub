// Online status tracking
let onlineStatusEnabled = false;
let statusUpdateInterval = null;
const ACTIVITY_TIMEOUT = 5 * 60 * 1000; // 5 minutes

document.addEventListener('DOMContentLoaded', function() {
    // Only run if user is authenticated
    if (!document.querySelector('meta[name="user-authenticated"]')) return;
    
    // Check user preferences first before enabling tracking
    checkOnlineStatusPreference();
});

function checkOnlineStatusPreference() {
    fetch('/api/user/preferences/online-status/')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            onlineStatusEnabled = data.show_online_status;
            
            if (onlineStatusEnabled) {
                setupOnlineTracking();
                console.log('Online status tracking enabled');
            } else {
                console.log('Online status tracking disabled by user preference');
            }
        })
        .catch(error => {
            console.error('Error checking online status preference:', error);
        });
}

function setupOnlineTracking() {
    // Set up activity tracking
    let lastActivity = new Date();
    let currentStatus = 'active';
    let activityTimeout;
    
    // Update last activity timestamp on user actions
    const updateActivity = () => {
        lastActivity = new Date();
        
        // If status was away, set back to active
        if (currentStatus !== 'active') {
            currentStatus = 'active';
            updateStatusOnServer('active');
        }
        
        // Clear any existing timeout
        if (activityTimeout) {
            clearTimeout(activityTimeout);
        }
        
        // Set timeout to check inactivity after defined timeout period
        activityTimeout = setTimeout(() => {
            // If no activity for timeout period, set to away
            const inactiveTime = (new Date() - lastActivity);
            
            if (inactiveTime >= ACTIVITY_TIMEOUT) {
                currentStatus = 'away';
                updateStatusOnServer('away');
            }
        }, ACTIVITY_TIMEOUT);
    };
    
    // Track user activity
    ['mousemove', 'keypress', 'click', 'scroll', 'touchstart'].forEach(event => {
        document.addEventListener(event, _.debounce(updateActivity, 2000), { passive: true });
    });
    
    // Initialize as active
    updateActivity();
    
    // Update status on page visibility changes
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            updateActivity();
        } else {
            currentStatus = 'away';
            updateStatusOnServer('away');
        }
    });
    
    // Handle page unload
    window.addEventListener('beforeunload', () => {
        // Use sendBeacon for more reliable delivery during page unload
        if (navigator.sendBeacon) {
            const data = JSON.stringify({ status: 'offline' });
            navigator.sendBeacon('/api/user/online-status/', data);
        } else {
            // Fallback method
            updateStatusOnServer('offline');
        }
    });
    
    // Start periodic status update to keep session alive
    startStatusUpdateInterval();
}

function updateStatusOnServer(status) {
    if (!onlineStatusEnabled) return;
    
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    
    fetch('/api/user/online-status/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ status: status })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Status updated:', data);
    })
    .catch(error => {
        console.error('Error updating online status:', error);
    });
}

function startStatusUpdateInterval() {
    // Clear any existing interval
    if (statusUpdateInterval) {
        clearInterval(statusUpdateInterval);
    }
    
    // Update status every 5 minutes to keep it active
    statusUpdateInterval = setInterval(() => {
        if (document.visibilityState === 'visible' && onlineStatusEnabled) {
            updateStatusOnServer('active');
        }
    }, 5 * 60 * 1000);
}