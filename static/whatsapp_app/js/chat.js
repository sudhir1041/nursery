// whatsapp_app/static/whatsapp_app/js/chat.js

/**
 * Handles chat functionality using AJAX polling with enhanced duplicate checking.
 * Integrates with Django backend views and models for WhatsApp messaging.
 */
document.addEventListener('DOMContentLoaded', () => {
    // --- Get DOM Elements ---
    const messageList = document.getElementById('message-list');
    const messageForm = document.getElementById('manual-message-form');
    const messageInput = messageForm?.querySelector('textarea[name="text_content"]');
    const noMessagesPlaceholder = document.getElementById('no-messages-placeholder');
    const sendButton = messageForm?.querySelector('button[type="submit"]');
    const sendButtonIcon = sendButton?.querySelector('i');
    const errorDisplay = document.getElementById('chat-error-display');
    // Media elements (keep if using)
    const attachButton = document.getElementById('attach-file-button');
    const fileInput = document.getElementById('chat-file-input');
    const fileUploadSpinner = document.getElementById('file-upload-spinner');

    if (!messageList || !messageForm || !messageInput || !sendButton || !sendButtonIcon) {
        console.warn("Chat UI elements not found or incomplete. Chat script may not fully function.");
    }

    const contactWaId = messageList?.dataset.contactWaId;
    let lastTimestamp = messageList?.dataset.lastTimestamp; // Timestamp for fetching NEWER messages
    let pollIntervalId = null;
    const pollInterval = 5000; // Poll every 5 seconds
    let isPolling = false;
    let isSending = false;
    const originalSendButtonHtml = sendButton?.innerHTML;

    // --- NEW: Set to track displayed message IDs ---
    const displayedMessageIds = new Set();
    // Pre-populate with initially rendered messages
    messageList?.querySelectorAll('.message[data-message-id]').forEach(el => {
        if (el.dataset.messageId) {
            displayedMessageIds.add(el.dataset.messageId);
        }
    });
    console.log("Initial displayed message IDs:", Array.from(displayedMessageIds));
    // ---------------------------------------------

    if (!contactWaId || !lastTimestamp) {
        console.error("Chat script error: Missing data attributes on #message-list.");
        // ... (disable form) ...
        return;
    }

    console.log(`Chat script initialized for contact ${contactWaId}, starting poll after ${lastTimestamp}`);

    // --- Helper functions (getCookie, formatTime, getStatusIconHTML, displayError, scrollToBottom) ---
    // Keep these as they were in the previous version.
    function getCookie(name) { /* ... */ }
    const csrftoken = getCookie('csrftoken');
    function formatTime(isoTimestamp) { /* ... */ }
    function getStatusIconHTML(status) { /* ... */ }
    function displayError(message) { /* ... */ }
    function scrollToBottom(force = false) { /* ... */ }


    // --- Function to add a single message object to the UI (with enhanced check) ---
    function addMessageToUI(msg) {
        if (!messageList) return;
        if (noMessagesPlaceholder) noMessagesPlaceholder.style.display = 'none';

        // --- ENHANCED DUPLICATE CHECK ---
        if (!msg || !msg.message_id) {
             console.warn("addMessageToUI called with invalid message object:", msg);
             return; // Don't process invalid messages
        }
        // Check both the DOM and our JS Set
        const alreadyInDOM = document.querySelector(`.message[data-message-id="${msg.message_id}"]`);
        const alreadyTracked = displayedMessageIds.has(msg.message_id);

        if (alreadyInDOM || alreadyTracked) {
             console.log(`Duplicate SKIPPED in addMessageToUI for msg ID: ${msg.message_id} (InDOM: ${!!alreadyInDOM}, Tracked: ${alreadyTracked})`);
            return; // Skip if already displayed or tracked
        }
        // --- END ENHANCED CHECK ---

        console.log(`>>> addMessageToUI called for msg ID: ${msg.message_id}, direction: ${msg.direction}`);

        const messageElement = document.createElement('div');
        messageElement.className = `message ${msg.direction === 'OUT' ? 'outgoing' : 'incoming'}`;
        messageElement.dataset.messageId = msg.message_id;

        // ... (rest of the message element creation: bubble, content, meta) ...
        // (Keep the detailed rendering logic from the previous version here)
        const bubble = document.createElement('div'); bubble.className = 'message-bubble';
        const content = document.createElement('div'); content.className = 'message-text';
        const messageType = msg.message_type || 'text'; const textContent = msg.text_content || '';
        if (messageType === 'text') { content.textContent = textContent; }
        else { content.innerHTML = `<span class="media-indicator"><i class="fas fa-file"></i> [${messageType}]</span>`; if (textContent) { const caption = document.createElement('p'); caption.className = 'media-caption'; caption.textContent = textContent; content.appendChild(caption); } }
        bubble.appendChild(content);
        const meta = document.createElement('div'); meta.className = 'message-meta';
        const timeSpan = document.createElement('span'); timeSpan.className = 'message-time'; timeSpan.textContent = formatTime(msg.timestamp); meta.appendChild(timeSpan);
        if (msg.direction === 'OUT') { const statusSpan = document.createElement('span'); statusSpan.className = 'message-status-icon'; statusSpan.innerHTML = getStatusIconHTML(msg.status); meta.appendChild(statusSpan); }
        bubble.appendChild(meta);
        messageElement.appendChild(bubble);
        // ... (end of element creation) ...

        messageList.appendChild(messageElement);
        displayedMessageIds.add(msg.message_id); // Add ID to our tracking Set

        console.log(`<<< Message ADDED to UI for msg ID: ${msg.message_id}. Total tracked: ${displayedMessageIds.size}`);

        // Update lastTimestamp (used for the *next* poll)
        if (msg.timestamp && (!lastTimestamp || new Date(msg.timestamp) > new Date(lastTimestamp))) {
            lastTimestamp = msg.timestamp;
            messageList.dataset.lastTimestamp = lastTimestamp;
            // console.log(`Updated lastTimestamp in addMessageToUI to: ${lastTimestamp}`);
        }
    }

    // --- Function to Update Message Status Icon ---
    function updateMessageStatus(statusData) { /* ... (same as before) ... */ }


    // --- Function to fetch new messages via AJAX ---
    async function fetchNewMessages() {
        if (isPolling || !messageList) return;
        isPolling = true;

        const currentLastTimestamp = messageList.dataset.lastTimestamp; // Use current value
        const fetchUrl = `/whatsapp/api/messages/latest/?wa_id=${contactWaId}&last_timestamp=${encodeURIComponent(currentLastTimestamp)}`;
        console.log(`Polling fetch: ${fetchUrl}`); // Log the exact request

        try {
            const response = await fetch(fetchUrl, { method: 'GET', headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } });
            if (!response.ok) { /* ... error handling ... */ isPolling = false; return; }
            const data = await response.json();

            if (data.status === 'success') {
                let addedNew = false;
                if (data.new_messages && data.new_messages.length > 0) {
                     console.log(`Polling success: Received ${data.new_messages.length} messages. IDs: ${data.new_messages.map(m => m.message_id).join(', ')}`);
                    data.new_messages.forEach(addMessageToUI); // Calls the function with logs & checks
                    addedNew = true;
                } else {
                    // console.log("Polling success: No new messages."); // Optional log for no new messages
                }

                // Update timestamp for the *next* poll based on server response
                if (data.next_poll_timestamp && new Date(data.next_poll_timestamp) > new Date(messageList.dataset.lastTimestamp)) {
                     console.log(`Polling update: Setting next poll timestamp to ${data.next_poll_timestamp} (was ${messageList.dataset.lastTimestamp})`);
                     messageList.dataset.lastTimestamp = data.next_poll_timestamp;
                     lastTimestamp = data.next_poll_timestamp; // Keep JS variable in sync
                }
                // TODO: Handle updated_statuses if implemented
                // if (data.updated_statuses && data.updated_statuses.length > 0) { updateMessageStatuses(data.updated_statuses); }

                if (addedNew) {
                    scrollToBottom(); // Scroll only if new messages were actually added
                }
            } else { /* ... error handling ... */ }
        } catch (error) { /* ... error handling ... */ }
        finally { isPolling = false; }
    }

    // --- Function to send manual message via AJAX ---
    async function sendManualMessage(event) {
        event.preventDefault();
        if (isSending || !messageForm) return;

        const messageText = messageInput.value.trim();
        if (!messageText) return;

        const sendUrl = messageForm.action;

        isSending = true; /* ... disable form ... */
        sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        console.log(`>>> sendManualMessage called. Text: "${messageText.substring(0,30)}..."`);

        const formData = new FormData(messageForm);

        try {
            const response = await fetch(sendUrl, { /* ... */ });
            const data = await response.json();

            if (response.ok && data.status === 'success' && data.message) {
                console.log(`<<< sendManualMessage SUCCESS. Server returned message ID: ${data.message.message_id}. UI update deferred to polling.`);
                messageInput.value = '';
            } else {
                 console.error(`<<< sendManualMessage FAILED. Status: ${response.status}, Response Data:`, data);
                 /* ... error handling ... */
            }
        } catch (error) {
             console.error("<<< sendManualMessage Network/Fetch ERROR:", error);
             /* ... error handling ... */
        } finally {
            /* ... re-enable form ... */
            messageInput.disabled = false; sendButton.disabled = false;
            sendButton.innerHTML = originalSendButtonHtml; messageInput.focus(); isSending = false;
        }
    }

    // --- Start/Stop Polling ---
    function startPolling() { /* ... (same as before) ... */ }
    function stopPolling() { /* ... (same as before) ... */ }

    // --- Event Listeners ---
    if(messageForm) messageForm.addEventListener('submit', sendManualMessage);
    if(messageInput) messageInput.addEventListener('keydown', (event) => { /* ... */ });
    document.addEventListener('visibilitychange', () => { /* ... */ });
    // if (attachButton) attachButton.addEventListener('click', () => fileInput?.click());
    // if (fileInput) fileInput.addEventListener('change', handleFileUpload); // Ensure handleFileUpload exists

    // --- Initial Setup ---
    scrollToBottom(true);
    if (document.visibilityState === 'visible') { startPolling(); }
    else { console.log("Tab initially hidden, polling paused."); }

}); // End DOMContentLoaded
