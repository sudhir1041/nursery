// whatsapp_app/static/whatsapp_app/js/chat.js

/**
 * Handles real-time chat functionality using AJAX polling:
 * - Fetches new messages periodically.
 * - Sends new messages typed by the user.
 * - Updates the chat UI dynamically.
 */
document.addEventListener('DOMContentLoaded', () => {
    // --- Get DOM Elements ---
    const messageList = document.getElementById('message-list');
    const messageForm = document.getElementById('manual-message-form');
    const messageInput = messageForm?.querySelector('textarea[name="text_content"]');
    const noMessagesPlaceholder = document.getElementById('no-messages-placeholder');
    const sendButton = messageForm?.querySelector('button[type="submit"]');
    const sendButtonIcon = sendButton?.querySelector('i'); // Get the icon element

    // --- Basic Configuration & State ---
    if (!messageList || !messageForm || !messageInput || !sendButton || !sendButtonIcon) {
        console.log("Chat UI elements not found on this page. Chat script inactive.");
        return; // Exit if essential elements aren't present
    }

    const contactWaId = messageList.dataset.contactWaId;
    let lastTimestamp = messageList.dataset.lastTimestamp; // Timestamp of the last message known by the server on page load
    let pollIntervalId = null; // To store the interval timer ID
    const pollInterval = 5000; // Poll every 5 seconds (adjust as needed)
    let isPolling = false; // Flag to prevent overlapping poll requests
    let isSending = false; // Flag to prevent double message sends
    const originalSendButtonHtml = sendButton.innerHTML; // Store original button content

    if (!contactWaId || !lastTimestamp) {
        console.error("Chat script error: Missing contact WA ID or initial timestamp data attributes on #message-list.");
        return;
    }

    console.log(`Chat script initialized for contact ${contactWaId}, starting poll after ${lastTimestamp}`);

    // --- Helper: Get CSRF token from cookies ---
    function getCookie(name) {
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
    if (!csrftoken) {
        console.warn("CSRF token not found. Message sending might fail.");
        // Disable send button if CSRF is missing?
        // sendButton.disabled = true;
        // sendButton.title = "Cannot send messages: CSRF token missing.";
    }

    // --- Helper: Format Timestamp for Display ---
    function formatTime(isoTimestamp) {
        if (!isoTimestamp) return '';
        try {
            // Use browser's locale for time formatting (HH:MM)
            return new Date(isoTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            console.error("Error formatting time:", e);
            return '';
        }
    }

    // --- Helper: Get Status Icon HTML ---
    function getStatusIconHTML(status) {
        switch (status) {
            case 'FAILED': return '<i class="bi bi-x-circle text-danger"></i>';
            case 'READ': return '<i class="bi bi-check2-all" style="color: #41a5e4;"></i>'; // Blue double tick
            case 'DELIVERED': return '<i class="bi bi-check2-all"></i>'; // Grey double tick
            case 'SENT': return '<i class="bi bi-check2"></i>'; // Grey single tick
            case 'PENDING': return '<i class="bi bi-clock"></i>'; // Pending clock
            default: return ''; // No icon for received or unknown
        }
    }

    // --- Function to add a single message object to the UI ---
    function addMessageToUI(msg) {
        // Remove placeholder if it exists and messages are being added
        if (noMessagesPlaceholder) {
            noMessagesPlaceholder.style.display = 'none';
        }

        // Avoid adding duplicate messages if polling overlaps slightly
        if (document.querySelector(`.message[data-message-id="${msg.message_id}"]`)) {
            // console.log(`Message ${msg.message_id} already exists, skipping.`);
            return;
        }

        const messageElement = document.createElement('div');
        messageElement.classList.add('message', 'mb-2');
        messageElement.classList.add(msg.direction === 'OUT' ? 'outgoing' : 'incoming');
        messageElement.classList.add('d-flex'); // Use flex for alignment
        messageElement.classList.add(msg.direction === 'OUT' ? 'justify-content-end' : 'justify-content-start');
        messageElement.dataset.messageId = msg.message_id; // Add message ID for potential future updates

        const bubble = document.createElement('div');
        bubble.classList.add('message-bubble', 'd-inline-block', 'p-2', 'px-3', 'rounded', 'shadow-sm');
        bubble.style.maxWidth = '75%'; // Set max width via JS or CSS

        // Apply background color and border radius based on direction
        bubble.style.backgroundColor = msg.direction === 'OUT' ? '#dcf8c6' : '#ffffff'; // WhatsApp-like colors
        bubble.style.borderTopLeftRadius = msg.direction === 'IN' ? '0.1rem' : '0.75rem';
        bubble.style.borderTopRightRadius = msg.direction === 'OUT' ? '0.1rem' : '0.75rem';
        if (msg.direction === 'IN') bubble.style.border = '1px solid #f0f0f0';


        // --- Message Content ---
        const content = document.createElement('div'); // Use div for potentially complex content
        content.classList.add('mb-0', 'message-text');
        content.style.fontSize = '0.95rem';
        content.style.lineHeight = '1.4';
        content.style.whiteSpace = 'pre-wrap'; // Preserve whitespace and newlines
        content.style.wordBreak = 'break-word'; // Break long words

        // Render content based on type
        if (msg.message_type === 'text') {
            // Directly set text content to handle special characters safely
            content.textContent = msg.text_content || '';
        } else if (msg.message_type === 'template') {
             content.innerHTML = `<em class="fst-italic"><i class="bi bi-file-richtext me-1"></i>Template: ${msg.template_name || 'Unknown'}</em>`;
             if(msg.text_content) content.innerHTML += `<div class="mt-1">${msg.text_content.replace(/\n/g, '<br>')}</div>`; // Render template text with line breaks
        } else if (msg.message_type === 'image' && msg.media_url) {
             content.innerHTML = `<p class="mb-1 fst-italic"><i class="bi bi-image me-1"></i><em>[Image]</em></p>
                                  <a href="${msg.media_url}" target="_blank" rel="noopener noreferrer">
                                      <img src="${msg.media_url}" alt="Image Attachment" class="img-fluid rounded" style="max-width: 200px; max-height: 200px; cursor: pointer; margin-top: 5px;">
                                  </a>`;
        } else if (msg.message_type === 'document') {
             content.innerHTML = `<p class="mb-1 fst-italic"><i class="bi bi-file-earmark-text me-1"></i><em>[Document]</em></p>`;
             if (msg.media_url) {
                 content.innerHTML += `<a href="${msg.media_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-secondary mt-1">
                                          <i class="bi bi-download"></i> Download
                                      </a>`;
             }
             if (msg.text_content) content.innerHTML += `<p class="mb-0 mt-1">${msg.text_content.replace(/\n/g, '<br>')}</p>`;
        } else {
            // Fallback for other types
            content.innerHTML = `<em class="fst-italic"><i class="bi bi-file-earmark me-1"></i>[${msg.message_type || 'Unknown Type'}]</em>`;
             if(msg.text_content) content.innerHTML += `<p class="mb-0 mt-1">${msg.text_content.replace(/\n/g, '<br>')}</p>`;
        }
        bubble.appendChild(content);

        // --- Message Meta (Timestamp & Status) ---
        const meta = document.createElement('small');
        meta.classList.add('message-meta', 'd-block', 'text-end', 'mt-1');
        meta.style.fontSize = '0.7rem';
        meta.style.color = msg.direction === 'OUT' ? 'rgba(0, 0, 0, 0.45)' : '#6c757d';

        const time = formatTime(msg.timestamp);
        let statusIconHTML = '';
        if (msg.direction === 'OUT') {
            statusIconHTML = `<span class="ms-1 message-status-icon" title="${msg.status || ''}">${getStatusIconHTML(msg.status)}</span>`;
        }
        meta.innerHTML = `${time}${statusIconHTML}`; // Use innerHTML to render icon
        bubble.appendChild(meta);

        messageElement.appendChild(bubble);
        messageList.appendChild(messageElement);

        // Update the global 'lastTimestamp' if this message is newer
        // Important for subsequent polls
        if (msg.timestamp && new Date(msg.timestamp) > new Date(lastTimestamp)) {
             lastTimestamp = msg.timestamp;
             // console.log(`Updated lastTimestamp to: ${lastTimestamp}`);
        }
    }

    // --- Function to scroll message list to bottom ---
    function scrollToBottom(force = false) {
        const threshold = 150; // How close to bottom user needs to be to auto-scroll (pixels)
        const shouldScroll = force || (messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < threshold);

        if (shouldScroll) {
            // Use smooth scrolling if available
            if ('scrollBehavior' in document.documentElement.style) {
                messageList.scrollTo({ top: messageList.scrollHeight, behavior: 'smooth' });
            } else {
                messageList.scrollTop = messageList.scrollHeight; // Fallback for older browsers
            }
        }
    }

    // --- Function to fetch new messages via AJAX ---
    async function fetchNewMessages() {
        if (isPolling) return; // Prevent overlapping polls
        isPolling = true;
        // console.log(`Polling for messages after: ${lastTimestamp}`);

        // Construct URL for the AJAX endpoint in views.py
        const url = `/whatsapp/chats/messages/latest/?wa_id=${contactWaId}&last_timestamp=${encodeURIComponent(lastTimestamp)}`;

        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest', // Identify as AJAX
                    'Accept': 'application/json',
                }
            });

            if (!response.ok) {
                console.error(`Error fetching messages: ${response.status} ${response.statusText}`);
                // Stop polling on critical errors like 404 (contact gone) or 403 (permissions)
                if (response.status === 404 || response.status === 403) {
                     stopPolling();
                     console.warn("Stopping polling due to client/server error (403/404).");
                }
                // Consider adding a delay before next poll on server errors (5xx)
                return; // Exit fetch function
            }

            const data = await response.json();

            if (data.status === 'success') {
                if (data.new_messages && data.new_messages.length > 0) {
                    console.log(`Received ${data.new_messages.length} new messages.`);
                    data.new_messages.forEach(addMessageToUI);
                    scrollToBottom(); // Scroll down only if new messages were added and user is near bottom
                }
                // Update timestamp for the *next* poll using the value from the server response
                if (data.next_poll_timestamp) {
                    // Only update if the server timestamp is actually newer
                    if (new Date(data.next_poll_timestamp) > new Date(lastTimestamp)) {
                         lastTimestamp = data.next_poll_timestamp;
                         // console.log(`Next poll will use timestamp: ${lastTimestamp}`);
                    }
                } else {
                     console.warn("Server did not return next_poll_timestamp.");
                }
                // TODO: Handle updated_statuses if implemented in the backend/view
                // e.g., find existing message elements by data-message-id and update status icon/text
            } else {
                console.error("AJAX endpoint returned error:", data.message || "Unknown error");
            }
        } catch (error) {
            console.error("Network or fetch error during polling:", error);
            // Consider adding exponential backoff or stopping polling after repeated network errors
        } finally {
             isPolling = false; // Allow next poll attempt
        }
    }

    // --- Function to send manual message via AJAX ---
    async function sendManualMessage(event) {
        event.preventDefault(); // Prevent default form submission
        if (isSending) return; // Prevent double clicks

        const messageText = messageInput.value.trim();
        if (!messageText) return; // Don't send empty messages

        const sendUrl = messageForm.action; // Get URL from form's action attribute

        // --- Disable form elements during send ---
        isSending = true;
        messageInput.disabled = true;
        sendButton.disabled = true;
        // Show spinner icon
        sendButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

        // --- Prepare form data ---
        const formData = new FormData();
        formData.append('text_content', messageText);
        // Add CSRF token if not handled globally by AJAX setup
        if (csrftoken) {
             formData.append('csrfmiddlewaretoken', csrftoken);
        }

        try {
            const response = await fetch(sendUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json', // Expect JSON response
                    // If CSRF included in form data, header might not be needed, but often good practice
                    // 'X-CSRFToken': csrftoken
                }
            });

            const data = await response.json();

            if (response.ok && data.status === 'success' && data.message) {
                // --- Success ---
                // Optionally add the 'SENT' message immediately to UI for responsiveness
                addMessageToUI(data.message);
                scrollToBottom(true); // Force scroll after sending your own message

                // Clear input field ONLY on success
                messageInput.value = '';
                console.log("Message sent successfully via AJAX.");
            } else {
                // --- Handle errors ---
                let errorMessage = "Failed to send message.";
                if (data.message) {
                    errorMessage = data.message;
                } else if (data.errors && data.errors.text_content) {
                    errorMessage = data.errors.text_content.join(' '); // Join validation errors
                } else if (!response.ok) {
                     errorMessage = `Server error: ${response.status} ${response.statusText}`;
                }
                console.error("Error sending message:", errorMessage, data);
                // Display error to user (replace alert with a non-blocking notification)
                alert(`Error: ${errorMessage}`);
            }
        } catch (error) {
            console.error("Network error sending message:", error);
            alert("Network error: Could not send message. Please check your connection and try again.");
        } finally {
            // --- Re-enable form elements ---
            messageInput.disabled = false;
            sendButton.disabled = false;
            sendButton.innerHTML = originalSendButtonHtml; // Restore original button content
            messageInput.focus(); // Set focus back to input
            isSending = false;
        }
    }

    // --- Start/Stop Polling ---
    function startPolling() {
        // Avoid starting multiple intervals
        if (pollIntervalId === null) {
             console.log("Starting message polling...");
             // Fetch immediately once when starting or resuming
             fetchNewMessages();
             // Set interval for subsequent polls
             pollIntervalId = setInterval(fetchNewMessages, pollInterval);
        }
    }

    function stopPolling() {
        if (pollIntervalId !== null) {
            console.log("Stopping message polling.");
            clearInterval(pollIntervalId);
            pollIntervalId = null;
        }
    }

    // --- Event Listeners ---
    // Send message on form submit
    messageForm.addEventListener('submit', sendManualMessage);

    // Optional: Send message on Enter key press (Shift+Enter for newline)
    messageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault(); // Prevent default newline insertion
            // Trigger form submission logic only if input has content
            if (messageInput.value.trim()) {
                sendManualMessage(event);
            }
        }
    });

    // Optional: Start/stop polling based on browser tab visibility to save resources
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            console.log("Tab became visible, resuming polling.");
            // Fetch immediately when tab becomes visible again
            fetchNewMessages();
            startPolling();
        } else {
            console.log("Tab became hidden, pausing polling.");
            stopPolling();
        }
    });

    // --- Initial Setup ---
    scrollToBottom(true); // Scroll to bottom on initial page load
    // Start polling only if the tab is currently visible
    if (document.visibilityState === 'visible') {
        startPolling();
    } else {
         console.log("Tab initially hidden, polling paused.");
    }

}); // End DOMContentLoaded

