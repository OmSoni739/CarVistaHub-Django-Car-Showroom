import os
from django.conf import settings
from django.core.files.storage import FileSystemStorage

# Secure private file storage for sensitive personal documents (e.g. Driving Licence images)
# Files stored here reside outside the public MEDIA_ROOT and have no public MEDIA_URL,
# preventing direct unauthorized browser access. Access is strictly controlled via
# authenticated Manager-only views.
private_storage_location = getattr(settings, 'PRIVATE_MEDIA_ROOT', settings.BASE_DIR / 'private_media')

private_storage = FileSystemStorage(
    location=private_storage_location,
    base_url=None,  # No direct public URL
)

