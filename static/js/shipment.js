// Function to get CSRF token from the form
function getCsrfToken() {
    return document.querySelector('#shipForm [name=csrfmiddlewaretoken]').value;
}

// Function to show the "View Card Details" popup
function showPopup(cardElement) {
    const popup = document.getElementById('cardPopup');
    
    const order = {
        platform: cardElement.dataset.platform,
        id: cardElement.dataset.orderId,
        location: cardElement.querySelector('.card__location').textContent.trim(),
        status: cardElement.querySelector('.card__status').textContent.trim(),
        customer: cardElement.querySelector('.card__title').textContent.trim(),
        phone: cardElement.querySelector('.card__contact').textContent.trim(),
        amount: cardElement.dataset.amount || 'N/A',
        advance_amount: cardElement.dataset.advance_amount || 'N/A',
        balance_amount: cardElement.dataset.balance_amount || 'N/A',
        date: cardElement.dataset.date || 'N/A', 
        address: cardElement.dataset.address || 'N/A',
        pincode: cardElement.dataset.pincode || 'N/A',
        note: cardElement.dataset.note || 'N/A',
        tracking: cardElement.dataset.tracking || 'N/A',
        shipmentStatus: cardElement.dataset.shipmentStatus || 'N/A',
        items: Array.from(cardElement.querySelectorAll('.card__list-item')).map(itemLi => {
            return {
                name: itemLi.dataset.itemName,
                potSize: itemLi.dataset.itemPotsize,
                quantity: parseInt(itemLi.dataset.itemQuantity) || 1
            };
        })
    };

    document.getElementById('popupPlatform').textContent = order.platform;
    document.getElementById('popupPlatform').className = `card__source card__source--${order.platform.toLowerCase()}`;
    document.getElementById('popupId').textContent = order.id;
    document.getElementById('popupLocation').textContent = order.location;
    document.getElementById('popupStatus').textContent = order.status;
    document.getElementById('popupTitle').textContent = order.customer;
    document.getElementById('popupContact').textContent = order.phone;
    document.getElementById('popupAmount').textContent = order.amount;
    document.getElementById('popupadvance_amount').textContent = order.advance_amount;
    document.getElementById('popupbalance_amount').textContent = order.balance_amount;
    document.getElementById('popupDate').textContent = order.date; 
    document.getElementById('popupAddress').textContent = order.address;
    document.getElementById('popupPincode').textContent = order.pincode;
    document.getElementById('popupNote').textContent = order.note;
    document.getElementById('popupTracking').textContent = order.tracking;
    document.getElementById('popupShipmentStatus').textContent = order.shipmentStatus;

    const itemsTableBody = document.getElementById('popupItemsTableBody');
    itemsTableBody.innerHTML = ''; 
    order.items.forEach((item, index) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${index + 1}</td>
            <td class="table-item">${item.name}</td>
            <td>${item.potSize}</td>
            <td>${item.quantity}</td>
        `;
        itemsTableBody.appendChild(tr);
    });

    popup.style.display = 'flex';
}

function closePopup() {
    document.getElementById('cardPopup').style.display = 'none';
}

function showShipPopup(cardElement) {
    const popup = document.getElementById('shipPopup');
    
    const orderId = cardElement.dataset.orderId;
    const platform = cardElement.dataset.platform;
    const customerName = cardElement.querySelector('.card__title').textContent.trim();

    const shipForm = document.getElementById('shipForm');
    shipForm.dataset.orderId = orderId;
    shipForm.dataset.platform = platform; // Store platform on the form

    document.getElementById('shipOrderId').textContent = `Order ID: ${orderId}`;
    document.getElementById('shipCustomer').textContent = `Customer: ${customerName}`;
    document.getElementById('shipPlatform').textContent = `Platform: ${platform}`;


    const itemsData = Array.from(cardElement.querySelectorAll('.card__list-item')).map((itemLi, index) => {
        return {
            id: `item-${orderId}-${platform}-${index}`, // Made ID more unique
            name: itemLi.dataset.itemName,
            potSize: itemLi.dataset.itemPotsize,
            quantity: parseInt(itemLi.dataset.itemQuantity) || 1,
            displayText: itemLi.textContent.trim() 
        };
    });

    const itemsContainer = document.getElementById('shipItems');
    itemsContainer.innerHTML = ''; 

    itemsData.forEach(item => {
        const itemRowDiv = document.createElement('div');
        itemRowDiv.className = 'ship-form__item-row';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'ship-form__checkbox';
        checkbox.checked = false; 
        checkbox.id = item.id; 
        checkbox.dataset.itemName = item.name;
        checkbox.dataset.itemPotSize = item.potSize;
        checkbox.dataset.itemQuantity = item.quantity;

        const label = document.createElement('label');
        label.textContent = item.displayText;
        label.htmlFor = checkbox.id; 

        itemRowDiv.appendChild(checkbox);
        itemRowDiv.appendChild(label);
        itemsContainer.appendChild(itemRowDiv);
    });
    
    const currentShipmentStatus = cardElement.dataset.shipmentStatus || 'processing';
    // Ensure the value exists in the dropdown options
    const shipStatusDropdown = document.getElementById('shipStatus');
    if ([...shipStatusDropdown.options].map(opt => opt.value).includes(currentShipmentStatus.toLowerCase())) {
        shipStatusDropdown.value = currentShipmentStatus.toLowerCase();
    } else {
        shipStatusDropdown.value = 'processing'; // Default if status not in options
    }


    popup.style.display = 'flex';
}

function closeShipPopup() {
    document.getElementById('shipPopup').style.display = 'none';
}

document.querySelectorAll('.card').forEach(card => {
    // NEW: "Show More" functionality for items list
    const showMoreButton = card.querySelector('.show-more-btn');
    if (showMoreButton) {
        showMoreButton.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevents the card's main click event (opening the popup)

            const hiddenItems = card.querySelectorAll('.card__list-item--hidden');
            const isExpanded = showMoreButton.getAttribute('aria-expanded') === 'true';

            hiddenItems.forEach(item => {
                // Toggle the display style
                item.style.display = isExpanded ? 'none' : 'list-item';
            });

            // Update the button text and its state for accessibility
            if (isExpanded) {
                showMoreButton.textContent = `Show ${hiddenItems.length} more...`;
                showMoreButton.setAttribute('aria-expanded', 'false');
            } else {
                showMoreButton.textContent = 'Show Less';
                showMoreButton.setAttribute('aria-expanded', 'true');
            }
        });
    }

    const viewButton = card.querySelector('.button--tertiary');
    if (viewButton) {
        viewButton.addEventListener('click', (e) => {
            e.stopPropagation(); 
            showPopup(card);
        });
    }

    const shipButton = card.querySelector('.button--primary');
    if (shipButton) {
        shipButton.addEventListener('click', (e) => {
            e.stopPropagation(); 
            showShipPopup(card);
        });
    }
    
    const cloneButton = card.querySelector('.button--secondary');
    if (cloneButton) {
        cloneButton.addEventListener('click', (e) => {
            e.stopPropagation();
            console.log('Clone button clicked for order:', card.dataset.orderId, 'Platform:', card.dataset.platform);
            alert('Clone functionality (full order duplication) to be implemented separately.');
        });
    }

    card.addEventListener('click', (e) => {
        // Only open the main popup if the click was not on a button
        if (!e.target.closest('button')) { 
            showPopup(card);
        }
    });
});

document.getElementById('cardPopup').addEventListener('click', (e) => {
    if (e.target.id === 'cardPopup') { 
        closePopup();
    }
});

document.getElementById('shipPopup').addEventListener('click', (e) => {
    if (e.target.id === 'shipPopup') {
        closeShipPopup();
    }
});

document.getElementById('shipForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const form = e.target;
    const shippingStatus = document.getElementById('shipStatus').value;
    const orderId = form.dataset.orderId;
    const platform = form.dataset.platform;

    const unselectedItems = [];
    const selectedItems = [];
    let totalUnselectedPlants = 0;

    const itemCheckboxes = document.querySelectorAll('#shipItems .ship-form__checkbox');

    itemCheckboxes.forEach(checkbox => {
        const itemDetails = {
            name: checkbox.dataset.itemName,
            potSize: checkbox.dataset.itemPotSize,
            quantity: parseInt(checkbox.dataset.itemQuantity) || 1
        };
        if (checkbox.checked) {
            selectedItems.push(itemDetails);
        } else {
            unselectedItems.push(itemDetails);
            totalUnselectedPlants += itemDetails.quantity;
        }
    });

    // Get current year from system
    const currentYear = new Date().getFullYear();
    // Create new order ID for unselected items by appending current year
    const newOrderId = orderId + currentYear;

    const customerName = document.getElementById('shipCustomer').textContent.replace('Customer: ', '');
    const customerEmail = document.getElementById('shipCustomer').dataset.email || '';
    const customerPhone = document.getElementById('shipCustomer').dataset.phone || '';
    const customerAddress = document.getElementById('shipCustomer').dataset.address || '';

    const shippingData = {
        orderId: orderId,
        platform: platform,
        shippingStatus: shippingStatus,
        selectedItems: selectedItems,
        unselectedItems: unselectedItems,
        totalUnselectedPlants: totalUnselectedPlants,
        newOrderDetails: {
            orderId: newOrderId,
            customerName: customerName,
            customerEmail: customerEmail,
            customerPhone: customerPhone,
            customerAddress: customerAddress,
            platform: platform,
            items: unselectedItems,
            status: 'pending'
        }
    };

    console.log("Shipping Data to send to backend:", JSON.stringify(shippingData, null, 2));

    const processingUrl = '/shipment/process-shipment/';

    fetch(processingUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(shippingData)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.error || `Server error: ${response.status} ${response.statusText}`);
            }).catch(() => {
                throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Backend success response:', data);
        
        let message = `Order ${orderId} processed successfully.`;
        if (unselectedItems.length > 0) {
            message += `\nNew order ${newOrderId} created with ${totalUnselectedPlants} unselected plants for ${customerName}`;
        }
        alert(message);
        
        // UPDATE: Refresh the page after 2 seconds to show the updated order list
        setTimeout(() => {
            location.reload();
        }, 2000); // 2000 milliseconds = 2 seconds
    })
    .catch((error) => {
        console.error('Error sending shipping data to backend:', error);
        alert(`Error processing order ${orderId}: ${error.message}. Please check console.`);
        closeShipPopup(); // Close popup only on error, since success will refresh
    });
});

