from rest_framework import serializers, viewsets
from .models import Facebook_orders


class FacebookOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facebook_orders
        fields = '__all__'


class FacebookOrderViewSet(viewsets.ModelViewSet):
    queryset = Facebook_orders.objects.all()
    serializer_class = FacebookOrderSerializer
