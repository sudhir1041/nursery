from rest_framework import serializers, viewsets
from .models import WooCommerceOrder


class WooCommerceOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = WooCommerceOrder
        fields = '__all__'


class WooCommerceOrderViewSet(viewsets.ModelViewSet):
    queryset = WooCommerceOrder.objects.all()
    serializer_class = WooCommerceOrderSerializer
