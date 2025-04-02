// Enhanced online-status.js with Work-Life Balance features
// This updates your existing static/js/online-status.js file

let onlineStatusEnabled = false;
let statusUpdateInterval = null;
let afkModeEnabled = false;
let afkTimeout = 30 * 60 * 1000; // Default 30 minutes
let afkTimeoutId = null;
let breakReminderInterval = null;
let breakFrequency = 60 * 60 * 1000; // Default 60 minutes
let workingHoursVisible = true;
let awayMessage = "Away from keyboard, will respond later...";
let userStatus = 'active';

document.addEventListener('DOMContentLoaded', function() {
    // Only run if user is authenticated
    if (!document.querySelector('meta[name="user-authenticated"]')) return;
    
    // Fetch user preferences first before enabling tracking
    fetchUserPreferences();
});

function fetchUserPreferences() {
    fetch('/api/user/work_life_balance_preferences/')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Update settings from preferences
            onlineStatusEnabled = data.show_online_status;
            afkModeEnabled = data.away_mode;
            afkTimeout = data.auto_away_after * 60 * 1000; // Convert minutes to milliseconds
            workingHoursVisible = data.share_working_hours;
            awayMessage = data.away_message || awayMessage;
            breakFrequency = data.break_frequency * 60 * 1000; // Convert minutes to milliseconds
            
            if (onlineStatusEnabled) {
                setupOnlineTracking();
                console.log('Online status tracking enabled');
            }
            
            if (afkModeEnabled) {
                setupAfkTracking();
                console.log('AFK mode enabled');
            }

            // Set up break reminders if enabled
            if (data.break_frequency > 0) {
                setupBreakReminders(data.break_frequency);
                console.log('Break reminders enabled every', data.break_frequency, 'minutes');
            }
            
            // Check if current time is within work hours
            if (workingHoursVisible) {
                checkWorkingHours();
            }
        })
        .catch(error => {
            console.error('Error fetching work-life balance preferences:', error);
            // Still enable basic online status
            if (onlineStatusEnabled) {
                setupOnlineTracking();
            }
        });
}

function setupOnlineTracking() {
    // Set up activity tracking
    let lastActivity = new Date();
    
    // Update last activity timestamp on user actions
    const updateActivity = () => {
        lastActivity = new Date();
        
        // If status was away, set back to active if we're not in AFK mode
        if (userStatus !== 'active' && (!afkModeEnabled || userStatus !== 'afk')) {
            userStatus = 'active';
            updateStatusOnServer('active');
        }
        
        // Reset AFK timeout if enabled
        if (afkModeEnabled && afkTimeoutId) {
            clearTimeout(afkTimeoutId);
            startAfkTimer();
        }
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
            userStatus = 'away';
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

function setupAfkTracking() {
    // Start AFK timer
    startAfkTimer();
    
    // Display indicator in UI
    addAfkIndicator();
}

function startAfkTimer() {
    // Clear any existing timeout
    if (afkTimeoutId) {
        clearTimeout(afkTimeoutId);
    }
    
    // Set new timeout
    afkTimeoutId = setTimeout(() => {
        // Set status to AFK
        userStatus = 'afk';
        updateStatusOnServer('afk', awayMessage);
        
        // Update UI indicator
        updateAfkIndicator(true);
        
        // Show notification to user
        if (Notification.permission === 'granted') {
            new Notification('Away From Keyboard', {
                body: 'Your status has been set to away. Click to set as active again.',
                icon: '/static/img/logo.png'
            });
        }
    }, afkTimeout);
}

function updateStatusOnServer(status, message = null) {
    if (!onlineStatusEnabled && status !== 'offline') return;
    
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    
    const payload = { status: status };
    if (message) {
        payload.message = message;
    }
    
    fetch('/api/user/online-status/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(payload)
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
            // Don't change afk status through this interval
            if (userStatus !== 'afk') {
                updateStatusOnServer('active');
            }
        }
    }, 5 * 60 * 1000);
}

function addAfkIndicator() {
    // Create an indicator in the navbar if it doesn't exist
    if (!document.getElementById('afk-indicator')) {
        const navbar = document.querySelector('.navbar-nav');
        if (navbar) {
            const indicator = document.createElement('li');
            indicator.className = 'nav-item';
            indicator.id = 'afk-indicator';
            indicator.innerHTML = `
                <span class="nav-link">
                    <i class="fas fa-user-clock"></i>
                    <span class="afk-status">AFK: Off</span>
                </span>
            `;
            navbar.appendChild(indicator);
            
            // Add click handler to manually toggle AFK
            indicator.addEventListener('click', toggleAfkStatus);
        }
    }
}

function updateAfkIndicator(isAfk) {
    const indicator = document.getElementById('afk-indicator');
    if (indicator) {
        const statusText = indicator.querySelector('.afk-status');
        if (statusText) {
            statusText.textContent = isAfk ? 'AFK: On' : 'AFK: Off';
        }
        
        // Update icon
        const icon = indicator.querySelector('i');
        if (icon) {
            icon.className = isAfk ? 'fas fa-user-clock text-warning' : 'fas fa-user-clock';
        }
    }
}

function toggleAfkStatus() {
    if (userStatus === 'afk') {
        // Turn off AFK
        userStatus = 'active';
        updateStatusOnServer('active');
        updateAfkIndicator(false);
        startAfkTimer(); // Restart the timer
    } else {
        // Turn on AFK
        userStatus = 'afk';
        updateStatusOnServer('afk', awayMessage);
        updateAfkIndicator(true);
        
        // Don't start timer again since we manually activated AFK
        if (afkTimeoutId) {
            clearTimeout(afkTimeoutId);
            afkTimeoutId = null;
        }
    }
}

function setupBreakReminders(frequency) {
    // Clear any existing interval
    if (breakReminderInterval) {
        clearInterval(breakReminderInterval);
    }
    
    // Calculate milliseconds
    const intervalMs = frequency * 60 * 1000;
    
    // Set interval for break reminders
    breakReminderInterval = setInterval(() => {
        // Only show reminder if user is active and page is visible
        if (document.visibilityState === 'visible' && userStatus === 'active') {
            showBreakReminder();
        }
    }, intervalMs);
    
    console.log(`Break reminders set for every ${frequency} minutes`);
}

function showBreakReminder() {
    // First check if we're within working hours
    if (!isWithinWorkingHours()) {
        return; // Don't show reminders outside work hours
    }
    
    // Create or get break reminder element
    let reminderEl = document.getElementById('break-reminder');
    if (!reminderEl) {
        reminderEl = document.createElement('div');
        reminderEl.id = 'break-reminder';
        reminderEl.className = 'break-reminder';
        reminderEl.innerHTML = `
            <div class="break-reminder-content">
                <h5><i class="fas fa-coffee"></i> Time for a break!</h5>
                <p>You've been working for a while. Take a short 5-minute break to rest your eyes and stretch.</p>
                <div class="break-reminder-actions">
                    <button class="btn btn-primary btn-sm take-break-btn">Take a break now</button>
                    <button class="btn btn-secondary btn-sm dismiss-btn">Dismiss</button>
                </div>
            </div>
        `;
        document.body.appendChild(reminderEl);
        
        // Add event listeners to buttons
        reminderEl.querySelector('.take-break-btn').addEventListener('click', () => {
            takeBreak();
            hideBreakReminder();
        });
        
        reminderEl.querySelector('.dismiss-btn').addEventListener('click', () => {
            hideBreakReminder();
        });
        
        // Add styles to break reminder
        const style = document.createElement('style');
        style.textContent = `
            .break-reminder {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 1000;
                max-width: 320px;
                opacity: 0;
                transform: translateY(20px);
                transition: opacity 0.3s, transform 0.3s;
            }
            .break-reminder.show {
                opacity: 1;
                transform: translateY(0);
            }
            .break-reminder-content {
                padding: 15px;
            }
            .break-reminder-actions {
                display: flex;
                justify-content: space-between;
                margin-top: 10px;
            }
        `;
        document.head.appendChild(style);
    }
    
    // Show the reminder
    setTimeout(() => {
        reminderEl.classList.add('show');
    }, 100);
    
    // Play sound (optional)
    const audio = new Audio('/static/sounds/notification.mp3');
    audio.play().catch(e => console.log('Could not play break reminder sound'));
    
    // Show browser notification
    if (Notification.permission === 'granted') {
        new Notification('Time for a break!', {
            body: 'You\'ve been working for a while. Take a short 5-minute break to rest your eyes and stretch.',
            icon: '/static/img/logo.png'
        });
    }
}

function hideBreakReminder() {
    const reminderEl = document.getElementById('break-reminder');
    if (reminderEl) {
        reminderEl.classList.remove('show');
    }
}

function takeBreak() {
    // Set status to break
    userStatus = 'break';
    updateStatusOnServer('break', 'Taking a break, back in 5 minutes');
    
    // Update AFK indicator if it exists
    const indicator = document.getElementById('afk-indicator');
    if (indicator) {
        const statusText = indicator.querySelector('.afk-status');
        if (statusText) {
            statusText.textContent = 'On Break';
        }
        
        // Update icon
        const icon = indicator.querySelector('i');
        if (icon) {
            icon.className = 'fas fa-coffee text-info';
        }
    }
    
    // After 5 minutes, set back to active if user hasn't interacted
    setTimeout(() => {
        if (userStatus === 'break') {
            userStatus = 'active';
            updateStatusOnServer('active');
            updateAfkIndicator(false);
        }
    }, 5 * 60 * 1000);
}

function checkWorkingHours() {
    // Update status based on working hours
    if (!isWithinWorkingHours()) {
        if (userStatus === 'active') {
            userStatus = 'outside-hours';
            updateStatusOnServer('outside-hours', 'Outside working hours');
        }
    } else if (userStatus === 'outside-hours') {
        userStatus = 'active';
        updateStatusOnServer('active');
    }
    
    // Check every minute
    setTimeout(checkWorkingHours, 60 * 1000);
}

function isWithinWorkingHours() {
    const now = new Date();
    const day = now.getDay(); // 0 is Sunday, 1 is Monday, etc.
    const time = now.getHours() * 60 + now.getMinutes(); // Current time in minutes since midnight
    
    // Get working hours from meta tags (assuming they are added to the template)
    const workDays = document.querySelector('meta[name="work-days"]')?.getAttribute('content') || '12345'; // Default Mon-Fri
    const workStartStr = document.querySelector('meta[name="work-start-time"]')?.getAttribute('content') || '09:00';
    const workEndStr = document.querySelector('meta[name="work-end-time"]')?.getAttribute('content') || '17:00';
    
    // Convert Sunday (0) to our format (7)
    const adjustedDay = day === 0 ? 7 : day;
    
    // Parse work days
    const workDaysArray = workDays.split('').map(Number);
    
    // Parse work hours
    const [startHours, startMinutes] = workStartStr.split(':').map(Number);
    const [endHours, endMinutes] = workEndStr.split(':').map(Number);
    
    const workStart = startHours * 60 + startMinutes;
    const workEnd = endHours * 60 + endMinutes;
    
    // Check if current day is a work day
    if (!workDaysArray.includes(adjustedDay)) {
        return false;
    }
    
    // Handle spanning midnight (when start time is after end time)
    if (workStart > workEnd) {
        return time >= workStart || time <= workEnd;
    } else {
        return time >= workStart && time <= workEnd;
    }
}

// Export functions for use in other modules
window.workLifeBalance = {
    toggleAfkStatus,
    takeBreak,
    showBreakReminder
};

document.addEventListener('DOMContentLoaded', function() {
    // Set up additional AFK toggle buttons if they exist
    const toggleAfkButtons = document.querySelectorAll('.toggle-afk-btn');
    
    if (toggleAfkButtons.length > 0) {
        toggleAfkButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                // Use the existing function
                toggleAfkStatus();
                console.log('AFK status toggled via button');
            });
        });
    }
    
    // Make sure the AFK status is reflected correctly on page load
    if (typeof userStatus !== 'undefined' && userStatus === 'afk') {
        updateAfkIndicator(true);
    }
    
    // Expose the toggle function globally for easier access
    if (typeof window.workLifeBalance !== 'undefined') {
        // Function is already exposed via window.workLifeBalance.toggleAfkStatus
        console.log('AFK toggle function available via window.workLifeBalance.toggleAfkStatus');
    } else {
        // As fallback, expose directly
        window.toggleAfkStatus = toggleAfkStatus;
        console.log('AFK toggle function exposed directly via window.toggleAfkStatus');
    }
});