from rest_framework import serializers, viewsets
from .models import ShopifyOrder


class ShopifyOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopifyOrder
        fields = '__all__'


class ShopifyOrderViewSet(viewsets.ModelViewSet):
    queryset = ShopifyOrder.objects.all()
    serializer_class = ShopifyOrderSerializer
