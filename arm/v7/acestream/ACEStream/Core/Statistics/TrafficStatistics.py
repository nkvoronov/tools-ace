#Embedded file name: ACEStream\Core\Statistics\TrafficStatistics.pyo
import sys
import random
import time
import urllib
import binascii
from traceback import print_exc
from ACEStream.version import VERSION, VERSION_REV
from ACEStream.Utilities.TimedTaskQueue import TimedTaskQueue
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class TrafficStatistics:
    NODE_CLIENT = 1
    NODE_SOURCE = 2
    NODE_SUPPORT = 3

    def __init__(self, node_type, node_id):
        self.url_list = None
        self.node_type = node_type
        self.node_id = node_id
        self.tqueue = TimedTaskQueue(nameprefix='TrafficStatTaskQueue', debug=False)

    def set_url_list(self, url_list):
        if DEBUG:
            log('tstats::set_url_list:', url_list)
        if url_list is None:
            self.url_list = None
        else:
            self.url_list = url_list

    def send_event(self, download_id, event, downloaded, uploaded, infohash, provider_key = None, provider_content_id = None):
        params = {'type': str(self.node_type),
         'node': self.node_id,
         'd': download_id,
         'e': event,
         'down': str(downloaded),
         'up': str(uploaded),
         'infohash': infohash}
        if provider_key is not None:
            params['provider'] = provider_key
        if provider_content_id is not None:
            params['cid'] = provider_content_id
        send_request_lambda = lambda : self.send_request(params)
        self.tqueue.add_task(send_request_lambda)

    def send_request(self, params, timeout = 5):
        if self.url_list is None:
            return
        get_params = []
        if len(params):
            for k, v in params.iteritems():
                get_params.append(k + '=' + urllib.quote_plus(v))

        query_string = ''
        if len(get_params):
            query_string = '?' + '&'.join(get_params)
        if DEBUG:
            log('tstats::send_request: query_string', query_string)
        for url in self.url_list['default']:
            try:
                url += query_string
                if DEBUG:
                    log('tstats::send_request: url', url)
                stream = urlOpenTimeout(url, timeout=timeout)
                stream.read()
                stream.close()
            except:
                if DEBUG:
                    log('tstats::send_request: failed: url', url)
