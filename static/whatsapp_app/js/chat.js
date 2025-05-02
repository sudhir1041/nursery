// whatsapp_app/static/whatsapp_app/js/chat.js

/**
 * Handles chat functionality using AJAX polling:
 * - Fetches new messages periodically.
 * - Sends new messages typed by the user via AJAX.
 * - Updates the chat UI dynamically using custom CSS classes.
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
    const attachButton = document.getElementById('attach-file-button');
    const fileInput = document.getElementById('chat-file-input');
    const fileUploadSpinner = document.getElementById('file-upload-spinner');

    if (!messageList || !messageForm || !messageInput || !sendButton || !sendButtonIcon) {
        console.warn("Chat UI elements not found or incomplete. Chat script may not fully function.");
        // return; // Allow script to continue if some non-essential elements are missing
    }

    const contactWaId = messageList?.dataset.contactWaId;
    let lastTimestamp = messageList?.dataset.lastTimestamp;
    let pollIntervalId = null;
    const pollInterval = 5000; // Poll every 5 seconds
    let isPolling = false;
    let isSending = false;
    const originalSendButtonHtml = sendButton?.innerHTML;

    if (!contactWaId || !lastTimestamp) {
        console.error("Chat script error: Missing data attributes on #message-list.");
        if(messageInput) messageInput.disabled = true;
        if(sendButton) sendButton.disabled = true;
        if(sendButton) sendButton.title = "Chat unavailable: Missing configuration.";
        return;
    }

    console.log(`Chat script initialized for contact ${contactWaId}, starting poll after ${lastTimestamp}`);

    // --- Helper: Get CSRF token ---
    function getCookie(name) { /* ... (same as before) ... */
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');
    if (!csrftoken) { console.warn("CSRF token not found."); }

    // --- Helper: Format Timestamp ---
    function formatTime(isoTimestamp) { /* ... (same as before) ... */
        if (!isoTimestamp) return '';
        try {
            return new Date(isoTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) { console.error("Error formatting time:", e); return ''; }
    }

    // --- Helper: Get Status Icon HTML ---
    function getStatusIconHTML(status) { /* ... (same as before using Font Awesome) ... */
        const statusLower = status ? status.toLowerCase() : '';
        switch (statusLower) {
            case 'failed': return '<i class="fas fa-exclamation-circle status-icon-failed" title="Failed"></i>';
            case 'read': return '<i class="fas fa-check-double status-icon-read" title="Read"></i>';
            case 'delivered': return '<i class="fas fa-check-double status-icon-delivered" title="Delivered"></i>';
            case 'sent': return '<i class="fas fa-check status-icon-sent" title="Sent"></i>';
            case 'pending': return '<i class="fas fa-clock status-icon-pending" title="Pending"></i>';
            default: return '';
        }
     }

    // --- Function to display errors ---
    function displayError(message) { /* ... (same as before) ... */
        console.error("Chat Error:", message);
        if (errorDisplay) {
            errorDisplay.textContent = message;
            errorDisplay.style.display = message ? 'block' : 'none';
            if (message && !message.toLowerCase().includes("connection")) {
                 setTimeout(() => { if (errorDisplay) errorDisplay.style.display = 'none'; }, 6000);
            }
        } else { console.warn("No #chat-error-display element found."); }
     }

    // --- Function to scroll message list to bottom ---
    function scrollToBottom(force = false) { /* ... (same as before) ... */
        if (!messageList) return;
        const threshold = 150;
        const isNearBottom = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < threshold;
        if (force || isNearBottom) {
            if ('scrollBehavior' in document.documentElement.style) {
                messageList.scrollTo({ top: messageList.scrollHeight, behavior: 'smooth' });
            } else { messageList.scrollTop = messageList.scrollHeight; }
        }
     }

    // --- Function to add a single message object to the UI ---
    function addMessageToUI(msg) {
        if (!messageList) return;
        if (noMessagesPlaceholder) noMessagesPlaceholder.style.display = 'none';

        // Robust duplicate check
        if (msg.message_id && document.querySelector(`.message[data-message-id="${msg.message_id}"]`)) {
            // console.log(`Message ${msg.message_id} already exists, skipping UI add.`);
            return; // Skip if already displayed
        }

        const messageElement = document.createElement('div');
        messageElement.className = `message ${msg.direction === 'OUT' ? 'outgoing' : 'incoming'}`;
        if (msg.message_id) messageElement.dataset.messageId = msg.message_id;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        const content = document.createElement('div');
        content.className = 'message-text';

        const messageType = msg.message_type || 'text';
        const textContent = msg.text_content || '';
        const mediaUrl = msg.media_url;
        const filename = msg.filename || '';

        if (messageType === 'text') { /* ... render text ... */ content.textContent = textContent; }
        else if (messageType === 'template') { /* ... render template ... */ }
        else if (messageType === 'image') { /* ... render image placeholder/link ... */ }
        else if (messageType === 'video') { /* ... render video placeholder/link ... */ }
        else if (messageType === 'audio') { /* ... render audio placeholder/link ... */ }
        else if (messageType === 'document') { /* ... render document placeholder/link ... */ }
        else { /* ... render fallback ... */ }
        // (Keep the detailed rendering logic from the previous version here)
        // Example for text:
         if (messageType === 'text') {
            content.textContent = textContent;
         } else { // Simplified placeholder for others for brevity
             content.innerHTML = `<span class="media-indicator"><i class="fas fa-file"></i> [${messageType}]</span>`;
             if (textContent) {
                 const caption = document.createElement('p');
                 caption.className = 'media-caption';
                 caption.textContent = textContent;
                 content.appendChild(caption);
             }
         }


        bubble.appendChild(content);

        const meta = document.createElement('div');
        meta.className = 'message-meta';
        const timeSpan = document.createElement('span');
        timeSpan.className = 'message-time';
        timeSpan.textContent = formatTime(msg.timestamp);
        meta.appendChild(timeSpan);
        if (msg.direction === 'OUT') {
            const statusSpan = document.createElement('span');
            statusSpan.className = 'message-status-icon';
            statusSpan.innerHTML = getStatusIconHTML(msg.status);
            meta.appendChild(statusSpan);
        }
        bubble.appendChild(meta);

        messageElement.appendChild(bubble);
        messageList.appendChild(messageElement);

        // Update lastTimestamp (used for the *next* poll)
        if (msg.timestamp && (!lastTimestamp || new Date(msg.timestamp) > new Date(lastTimestamp))) {
            lastTimestamp = msg.timestamp;
            messageList.dataset.lastTimestamp = lastTimestamp; // Update data attribute too
        }
    }

    // --- Function to Update Message Status Icon ---
    function updateMessageStatus(statusData) { /* ... (same as before) ... */
         if (!statusData || !statusData.message_id || !statusData.status) return;
         const messageElement = document.querySelector(`.message[data-message-id="${statusData.message_id}"]`);
         if (messageElement && messageElement.classList.contains('outgoing')) {
             const statusIconSpan = messageElement.querySelector('.message-status-icon');
             if (statusIconSpan) {
                 const newIconHTML = getStatusIconHTML(statusData.status);
                 if (statusIconSpan.innerHTML !== newIconHTML) {
                     console.log(`Updating status for ${statusData.message_id} to ${statusData.status}`);
                     statusIconSpan.innerHTML = newIconHTML;
                     statusIconSpan.title = statusData.status;
                 }
             }
         }
    }


    // --- Function to fetch new messages via AJAX ---
    async function fetchNewMessages() {
        if (isPolling || !messageList) return; // Check messageList exists
        isPolling = true;

        const currentLastTimestamp = messageList.dataset.lastTimestamp; // Use current value from data attribute
        const fetchUrl = `/whatsapp/api/messages/latest/?wa_id=${contactWaId}&last_timestamp=${encodeURIComponent(currentLastTimestamp)}`;

        try {
            const response = await fetch(fetchUrl, { /* ... headers ... */ });
            if (!response.ok) { /* ... error handling ... */ return; }
            const data = await response.json();

            if (data.status === 'success') {
                let addedNew = false;
                if (data.new_messages && data.new_messages.length > 0) {
                    console.log(`Polling: Received ${data.new_messages.length} new messages.`);
                    data.new_messages.forEach(addMessageToUI); // This updates lastTimestamp internally
                    addedNew = true;
                }
                // Update timestamp for the *next* poll based on server response
                // This ensures we don't miss messages if addMessageToUI didn't update timestamp for some reason
                if (data.next_poll_timestamp && new Date(data.next_poll_timestamp) > new Date(messageList.dataset.lastTimestamp)) {
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
        if (isSending || !messageForm) return; // Check form exists

        const messageText = messageInput.value.trim();
        if (!messageText) return;

        const sendUrl = messageForm.action; // Get URL from form

        isSending = true; /* ... disable form ... */
        sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        const formData = new FormData(messageForm); // Use FormData to include hidden fields like wa_id and csrf
        // formData.append('text_content', messageText); // Already included by form
        // formData.append('wa_id', contactWaId); // Already included by hidden input
        // if (csrftoken) formData.append('csrfmiddlewaretoken', csrftoken); // Already included by {% csrf_token %}

        try {
            const response = await fetch(sendUrl, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
            });
            const data = await response.json();

            if (response.ok && data.status === 'success' && data.message) {
                // --- SUCCESS ---
                // *** REMOVED addMessageToUI(data.message); ***
                // Rely on the next poll to fetch and display the sent message.
                messageInput.value = ''; // Clear input ONLY on success
                console.log("Message sent successfully via AJAX. Waiting for poll to display.");
            } else {
                // --- Handle errors ---
                let errorMessage = data.message || "Failed to send message.";
                if (data.errors && data.errors.text_content) { errorMessage = data.errors.text_content.join(' '); }
                else if (!response.ok) { errorMessage = `Server error: ${response.status}`; }
                console.error("Error sending message:", errorMessage, data);
                displayError(`Error: ${errorMessage}`);
            }
        } catch (error) {
            console.error("Network error sending message:", error);
            displayError("Network error: Could not send message.");
        } finally {
            // --- Re-enable form elements ---
            messageInput.disabled = false;
            sendButton.disabled = false;
            sendButton.innerHTML = originalSendButtonHtml;
            messageInput.focus();
            isSending = false;
        }
    }

    // --- Start/Stop Polling ---
    function startPolling() { /* ... (same as before) ... */
        if (pollIntervalId === null) {
            console.log("Starting message polling...");
            fetchNewMessages();
            pollIntervalId = setInterval(fetchNewMessages, pollInterval);
        }
     }
    function stopPolling() { /* ... (same as before) ... */
        if (pollIntervalId !== null) {
            console.log("Stopping message polling.");
            clearInterval(pollIntervalId);
            pollIntervalId = null;
        }
     }

    // --- Event Listeners ---
    if(messageForm) messageForm.addEventListener('submit', sendManualMessage);
    if(messageInput) messageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (messageInput.value.trim()) { sendManualMessage(event); }
        }
    });
    // Keep visibility change listener
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') { startPolling(); }
        else { stopPolling(); }
    });
    // Keep file upload listeners if needed
    // if (attachButton) attachButton.addEventListener('click', () => fileInput?.click());
    // if (fileInput) fileInput.addEventListener('change', handleFileUpload); // Ensure handleFileUpload exists

    // --- Initial Setup ---
    scrollToBottom(true);
    if (document.visibilityState === 'visible') { startPolling(); }
    else { console.log("Tab initially hidden, polling paused."); }

}); // End DOMContentLoaded

