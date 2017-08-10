#Embedded file name: ACEStream\Core\Statistics\GoogleAnalytics.pyo
import sys
import urllib
import random
import time
import hashlib
from ACEStream.Core.Session import Session
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class GoogleAnalytics:
    TRACKING_URL = 'http://www.google-analytics.com/__utm.gif'
    ANALYTICS_VERSION = '4.3'
    ACCOUNT_ID = 'UA-24039434-6'

    @classmethod
    def send_event(cls, category, action, label = None, value = None):
        event_string = '5(' + category + '*' + action
        if label is not None:
            event_string += '*' + label
        event_string += ')'
        if value is not None:
            event_string += '(' + value + ')'
        perm_id = Session.get_instance().get_permid()
        perm_id = hashlib.md5(perm_id).hexdigest()
        domain_hash = long('0x' + perm_id[-8:], 16)
        visitor_id = long('0x' + perm_id[:8], 16)
        domain_hash /= 10
        visitor_id /= 10
        now = time.time()
        first_visit = long(now)
        prev_visit = long(now)
        current_visit = long(now)
        visit_number = 1
        cookie_string = '__utma=' + str(domain_hash) + '.' + str(visitor_id) + '.' + str(first_visit) + '.' + str(prev_visit) + '.' + str(current_visit) + '.' + str(visit_number) + ';'
        params = {'utmwv': cls.ANALYTICS_VERSION,
         'utmn': random.randint(1, sys.maxint),
         'utmt': 'event',
         'utme': event_string,
         'utmac': cls.ACCOUNT_ID,
         'utmcc': cookie_string}
        return cls.send_request(params)

    @classmethod
    def send_request(cls, params):
        get_params = []
        for k, v in params.iteritems():
            get_params.append(k + '=' + urllib.quote_plus(str(v)))

        url = cls.TRACKING_URL + '?' + '&'.join(get_params)
        try:
            stream = urllib.urlopen(url)
            stream.read()
            stream.close()
            if DEBUG:
                log('ga::send_request: success:', url)
            return True
        except:
            if DEBUG:
                log('ga::send_request: failed:', url)
            return False
