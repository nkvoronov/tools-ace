#Embedded file name: ACEStream\Core\Statistics\Settings.pyo
import time
import binascii
import json
from traceback import print_exc
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class RemoteStatisticsSettings:
    SETTINGS_URL = 'http://stat.acestream.net/opt/check'
    RETRY_ON_ERROR = 3600
    MODE_ALLOW_ALL = 1
    MODE_DENY_ALL = 2
    MODE_WHITELIST = 3
    MODE_BLACKLIST = 4

    def __init__(self):
        self.reset_settings()

    def reset_settings(self):
        self.settings = {}

    def get_url_list(self, stat_type):
        if not self.settings.has_key(stat_type):
            return None
        return self.settings[stat_type]['url-list']

    def get_options(self, stat_type):
        if not self.settings.has_key(stat_type):
            return None
        return self.settings[stat_type]['options']

    def check_content(self, stat_type, tdef):
        if not self.settings.has_key(stat_type):
            return False
        options = self.settings[stat_type]
        if options['mode'] == RemoteStatisticsSettings.MODE_DENY_ALL:
            return False
        if options['mode'] == RemoteStatisticsSettings.MODE_ALLOW_ALL:
            return True
        if options['mode'] == RemoteStatisticsSettings.MODE_WHITELIST:
            if options['whitelist_infohash'] is not None:
                infohash = binascii.hexlify(tdef.get_infohash())
                return infohash in options['whitelist_infohash']
            if options['whitelist_content'] is not None:
                provider_key = tdef.get_provider()
                content_id = tdef.get_content_id()
                if provider_key is None or content_id is None:
                    return False
                k = provider_key + ':' + content_id
                return k in options['whitelist_content']
        elif options['mode'] == RemoteStatisticsSettings.MODE_BLACKLIST:
            if options['blacklist_infohash'] is not None:
                infohash = binascii.hexlify(tdef.get_infohash())
                return infohash not in options['blacklist_infohash']
            if options['blacklist_content'] is not None:
                provider_key = tdef.get_provider()
                content_id = tdef.get_content_id()
                if provider_key is None or content_id is None:
                    return False
                k = provider_key + ':' + content_id
                return k not in options['blacklist_content']
        if DEBUG:
            log('RemoteStatisticsSettings::check_content: should not be here: settings', self.settings)
        return False

    def check_settings(self, timeout = 120):
        try:
            if DEBUG:
                t = time.time()
            stream = urlOpenTimeout(RemoteStatisticsSettings.SETTINGS_URL, timeout=timeout)
            response = stream.read()
            stream.close()
            if DEBUG:
                log('RemoteStatisticsSettings::check_settings: got response: time', time.time() - t, 'response', response)
            self.reset_settings()
            response = json.loads(response)
            for stat_type, options in response.iteritems():
                if stat_type == '_expires':
                    expires = long(options)
                else:
                    mode = options['mode']
                    parsed_options = {'mode': None,
                     'url-list': options['url-list'],
                     'whitelist_infohash': None,
                     'whitelist_content': None,
                     'blacklist_infohash': None,
                     'blacklist_content': None,
                     'options': options.get('options', None)}
                    if mode == 'all':
                        parsed_options['mode'] = RemoteStatisticsSettings.MODE_ALLOW_ALL
                    elif mode == 'none':
                        parsed_options['mode'] = RemoteStatisticsSettings.MODE_DENY_ALL
                    elif mode == 'whitelist':
                        parsed_options['mode'] = RemoteStatisticsSettings.MODE_WHITELIST
                        if options.has_key('infohashes'):
                            parsed_options['whitelist_infohash'] = set(options['infohashes'])
                        elif options.has_key('content'):
                            parsed_options['whitelist_content'] = set(options['content'])
                        else:
                            raise Exception, 'missing content identifiers'
                    elif mode == 'blacklist':
                        parsed_options['mode'] = RemoteStatisticsSettings.MODE_BLACKLIST
                        if options.has_key('infohashes'):
                            parsed_options['blacklist_infohash'] = set(options['infohashes'])
                        elif options.has_key('content'):
                            parsed_options['blacklist_content'] = set(options['content'])
                        else:
                            raise Exception, 'missing content identifiers'
                    else:
                        raise Exception, 'unknown mode'
                    self.settings[stat_type] = parsed_options

            return expires
        except:
            self.reset_settings()
            if DEBUG:
                print_exc()
            return RemoteStatisticsSettings.RETRY_ON_ERROR
