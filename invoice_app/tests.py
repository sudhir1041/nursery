from django.test import TestCase, RequestFactory
from django.urls import reverse
from .models import Order, Invoice
from .views import invoice_pdf
from django.contrib.auth.models import User
import json

class InvoicePDFTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='testpass'
        )
        
        # Create test order data
        self.order_data = {
            'order_id': 'TEST-001',
            'customer_name': 'Test Customer',
            'customer_address': '123 Test St, Test City, 12345',
            'customer_email': 'customer@test.com',
            'customer_phone': '1234567890',
            'order_total': 100.00,
            'order_status': 'completed',
            'order_items': json.dumps([
                {
                    'name': 'Test Product',
                    'price': '50.00',
                    'quantity': 2
                }
            ]),
            'payment_method': 'credit_card',
            'shipping_charge': 10.00
        }
        
        # Create test order and invoice
        self.order = Order.objects.create(**self.order_data)
        self.invoice = Invoice.objects.create(order=self.order)

    def test_invoice_pdf_generation(self):
        """Test that PDF generation works correctly"""
        request = self.factory.get(reverse('invoice_pdf', args=[self.order.id]))
        request.user = self.user
        
        # Set the scheme and host for absolute URI building
        request.scheme = 'http'
        request.META['SERVER_NAME'] = 'testserver'
        request.META['SERVER_PORT'] = '80'
        
        response = invoice_pdf(request, self.order.id)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'invoice_{self.invoice.invoice_number}.pdf', 
                     response['Content-Disposition'])

    def test_invoice_pdf_invalid_order(self):
        """Test PDF generation with invalid order ID"""
        request = self.factory.get(reverse('invoice_pdf', args=[99999]))
        request.user = self.user
        
        # Set the scheme and host for absolute URI building
        request.scheme = 'http'
        request.META['SERVER_NAME'] = 'testserver'
        request.META['SERVER_PORT'] = '80'
        
        response = invoice_pdf(request, 99999)
        
        self.assertEqual(response.status_code, 200)  # Returns 200 with error message
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertIn('Error generating invoice PDF', str(response.content))