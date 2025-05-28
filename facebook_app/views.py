import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DeleteView 
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta

from .models import Facebook_orders 
from .forms import FacebookOrderForm
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin

logger = logging.getLogger(__name__)

# --- Order List View  ---
@login_required
def facebook_order_list_view(request):
    """
    Displays a list of synchronized Facebook orders,
    with searching and overdue highlighting based on order status.
    NOTE: Pagination is recommended for large datasets.
    """
    queryset = Facebook_orders.objects.all()

    search_query = request.GET.get('search_query', '').strip()
    active_filter = False 

    # --- Apply Search Filter ---
    if search_query:
        logger.debug(f"Facebook Applying search filter: '{search_query}'")
        # Use Q objects for OR query on various fields
        query_filter = Q(email__icontains=search_query) | \
                       Q(phone__icontains=search_query) | \
                       Q(alternet_number__icontains=search_query) | \
                       Q(first_name__icontains=search_query) | \
                       Q(last_name__icontains=search_query) | \
                       Q(order_id__iexact=search_query) 
        queryset = queryset.filter(query_filter)
        active_filter = True

    # --- Calculate Overdue Highlight Flag for Facebook Orders ---
    # WARNING: This processes the *entire* filtered queryset.
    now = timezone.now()
    two_days_ago = now - timedelta(days=2) # Highlight orders older than 2 days

    # --- Configuration based on provided Facebook_orders model ---
    # Statuses indicating the order needs attention and might be "overdue" if old.
    # These come from your ORDER_STATUS_CHOICES
    actionable_statuses = ['pending', 'processing', 'on-hold'] # <-- Review this list if needed
    status_field_name = 'status'          # Correct field name from model
    date_field_name = 'date_created'      # Correct field name from model
    # --- End Configuration ---

    processed_orders = [] 
    for order in queryset: 
        # Set a default value first
        order.is_overdue_highlight = False
        try:
            # Safely access fields using getattr and check date validity
            current_status = getattr(order, status_field_name, None)
            creation_date = getattr(order, date_field_name, None)

            if creation_date: 
                status_needs_action = (
                    current_status and 
                    current_status in actionable_statuses
                )

                # Check if it's older than 2 days (assuming timezone compatibility)
                is_old = creation_date < two_days_ago

                # Highlight if both conditions are met
                if status_needs_action and is_old:
                    order.is_overdue_highlight = True

        except Exception as e:
            # Log unexpected errors during highlight calculation
            order_id_str = getattr(order, 'order_id', getattr(order, 'id', 'N/A')) 
            logger.error(f"Error calculating highlight for Facebook Order ID {order_id_str}: {e}", exc_info=True)
            order.is_overdue_highlight = False 

        processed_orders.append(order) 

    # --- Prepare Context ---
    context = {
        'orders': processed_orders,
        'page_title': 'Facebook Orders',
        'current_search_query': search_query, 
        'active_filter': active_filter,
    }

    # Ensure this template path matches your project structure
    template_name = 'facebook/order_list.html'
    return render(request, template_name, context)


# --- Order Detail View  ---
@login_required
def facebook_order_detail_view(request, order_id):
    order = get_object_or_404(Facebook_orders, order_id=order_id)
    order_products_list = order.products_json or []
    context = {
        'order': order,
        'order_products_list': order_products_list, 
        'page_title': f'Facebook Order Details {order.order_id}'
    }
    return render(request, 'facebook/order_detail.html', context)

# --- Order Create View  ---
@login_required
def facebook_order_create_view(request):
    if request.method == 'POST':
        form = FacebookOrderForm(request.POST)

        if form.is_valid():
            try:
                order_instance = form.save()
                messages.success(request, f"Order {order_instance.order_id} created successfully!")
                # return redirect('facebook_order_detail', order_id=order_instance.order_id)
                return redirect('facebook_index')
            except Exception as e:
                logger.exception(f"[Create Order] Error saving form: {e}")
                messages.error(request, "An unexpected error occurred while saving the order.")
        else:
             messages.error(request, "Please correct the validation errors below.")
    else:

        form = FacebookOrderForm()

    return render(request, 'facebook/order_form.html', { 
        'form': form,
        'page_title': 'Create New Facebook Order',
        'form_mode': 'Create'
        
    })
# --- Order Edit View ---
@login_required
def facebook_order_edit_view(request, order_id):
    # Remove this invalid conversion to int
    if not isinstance(order_id, str) or not order_id.startswith('NS'):
        raise Http404(f"Invalid order ID format: {order_id}")

    order_instance = get_object_or_404(Facebook_orders, order_id=order_id)

    if request.method == 'POST':
        form = FacebookOrderForm(request.POST, instance=order_instance)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Order {order_instance.order_id} updated successfully!")
                return redirect('facebook_index')
            except Exception as e:
                logger.exception(f"Error updating Facebook order {order_id}: {e}")
                messages.error(request, "Error updating order. Please check the data.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = FacebookOrderForm(instance=order_instance)

    context = {
        'form': form,
        'order': order_instance,
        'page_title': f'Edit Facebook Order {order_instance.order_id}',
        'form_mode': 'Edit'
    }
    return render(request, 'facebook/order_form.html', context)



# --- Order Delete View ---
class FacebookOrderDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = 'facebook.delete_facebook_orders'
    model = Facebook_orders
    template_name = 'facebook/order_confirm_delete.html'
    success_url = reverse_lazy('facebook_index') 
    slug_field = 'order_id'
    slug_url_kwarg = 'order_id'
    context_object_name = 'order'
    permission_denied_message = "You do not have permission to delete orders."
    
    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return render(self.request, 'facebook/403.html', {
            'error_message': self.permission_denied_message
        }, status=403)

    def post(self, request, *args, **kwargs):
        order_id_display = self.get_object().order_id
        messages.success(request, f"Order {order_id_display} deleted successfully.")
        return super().post(request, *args, **kwargs)

