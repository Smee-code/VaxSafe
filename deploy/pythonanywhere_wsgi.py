# PythonAnywhere WSGI file for VaxSafe.
#
# Copy everything below into the WSGI configuration file linked on your
# PythonAnywhere "Web" tab (replace its whole contents), then change
# YOURUSERNAME to your PythonAnywhere username. Settings such as the secret
# key are read from the .env file in the project folder, not from here.

import os
import sys

PROJECT_DIR = '/home/YOURUSERNAME/VaxSafe'

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vaxsafe.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
