
document.addEventListener('DOMContentLoaded', function() {
    // Only run on thread detail pages
    const messagesContainer = document.getElementById('messages-list');
    if (!messagesContainer) return;
    
    // Set up intersection observer to detect when messages are visible
    setupMessageReadTracking();
    
    // Set up read receipt popups
    setupReadReceiptPopups();
});

function setupMessageReadTracking() {
    // Only track messages if the user is logged in
    if (!userId) return;
    
    // Track which messages we've already marked as read
    const readMessages = new Set();
    
    // Create an intersection observer
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const messageElement = entry.target;
                const messageId = messageElement.getAttribute('data-message-id');
                
                // Skip if already marked as read
                if (readMessages.has(messageId)) return;
                
                // Mark as read
                markMessageRead(messageId);
                readMessages.add(messageId);
            }
        });
    }, {
        root: null, // viewport
        threshold: 0.5 // 50% visible
    });
    
    // Observe all message elements
    document.querySelectorAll('.message-container').forEach(message => {
        const messageId = message.getAttribute('data-message-id');
        if (messageId) {
            observer.observe(message);
        }
    });
    
    // Also include replies
    document.querySelectorAll('.reply').forEach(reply => {
        const messageId = reply.getAttribute('data-message-id');
        if (messageId) {
            observer.observe(reply);
        }
    });
}

function markMessageRead(messageId) {
    // Skip if no message ID
    if (!messageId) return;
    
    fetch(`/api/message/${messageId}/mark-read/`, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        console.log(`Message ${messageId} marked as read:`, data);
    })
    .catch(error => {
        console.error(`Error marking message ${messageId} as read:`, error);
    });
}

function setupReadReceiptPopups() {
    // Only run for sent messages
    const readReceiptIcons = document.querySelectorAll('.read-receipt-icon');
    
    readReceiptIcons.forEach(icon => {
        const messageId = icon.getAttribute('data-message-id');
        const popoverId = `read-receipt-popover-${messageId}`;
        
        // Create popover element if not exists
        let popover = document.getElementById(popoverId);
        if (!popover) {
            popover = document.createElement('div');
            popover.id = popoverId;
            popover.className = 'read-receipt-popover popover fade';
            popover.setAttribute('role', 'tooltip');
            
            // Add arrow and content
            popover.innerHTML = `
                <div class="popover-arrow"></div>
                <h3 class="popover-header">Read Status</h3>
                <div class="popover-body">
                    <div class="read-receipt-loading">
                        <div class="spinner-border spinner-border-sm" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <span class="ms-2">Loading...</span>
                    </div>
                    <div class="read-receipt-content" style="display: none;">
                        <div class="read-by-list"></div>
                        <div class="read-pending-list"></div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(popover);
        }
        
        // Initialize Bootstrap popover
        const bsPopover = new bootstrap.Popover(icon, {
            container: 'body',
            trigger: 'click',
            html: true,
            content: popover,
            placement: 'left'
        });
        
        // Load read status when popover is shown
        icon.addEventListener('shown.bs.popover', function() {
            loadReadStatus(messageId, popover);
        });
    });
}

function loadReadStatus(messageId, popoverElement) {
    const loadingElement = popoverElement.querySelector('.read-receipt-loading');
    const contentElement = popoverElement.querySelector('.read-receipt-content');
    const readByList = popoverElement.querySelector('.read-by-list');
    const pendingList = popoverElement.querySelector('.read-pending-list');
    
    // Show loading, hide content
    loadingElement.style.display = 'flex';
    contentElement.style.display = 'none';
    
    fetch(`/api/message/${messageId}/read-status/`)
    .then(response => response.json())
    .then(data => {
        // Hide loading, show content
        loadingElement.style.display = 'none';
        contentElement.style.display = 'block';
        
        // Clear previous content
        readByList.innerHTML = '';
        pendingList.innerHTML = '';
        
        // Show read users
        if (data.read_by && data.read_by.length > 0) {
            const readByHeader = document.createElement('h6');
            readByHeader.className = 'mb-2 text-success';
            readByHeader.innerHTML = '<i class="fas fa-check-circle"></i> Read by:';
            readByList.appendChild(readByHeader);
            
            const readByUl = document.createElement('ul');
            readByUl.className = 'list-unstyled mb-3';
            
            data.read_by.forEach(user => {
                const readDate = new Date(user.read_at);
                const readByItem = document.createElement('li');
                readByItem.className = 'small';
                readByItem.innerHTML = `
                    ${user.username} 
                    <span class="text-muted">${readDate.toLocaleString()}</span>
                `;
                readByUl.appendChild(readByItem);
            });
            
            readByList.appendChild(readByUl);
        } else {
            readByList.innerHTML = '<p class="text-muted small">No one has read this message yet.</p>';
        }
        
        // Show pending users
        if (data.pending && data.pending.length > 0) {
            const pendingHeader = document.createElement('h6');
            pendingHeader.className = 'mb-2 text-muted';
            pendingHeader.innerHTML = '<i class="fas fa-clock"></i> Not read yet:';
            pendingList.appendChild(pendingHeader);
            
            const pendingUl = document.createElement('ul');
            pendingUl.className = 'list-unstyled mb-0';
            
            data.pending.forEach(user => {
                const pendingItem = document.createElement('li');
                pendingItem.className = 'small text-muted';
                pendingItem.textContent = user.username;
                pendingUl.appendChild(pendingItem);
            });
            
            pendingList.appendChild(pendingUl);
        }
        
        // Add a message about asynchronous communication
        const asyncMessage = document.createElement('div');
        asyncMessage.className = 'mt-3 text-muted small fst-italic';
        asyncMessage.innerHTML = 'Remember: Not everyone is online at the same time. Asynchronous communication is key to thoughtful collaboration.';
        contentElement.appendChild(asyncMessage);
    })
    .catch(error => {
        console.error(`Error loading read status for message ${messageId}:`, error);
        contentElement.innerHTML = '<div class="text-danger">Error loading read status.</div>';
        contentElement.style.display = 'block';
        loadingElement.style.display = 'none';
    });
}

// Helper function to get CSRF token
function getCsrfToken() {
    return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
}