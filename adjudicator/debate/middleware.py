from django.http import HttpResponseForbidden
import geoip2.database
from django.conf import settings
import os

class EUBlockerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        db_path = os.path.join(settings.BASE_DIR, 'GeoLite2-Country.mmdb')
        self.reader = geoip2.database.Reader(db_path)

    def __call__(self, request):
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        try:
            # Check if IP is from EU
            response = self.reader.country(ip)
            if response.country.is_in_european_union:
                return HttpResponseForbidden('''
                    <h1>Service Not Available in EU</h1>
                    <p>We apologize, but this service is currently not available in the European Union 
                    while we work on GDPR compliance.</p>
                ''')
        except:
            # If we can't determine location, let the request through
            pass

        return self.get_response(request)

    def __del__(self):
        self.reader.close() 