// break-reminder.js - Add this to your static/js/ directory

class BreakReminderService {
    constructor() {
        this.isEnabled = false;
        this.frequency = 60; // Default: 60 minutes
        this.reminderInterval = null;
        this.lastBreakTime = new Date();
        this.notificationsEnabled = false;
        this.breakDuration = 5; // Default: 5 minutes
        this.breakHistory = [];
        this.nextBreakTime = null;
        this.breakNotificationAudio = new Audio('/static/sounds/break-reminder.mp3');
    }
    
    init() {
        // Use a more robust initialization pattern to prevent undefined errors
        const settings = (window.workLifeBalance && window.workLifeBalance.breakSettings) || {
            enabled: true,
            frequency: 60,
            breakDuration: 5
        };
        
        // Apply settings
        this.updateSettings(settings);
        
        // If we didn't get settings from window.workLifeBalance.breakSettings, fetch from server
        if (!(window.workLifeBalance && window.workLifeBalance.breakSettings)) {
            this.fetchSettings();
        }
        
        // Request notification permission
        this.requestNotificationPermission();
        
        // Set up event listeners for break actions
        this.setupEventListeners();
        
        // Add break progress indicator to the UI
        this.addBreakIndicator();
    }
    
    updateSettings(settings) {
        this.isEnabled = settings.enabled !== false;
        this.frequency = settings.frequency || 60;
        this.breakDuration = settings.breakDuration || 5;
        
        // Clear existing interval
        if (this.reminderInterval) {
            clearInterval(this.reminderInterval);
            this.reminderInterval = null;
        }
        
        // Start new interval if enabled
        if (this.isEnabled) {
            this.startReminders();
            console.log(`Break reminders enabled: every ${this.frequency} minutes`);
        }
    }
    
    fetchSettings() {
        fetch('/api/user/work_life_balance_preferences/')
            .then(response => response.json())
            .then(data => {
                // Check either for success status or direct break_frequency property
                if ((data.status === 'success' && data.break_frequency) || data.break_frequency) {
                    this.updateSettings({
                        enabled: true,
                        frequency: data.break_frequency,
                        breakDuration: data.break_duration || 5
                    });
                }
            })
            .catch(error => {
                console.error('Error fetching break reminder settings:', error);
                
                // Use defaults
                this.updateSettings({
                    enabled: true,
                    frequency: 60,
                    breakDuration: 5
                });
            });
    }
    
    requestNotificationPermission() {
        if (!("Notification" in window)) {
            console.log("This browser does not support notifications");
            return;
        }
        
        if (Notification.permission === "granted") {
            this.notificationsEnabled = true;
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(permission => {
                this.notificationsEnabled = permission === "granted";
            });
        }
    }
    
    startReminders() {
        // Calculate when the next break should be
        const now = new Date();
        const minutesSinceLastBreak = Math.floor((now - this.lastBreakTime) / (1000 * 60));
        const minutesUntilNextBreak = Math.max(this.frequency - minutesSinceLastBreak, 0);
        
        // Update next break time
        this.nextBreakTime = new Date(now.getTime() + minutesUntilNextBreak * 60 * 1000);
        
        // Update the progress indicator
        this.updateBreakProgress();
        
        // Set interval to show the reminder
        this.reminderInterval = setInterval(() => {
            // Check if it's time for a break
            const currentTime = new Date();
            const currentMinutesSinceLastBreak = Math.floor((currentTime - this.lastBreakTime) / (1000 * 60));
            
            if (currentMinutesSinceLastBreak >= this.frequency) {
                this.showBreakReminder();
            }
            
            // Update the progress indicator every minute
            this.updateBreakProgress();
        }, 60 * 1000); // Check every minute
        
        // Initial check in case a break is already due
        const currentTime = new Date();
        const initialMinutesSinceLastBreak = Math.floor((currentTime - this.lastBreakTime) / (1000 * 60));
        
        if (initialMinutesSinceLastBreak >= this.frequency) {
            this.showBreakReminder();
        }
    }
    
    showBreakReminder() {
        // Only show if user is active and page is visible
        if (document.visibilityState !== 'visible' || 
            (window.userStatus && window.userStatus !== 'active')) {
            return;
        }
        
        // Create or get reminder element
        let reminderEl = document.getElementById('break-reminder');
        if (!reminderEl) {
            reminderEl = document.createElement('div');
            reminderEl.id = 'break-reminder';
            reminderEl.className = 'break-reminder';
            reminderEl.innerHTML = `
                <div class="break-reminder-content">
                    <h5><i class="fas fa-coffee"></i> Time for a break!</h5>
                    <p>You've been working for ${this.frequency} minutes. Taking regular breaks helps maintain productivity and reduces eye strain.</p>
                    <div class="break-timer">
                        <span id="break-time-remaining">5:00</span> remaining
                    </div>
                    <div class="break-reminder-actions">
                        <button class="btn btn-primary btn-sm take-break-btn">Start Break</button>
                        <button class="btn btn-outline-secondary btn-sm snooze-btn">Snooze 10 min</button>
                        <button class="btn btn-outline-secondary btn-sm dismiss-btn">Skip</button>
                    </div>
                </div>
            `;
            document.body.appendChild(reminderEl);
            
            // Add event listeners
            reminderEl.querySelector('.take-break-btn').addEventListener('click', () => {
                this.startBreak();
            });
            
            reminderEl.querySelector('.snooze-btn').addEventListener('click', () => {
                this.snoozeBreak();
            });
            
            reminderEl.querySelector('.dismiss-btn').addEventListener('click', () => {
                this.dismissBreak();
            });
            
            // Add styles
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
                .break-timer {
                    text-align: center;
                    margin: 10px 0;
                    font-size: 1.2rem;
                    font-weight: bold;
                }
                .break-reminder-actions {
                    display: flex;
                    justify-content: space-between;
                    margin-top: 10px;
                }
                .break-progress {
                    position: fixed;
                    bottom: 10px;
                    left: 10px;
                    background: white;
                    border-radius: 4px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    padding: 5px 10px;
                    font-size: 12px;
                    cursor: pointer;
                    z-index: 900;
                    display: flex;
                    align-items: center;
                }
                .break-progress-bar {
                    width: 100px;
                    height: 6px;
                    background: #e9ecef;
                    border-radius: 3px;
                    margin-left: 10px;
                    overflow: hidden;
                }
                .break-progress-fill {
                    height: 100%;
                    background: #4a6fdc;
                    width: 0%;
                    transition: width 1s linear;
                }
                .taking-break .break-progress-fill {
                    background: #28a745;
                }
            `;
            document.head.appendChild(style);
        }
        
        // Play sound
        if (this.breakNotificationAudio) {
            this.breakNotificationAudio.play().catch(e => console.log('Could not play break reminder sound'));
        }
        
        // Show the reminder
        setTimeout(() => {
            reminderEl.classList.add('show');
        }, 100);
        
        // Show browser notification
        if (this.notificationsEnabled) {
            const notification = new Notification('Time for a break!', {
                body: `You've been working for ${this.frequency} minutes. Taking regular breaks helps reduce eye strain and fatigue.`,
                icon: '/static/img/logo.png'
            });
            
            // Close notification after 10 seconds
            setTimeout(() => notification.close(), 10000);
            
            // Focus window when notification is clicked
            notification.onclick = function() {
                window.focus();
                this.close();
            };
        }
    }
    
    startBreak() {
        // Update last break time
        this.lastBreakTime = new Date();
        
        // Hide reminder
        const reminderEl = document.getElementById('break-reminder');
        if (reminderEl) {
            reminderEl.classList.remove('show');
        }
        
        // Log break for analytics
        this.logBreak('taken');
        
        // Update user status if online status tracking is enabled
        if (window.updateStatusOnServer) {
            window.updateStatusOnServer('break', 'Taking a break, back soon');
        }
        
        // Add break timer to UI
        this.showBreakTimer();
        
        // Update break progress indicator
        this.updateBreakProgress(true);
        
        // Schedule next break
        this.nextBreakTime = new Date(this.lastBreakTime.getTime() + this.frequency * 60 * 1000);
    }
    
    snoozeBreak() {
        // Snooze for 10 minutes
        const snoozeTime = new Date();
        this.nextBreakTime = new Date(snoozeTime.getTime() + 10 * 60 * 1000);
        
        // Hide reminder
        const reminderEl = document.getElementById('break-reminder');
        if (reminderEl) {
            reminderEl.classList.remove('show');
        }
        
        // Log break for analytics
        this.logBreak('snoozed');
        
        // Update break progress
        this.updateBreakProgress();
    }
    
    dismissBreak() {
        // Update last break time so we don't immediately show another reminder
        this.lastBreakTime = new Date();
        
        // Hide reminder
        const reminderEl = document.getElementById('break-reminder');
        if (reminderEl) {
            reminderEl.classList.remove('show');
        }
        
        // Log break for analytics
        this.logBreak('skipped');
        
        // Schedule next break
        this.nextBreakTime = new Date(this.lastBreakTime.getTime() + this.frequency * 60 * 1000);
        
        // Update break progress
        this.updateBreakProgress();
    }
    
    showBreakTimer() {
        // Create break timer overlay if it doesn't exist
        let timerEl = document.getElementById('break-timer-overlay');
        if (!timerEl) {
            timerEl = document.createElement('div');
            timerEl.id = 'break-timer-overlay';
            timerEl.className = 'break-timer-overlay';
            timerEl.innerHTML = `
                <div class="break-timer-content">
                    <h3><i class="fas fa-coffee"></i> Break Time</h3>
                    <div class="break-timer-countdown">
                        <span id="break-minutes">5</span>:<span id="break-seconds">00</span>
                    </div>
                    <p>Take a moment to rest your eyes, stretch, or get some water.</p>
                    <button class="btn btn-primary end-break-btn">End Break Early</button>
                </div>
            `;
            document.body.appendChild(timerEl);
            
            // Add event listener for end break button
            timerEl.querySelector('.end-break-btn').addEventListener('click', () => {
                this.endBreak();
            });
            
            // Add styles
            const style = document.createElement('style');
            style.textContent = `
                .break-timer-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0, 0, 0, 0.7);
                    z-index: 2000;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    opacity: 0;
                    transition: opacity 0.3s;
                }
                .break-timer-overlay.show {
                    opacity: 1;
                }
                .break-timer-content {
                    background: white;
                    border-radius: 8px;
                    padding: 30px;
                    text-align: center;
                    max-width: 400px;
                }
                .break-timer-countdown {
                    font-size: 3rem;
                    font-weight: bold;
                    margin: 20px 0;
                }
            `;
            document.head.appendChild(style);
        }
        
        // Show the timer
        setTimeout(() => {
            timerEl.classList.add('show');
        }, 100);
        
        // Start countdown
        let totalSeconds = this.breakDuration * 60;
        const countdownEl = document.getElementById('break-minutes');
        const secondsEl = document.getElementById('break-seconds');
        
        // Update initial display
        countdownEl.textContent = Math.floor(totalSeconds / 60);
        secondsEl.textContent = (totalSeconds % 60).toString().padStart(2, '0');
        
        // Set countdown interval
        const countdownInterval = setInterval(() => {
            totalSeconds--;
            
            if (totalSeconds <= 0) {
                // Break is over
                clearInterval(countdownInterval);
                this.endBreak();
                return;
            }
            
            // Update display
            countdownEl.textContent = Math.floor(totalSeconds / 60);
            secondsEl.textContent = (totalSeconds % 60).toString().padStart(2, '0');
        }, 1000);
        
        // Store interval ID for cleanup
        this.countdownInterval = countdownInterval;
    }
    
    endBreak() {
        // Clear countdown interval
        if (this.countdownInterval) {
            clearInterval(this.countdownInterval);
            this.countdownInterval = null;
        }
        
        // Hide timer overlay
        const timerEl = document.getElementById('break-timer-overlay');
        if (timerEl) {
            timerEl.classList.remove('show');
            setTimeout(() => {
                timerEl.remove();
            }, 300);
        }
        
        // Update user status back to active
        if (window.updateStatusOnServer) {
            window.updateStatusOnServer('active');
        }
        
        // Update break progress indicator
        this.updateBreakProgress();
        
        // Log break end
        this.logBreakEnd();
    }
    
    logBreak(action) {
        // Log break start for analytics
        const breakLog = {
            startTime: new Date().toISOString(),
            action: action,
            scheduled: true
        };
        
        this.currentBreak = breakLog;
        
        // In a real implementation, you might send this to the server
        console.log('Break started:', breakLog);
    }
    
    logBreakEnd() {
        if (!this.currentBreak) return;
        
        // Calculate break duration
        const endTime = new Date();
        const startTime = new Date(this.currentBreak.startTime);
        const durationMinutes = Math.round((endTime - startTime) / (1000 * 60));
        
        const breakLog = {
            ...this.currentBreak,
            endTime: endTime.toISOString(),
            durationMinutes: durationMinutes
        };
        
        // Add to break history
        this.breakHistory.push(breakLog);
        
        // Reset current break
        this.currentBreak = null;
        
        // In a real implementation, you might send this to the server
        console.log('Break ended:', breakLog);
    }
    
    addBreakIndicator() {
        // Create break progress indicator
        const indicator = document.createElement('div');
        indicator.className = 'break-progress';
        indicator.innerHTML = `
            <span>Next break:</span>
            <span id="next-break-time" class="ms-1">--:--</span>
            <div class="break-progress-bar ms-2">
                <div class="break-progress-fill" id="break-progress-fill"></div>
            </div>
        `;
        document.body.appendChild(indicator);
        
        // Add click handler to toggle more info
        indicator.addEventListener('click', () => {
            // Show break reminder manually
            window.workLifeBalance.showBreakReminder();
        });
    }
    
    updateBreakProgress(isTakingBreak = false) {
        const now = new Date();
        const nextBreakEl = document.getElementById('next-break-time');
        const progressFill = document.getElementById('break-progress-fill');
        const progressContainer = document.querySelector('.break-progress');
        
        if (!nextBreakEl || !progressFill || !progressContainer) return;
        
        if (isTakingBreak) {
            // Show break in progress
            nextBreakEl.textContent = 'In progress';
            progressContainer.classList.add('taking-break');
            progressFill.style.width = '100%';
            return;
        }
        
        // Remove break in progress style if present
        progressContainer.classList.remove('taking-break');
        
        if (!this.nextBreakTime) {
            nextBreakEl.textContent = '--:--';
            progressFill.style.width = '0%';
            return;
        }
        
        const timeUntilBreak = this.nextBreakTime - now;
        
        if (timeUntilBreak <= 0) {
            // Break is due now
            nextBreakEl.textContent = 'Now';
            progressFill.style.width = '100%';
            return;
        }
        
        // Format time until next break
        const minutesUntilBreak = Math.ceil(timeUntilBreak / (1000 * 60));
        
        if (minutesUntilBreak < 60) {
            nextBreakEl.textContent = `${minutesUntilBreak} min`;
        } else {
            const hours = Math.floor(minutesUntilBreak / 60);
            const minutes = minutesUntilBreak % 60;
            nextBreakEl.textContent = `${hours}h ${minutes}m`;
        }
        
        // Update progress bar
        const totalMinutes = this.frequency;
        const elapsedMinutes = totalMinutes - minutesUntilBreak;
        const progressPercentage = Math.min(100, Math.max(0, (elapsedMinutes / totalMinutes) * 100));
        progressFill.style.width = `${progressPercentage}%`;
    }
    
    setupEventListeners() {
        // Register this service with the global workLifeBalance object
        if (!window.workLifeBalance) {
            window.workLifeBalance = {};
        }
        
        window.workLifeBalance.breakReminder = this;
        window.workLifeBalance.showBreakReminder = () => this.showBreakReminder();
        window.workLifeBalance.startBreak = () => this.startBreak();
        window.workLifeBalance.endBreak = () => this.endBreak();
    }
}

// Initialize break reminder service when the page loads
document.addEventListener('DOMContentLoaded', function() {
    const breakReminder = new BreakReminderService();
    breakReminder.init();
});