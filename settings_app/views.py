from rest_framework import viewsets
from .models import Credential
from .serializers import CredentialSerializer


class CredentialViewSet(viewsets.ModelViewSet):
    queryset = Credential.objects.all()
    serializer_class = CredentialSerializer
