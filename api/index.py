import os
import sys

# Add backend/ to path so `import raktch` resolves correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'raktch.settings')

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()
