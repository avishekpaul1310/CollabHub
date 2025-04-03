/**
 * AFK Mode Toggle Handler
 * Handles the Away From Keyboard mode toggle functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Find the AFK mode toggle button - FIXED SELECTOR
    const afkToggleBtn = document.getElementById('toggle-afk-mode');
    if (!afkToggleBtn) return;
    
    // Initialize the button state based on current AFK status
    updateAfkButtonState();
    
    // Add click handler to toggle AFK mode
    afkToggleBtn.addEventListener('click', function(e) {
        e.preventDefault();
        toggleAfkMode();
    });
    
    // Function to toggle AFK mode
    function toggleAfkMode() {
        // If window.workLifeBalance exists, use its methods
        if (window.workLifeBalance && typeof window.workLifeBalance.toggleAfkStatus === 'function') {
            window.workLifeBalance.toggleAfkStatus();
            return;
        }
        
        // Fallback implementation
        const isCurrentlyAfk = localStorage.getItem('userAfkMode') === 'true';
        const newAfkState = !isCurrentlyAfk;
        
        // Update local storage
        localStorage.setItem('userAfkMode', newAfkState);
        
        // Update UI
        updateAfkButtonState();
        
        // Send state to server
        sendAfkStateToServer(newAfkState);
        
        // Show notification
        if (newAfkState) {
            showNotification('AFK mode enabled', 'Your status is now set to Away From Keyboard');
        } else {
            showNotification('AFK mode disabled', 'Your status is now set to Active');
        }
    }
    
    // Update button state based on current AFK status
    function updateAfkButtonState() {
        const isAfk = localStorage.getItem('userAfkMode') === 'true';
        
        if (!afkToggleBtn) return;
        
        if (isAfk) {
            afkToggleBtn.innerHTML = '<i class="fas fa-user-clock fa-fw"></i> Disable AFK Mode';
        } else {
            afkToggleBtn.innerHTML = '<i class="fas fa-user-clock fa-fw"></i> Toggle AFK Mode';
        }
    }
    
    // Send AFK state to server
    function sendAfkStateToServer(isAfk) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        
        fetch('/api/user/update_afk_status/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                afk_mode: isAfk
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            console.log('AFK status updated:', data);
        })
        .catch(error => {
            console.error('Error updating AFK status:', error);
        });
    }
    
    // Show notification to user
    function showNotification(title, message) {
        // Try to play notification sound
        if (window.playNotificationSound) {
            window.playNotificationSound();
        }
        
        // Show browser notification if permitted
        if (Notification.permission === 'granted') {
            new Notification(title, {
                body: message,
                icon: '/static/img/logo.png'
            });
        }
    }
});
