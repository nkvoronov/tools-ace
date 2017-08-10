#Embedded file name: ACEStream\Core\Ads\Manager.pyo
import sys
import time
import hashlib
import random
import base64
import urllib
import os
import binascii
from urlparse import urlparse, urlunparse
from urllib2 import HTTPError, URLError
from types import ListType, DictType
from traceback import print_exc
from xml.dom.minidom import parseString
from xml.dom import expatbuilder
from threading import Thread
try:
    import json
except:
    import simplejson as json

from M2Crypto import RSA, BIO
from ACEStream.version import VERSION
from ACEStream.Core.simpledefs import *
from ACEStream.Core.TorrentDef import *
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.TS.domutils import domutils
DEBUG = False

class BadResponseException(Exception):
    pass


class AdBlockDetectedException(Exception):
    pass


class AdManager:
    TS_ADSYSTEM = 'TS_ADS'
    REQUEST_SECRET = 'q\\\'X!;UL0J_<R*z#GBTL(9mCeRJbm/;L.oi9.`\\"iETli9GD]`t&xlT(]MhJ{NVN,Q.)r~(6+9Bt(G,O%2c/g@sPi]<c[i\\\\ga]fkbHgwH:->ok4w8><y]^:Lw465+W4a(:'
    AD_REQUEST_TIMEOUT = 5
    MAX_VAST_REDIRECTS = 3
    AD_BLOCK_MAX_NETWORK_ERRORS = 10
    RESPONSE_PUBKEY = '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAymBcELt1ju/RIS/pWpeE\ncj7HzeCXxwmAyeYY3IIqtQgRFGMj+aMoJBVPIJwhN4Q+SqfNStmYTpCKUm1nyxi4\nNyP/+x/7eaaWzGSrShRXUOOE/gA23LKWKrugL7+y+XhEe11cyjN6qRqvO+uoCFZy\nwOIz+eK+nnK8LR/v9acFHdwXtFQyqP9uGgNkjytvPU2xLa9Ye2M7zMaq7wfmiqgQ\nEeQQkL3/aCMsEg3LnLGLA3F9zQ0JSc5hcbisGkijVA7cPgSVJ9Q1I6P8G5Ha4Bvm\n6qh325LuShD6PGK5ad1/TmbMIeeYEutRZsDqK81ww9gLvq6LCxBgkm5E+VgJoiMr\nUQIDAQAB\n-----END PUBLIC KEY-----'
    AD_SERVERS = ['a1.torrentstream.org',
     'a1.torrentstream.net',
     'a1.torrentstream.info',
     'a2.torrentstream.org',
     'a2.torrentstream.net',
     'a2.torrentstream.info',
     'a3.torrentstream.org',
     'a3.torrentstream.net',
     'a3.torrentstream.info']

    def __init__(self, baseapp, cookie_jar = None):
        self.baseapp = baseapp
        self.ad_first_count = {}
        self.network_errors = {}
        self.cookie_jar = cookie_jar

    def get_ads(self, device_id, user_login, user_level, content_type, content_id, content_ext, content_duration, affiliate_id = 0, zone_id = 0, developer_id = 0, include_interruptable_ads = True, is_live = False, provider_key = None, provider_content_id = None, user_profile = None):
	return []
        random_number = random.randint(1, sys.maxint)
        params = []
        params.append('d=' + device_id)
        params.append('u=' + user_login)
        params.append('ul=' + str(user_level))
        params.append('ct=' + str(content_type))
        params.append('cid=' + content_id)
        params.append('cext=' + content_ext)
        params.append('dur=' + str(content_duration))
        params.append('a=' + str(affiliate_id))
        params.append('z=' + str(zone_id))
        params.append('did=' + str(developer_id))
        params.append('t=' + str(int(time.time())))
        params.append('r=' + str(random_number))
        params.append('i=' + str(1 if include_interruptable_ads else 0))
        params.append('l=' + str(1 if is_live else 0))
        params.append('v=' + VERSION)
        if provider_key is not None:
            params.append('p=' + provider_key)
        if provider_content_id is not None:
            params.append('pc=' + provider_content_id)
        if user_profile is not None:
            params.append('gender=' + str(user_profile.get_gender_id()))
            params.append('age=' + str(user_profile.get_age_id()))
        data = '#'.join(sorted(params))
        sig = hashlib.sha1(data + self.REQUEST_SECRET).hexdigest()
        p = []
        for param in params:
            p.append(urllib.quote_plus(param, '='))

        query = '/get?' + '&'.join(p) + '&s=' + sig
        got_success = False
        for ad_server in self.AD_SERVERS:
            try:
                url = 'http://' + ad_server + query
                if DEBUG:
                    log('AdManager::get_ads: send request: url', url)
                request_data = {'start_time': time.time(),
                 'timeout': self.AD_REQUEST_TIMEOUT}
                _t = time.time()
                stream = urlOpenTimeout(url, timeout=self.AD_REQUEST_TIMEOUT)
                _t_open = time.time() - _t
                _t = time.time()
                response = stream.read()
                _t_read = time.time() - _t
                _t = time.time()
                stream.close()
                _t_close = time.time() - _t
                if DEBUG:
                    log('admanager::get_ads: request time: open', _t_open, 'read', _t_read, 'close', _t_close)
                vast_ads, ad_settings = self.parse_vast_response(url, response, random_number, request_data, self.MAX_VAST_REDIRECTS)
                ads = self.format_vast_ads(vast_ads, ad_settings, include_interruptable_ads)
                got_success = True
                break
            except BadResponseException as e:
                if DEBUG:
                    log('AdManager::get_ads: exc: ' + str(e))
            except HTTPError as e:
                if DEBUG:
                    log('AdManager::get_ads: http error: ' + str(e))
            except URLError as e:
                if DEBUG:
                    log('AdManager::get_ads: url error: ' + str(e))
            except AdBlockDetectedException:
                if DEBUG:
                    log('AdManager::get_ads: ad block detected')
            except:
                if DEBUG:
                    print_exc()

        if not got_success:
            return False
        return ads

    def get_preload_ads(self, deviceid, user_login, include_interruptable_ads = True, user_profile = None):
	return []
        random_number = random.randint(1, sys.maxint)
        params = []
        params.append('d=' + deviceid)
        params.append('u=' + user_login)
        if include_interruptable_ads:
            flag = 1
        else:
            flag = 0
        params.append('i=' + str(flag))
        params.append('t=' + str(int(time.time())))
        params.append('r=' + str(random_number))
        params.append('v=' + VERSION)
        if user_profile is not None:
            params.append('gender=' + str(user_profile.get_gender_id()))
            params.append('age=' + str(user_profile.get_age_id()))
        data = '#'.join(sorted(params))
        sig = hashlib.sha1(data + self.REQUEST_SECRET).hexdigest()
        p = []
        for param in params:
            p.append(urllib.quote_plus(param, '='))

        query = '/preload?' + '&'.join(p) + '&s=' + sig
        got_success = False
        for ad_server in self.AD_SERVERS:
            try:
                url = 'http://' + ad_server + query
                if DEBUG:
                    log('AdManager::get_preload_ads: send request: url', url)
                stream = urlOpenTimeout(url, timeout=5)
                response = stream.read()
                stream.close()
                ads = self.parse_preload_ad_response(response, random_number)
                got_success = True
                break
            except BadResponseException as e:
                if DEBUG:
                    log('AdManager::get_preload_ads: exc: ' + str(e))
            except HTTPError as e:
                if DEBUG:
                    log('AdManager::get_preload_ads: http error: ' + str(e))
            except URLError as e:
                if DEBUG:
                    log('AdManager::get_preload_ads: url error: ' + str(e))
            except:
                log_exc()

        if not got_success:
            return False
        return ads

    def send_event(self, tracking_url_list, add_sign):
        for url in tracking_url_list:
            if DEBUG:
                log('AdManager::send_event: url', url, 'add_sign', add_sign)
            if add_sign:
                urldata = list(urlparse(url))
                params = []
                query = urldata[4]
                if len(query) > 0:
                    params = query.split('&')
                random_number = random.randint(1, sys.maxint)
                params.append('r=' + str(random_number))
                params.append('t=' + str(long(time.time())))
                payload = []
                for param in params:
                    name, value = param.split('=')
                    payload.append(name + '=' + urllib.unquote_plus(value))

                payload = '#'.join(sorted(payload))
                sig = hashlib.sha1(payload + self.REQUEST_SECRET).hexdigest()
                params.append('s=' + sig)
                query = '&'.join(params)
                urldata[4] = query
                url = urlunparse(urldata)
                if DEBUG:
                    log('admanager::send_event: added request signature: params', params, 'payload', payload, 'url', url)
            try:
                stream = urlOpenTimeout(url, timeout=30, cookiejar=self.cookie_jar)
                response = stream.read()
                stream.close()
            except:
                if DEBUG:
                    print_exc()

    def send_error(self, tracking_url_list, error_code, error_description, delayed = False):
        if delayed:
            if DEBUG:
                log('admanager::send_error: schedule delayed execution')
            self.baseapp.run_delayed(self.send_error, args=[tracking_url_list,
             error_code,
             error_description,
             False])
            return
        for url in tracking_url_list:
            if DEBUG:
                log('AdManager::send_error: url', url, 'error_code', error_code, 'error_description', error_description)
            try:
                error_description = urllib.quote_plus(str(error_description))
            except:
                if DEBUG:
                    print_exc()

            try:
                url = url.replace('[ERRORCODE]', str(error_code))
                url = url.replace('[ERRORDESCRIPTION]', error_description)
                stream = urlOpenTimeout(url, timeout=30, cookiejar=self.cookie_jar)
                response = stream.read()
                stream.close()
            except:
                if DEBUG:
                    print_exc()

    def parse_vast_response(self, ad_server_url, response, request_random, request_data, max_redirects, redirects = 0):
        if DEBUG:
            log('admanager::parse_vast_response: request_data', request_data, 'max_redirects', max_redirects, 'redirects', redirects, 'response', response)
        if len(response) == 0:
            raise BadResponseException('Empty response')
        doc = parseString(response)
        root = doc.documentElement
        if root.tagName == 'VAST':
            ver = root.getAttribute('version')
            if len(ver) == 0:
                raise BadResponseException, 'Missing vast version'
            if ver == '2.0':
                vast_version = 2
            elif ver == '1.0':
                vast_version = 1
            else:
                raise BadResponseException, 'Unsupported vast version ' + ver
        elif root.tagName == 'VideoAdServingTemplate':
            vast_version = 1
        else:
            raise BadResponseException, 'Bad response tagname: ' + root.tagName
        if redirects == 0:
            primary_response = True
        else:
            primary_response = False
        first_ad = True
        ad_settings = {}
        inline_ads = []
        wrapper_ads = []
        for e_ad in domutils.get_children_by_tag_name(root, 'Ad'):
            inline = domutils.get_children_by_tag_name(e_ad, 'InLine')
            wrapper = domutils.get_children_by_tag_name(e_ad, 'Wrapper')
            if len(inline) == 0 and len(wrapper) == 0:
                raise BadResponseException, 'InLine or Wrapper expected'
            if len(inline) > 0 and len(wrapper) > 0:
                raise BadResponseException, 'Single InLine or Wrapper expected'
            data = {}
            ad_root = None
            if len(inline) > 0:
                if len(inline) > 1:
                    raise BadResponseException, 'Single InLine expected'
                data['type'] = 'inline'
                ad_root = inline[0]
                data['ad_server_url'] = ad_server_url
                data['adsystem'] = self.vast_parse_adsystem(vast_version, ad_root)
                data['impressions'] = self.vast_parse_impressions(vast_version, ad_root)
                data['errors'] = self.vast_parse_errors(vast_version, ad_root)
                data['creatives'] = self.vast_parse_creatives(vast_version, ad_root, is_wrapper=False, adsystem=data['adsystem']['name'])
            elif len(wrapper) > 0:
                if len(wrapper) > 1:
                    raise BadResponseException, 'Single Wrapper expected'
                data['type'] = 'wrapper'
                data['max_redirects'] = max_redirects
                ad_root = wrapper[0]
                data['vast_redirect_url'] = self.vast_parse_redirect(vast_version, ad_root)
                data['adsystem'] = self.vast_parse_adsystem(vast_version, ad_root)
                data['impressions'] = self.vast_parse_impressions(vast_version, ad_root)
                data['errors'] = self.vast_parse_errors(vast_version, ad_root)
                data['creatives'] = self.vast_parse_creatives(vast_version, ad_root, is_wrapper=True, adsystem=data['adsystem']['name'])
            ext_data = self.vast_parse_ts_extension(ad_root)
            if primary_response:
                if data['adsystem']['name'] != self.TS_ADSYSTEM:
                    raise BadResponseException, 'Bad AdSystem for the primary response'
                if first_ad:
                    if ext_data['min_ads_duration'] is None:
                        raise BadResponseException, 'Missing MinAdsDuration'
                    if ext_data['max_ads_duration'] is None:
                        raise BadResponseException, 'Missing MaxAdsDuration'
                    ad_settings['min_ads_duration'] = ext_data['min_ads_duration']
                    ad_settings['max_ads_duration'] = ext_data['max_ads_duration']
                    if ext_data['request_timeout'] is not None:
                        request_data['timeout'] = ext_data['request_timeout']
                        if DEBUG:
                            log('admanager::parse_vast_response: update from ext_data: request_timeout', request_data['timeout'])
                if data['type'] == 'wrapper':
                    if ext_data['max_redirects'] is not None:
                        data['max_redirects'] = ext_data['max_redirects']
                        if DEBUG:
                            log('admanager::parse_vast_response: update from ext_data: max_redirects', data['max_redirects'])
                    if ext_data['check_ts_id'] == 'no':
                        data['check_ts_id'] = False
                    else:
                        data['check_ts_id'] = True
                    if ext_data['predownload'] == 'yes':
                        data['predownload'] = True
                    else:
                        data['predownload'] = False
                    try:
                        priority = int(ext_data.get('priority', 1000))
                    except:
                        priority = 1000

                    data['priority'] = priority
                    data['check_duration'] = ext_data['check_duration']
            else:
                data['check_ts_id'] = request_data['check_ts_id']
                data['predownload'] = request_data['predownload']
                data['priority'] = request_data['priority']
                data['check_duration'] = request_data['check_duration']
                if DEBUG:
                    log('admanager::parse_vast_response: inherit settings from primary response: check_ts_id', data['check_ts_id'], 'predownload', data['predownload'], 'priority', data['priority'], 'check_duration', data['check_duration'])
            check_signature = False
            if data['adsystem']['name'] == self.TS_ADSYSTEM:
                check_signature = True
            if first_ad:
                first_ad = False
                if check_signature:
                    self.vast_check_signature(response, request_random, ext_data['response_random'], ext_data['response_sig'])
            if data['type'] == 'inline':
                inline_ads.append(data)
            else:
                wrapper_ads.append(data)

        if DEBUG:
            log('admanager::parse_vast_response: inline_ads', inline_ads, 'wrapper_ads', wrapper_ads)
        if len(wrapper_ads):
            wrapper_inline_ads = self.start_all_wrapper_requests(wrapper_ads, request_random, request_data, redirects)
            if wrapper_inline_ads is not None:
                inline_ads.extend(wrapper_inline_ads)
        return (inline_ads, ad_settings)

    def start_all_wrapper_requests(self, wrapper_ads, request_random, request_data, redirects):
        wrapper_ads.sort(key=lambda wrapper: wrapper['priority'])
        threads = [[]]
        level = 0
        prev_priority = -1
        for wrapper in wrapper_ads:
            if redirects >= wrapper['max_redirects']:
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: max redirects reached: url', wrapper['vast_redirect_url'], 'redirects', redirects, 'max', wrapper['max_redirects'])
                self.send_error(wrapper['errors'], 302, 'max_redirects_reached', True)
                continue
            t = time.time() - request_data['start_time']
            if t >= request_data['timeout']:
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: request timed out, stop: time', t, 'timeout', request_data['timeout'])
                self.send_error(wrapper['errors'], 301, 'wrapper_timeout', True)
                break
            time_left = int(request_data['timeout'] - t)
            if time_left == 0:
                time_left = 1
            url = wrapper['vast_redirect_url']
            if DEBUG:
                log('admanager::start_all_wrapper_requests: fetch wrapper url: url', url, 'time_left', time_left, 'max_redirects', wrapper['max_redirects'])
            if redirects == 0:
                request_data = request_data.copy()
                request_data['check_ts_id'] = wrapper['check_ts_id']
                request_data['predownload'] = wrapper['predownload']
                request_data['priority'] = wrapper['priority']
                request_data['check_duration'] = wrapper['check_duration']
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: set inherited settings: url', url, 'request_data', request_data)
            thread, retval = self.start_single_wrapper_request_thread(wrapper, url, time_left, request_random, request_data, wrapper['max_redirects'], redirects)
            if prev_priority != -1 and prev_priority < wrapper['priority']:
                threads.append([])
                level = len(threads) - 1
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: create new priority level: prev_priority', prev_priority, 'priority', wrapper['priority'], 'level', level)
            prev_priority = wrapper['priority']
            if DEBUG:
                log('admanager::start_all_wrapper_requests: append wrapper: priority', prev_priority, 'level', level)
            threads[level].append((thread, retval, wrapper))

        for t in threads:
            for thread, retval, wrapper in t:
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: start wrapper thread: url', wrapper['vast_redirect_url'], 'thread', thread.name)
                thread.start()

        wrapper_inline_ads = None
        selected_wrapper = None
        level = 0
        while level < len(threads):
            if DEBUG:
                log('admanager::start_all_wrapper_requests: wait for threads at level', level)
            got_unfinished_thread = False
            for thread, retval, wrapper in threads[level]:
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: wait for thread', thread.name)
                if thread.is_alive():
                    if DEBUG:
                        log('admanager::start_all_wrapper_requests: thread is not finished, check next: thread', thread.name)
                    got_unfinished_thread = True
                    continue
                if retval.get('finished', False):
                    if DEBUG:
                        log('admanager::start_all_wrapper_requests: thread is already finished, do not process: thread', thread.name)
                    continue
                retval['finished'] = True
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: thread finished: thread', thread.name, 'retval', retval)
                if retval['ads'] is not None:
                    if DEBUG:
                        log('admanager::start_all_wrapper_requests: got ads, select wrapper: thread', thread.name)
                    wrapper_inline_ads = retval['ads']
                    selected_wrapper = wrapper
                    break
                elif isinstance(retval['error'], HTTPError) or isinstance(retval['error'], URLError):
                    if DEBUG:
                        log('admanager::start_all_wrapper_requests: got network error: thread', thread.name)
                    if not self.check_network_errors(wrapper['vast_redirect_url']):
                        raise AdBlockDetectedException
                elif DEBUG:
                    log('admanager::start_all_wrapper_requests: got error: thread', thread.name)

            if selected_wrapper is not None:
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: got selected wrapper, break: thread', thread.name)
                break
            if got_unfinished_thread:
                if DEBUG:
                    log('admanager::start_all_wrapper_requests: got unfinished thread, wait')
                time.sleep(0.1)
                continue
            elif DEBUG:
                log('admanager::start_all_wrapper_requests: no unfinished threads, check next level')
            level += 1

        if wrapper_inline_ads is not None:
            for ad in wrapper_inline_ads:
                ad['impressions'].extend(selected_wrapper['impressions'])
                ad['errors'].extend(selected_wrapper['errors'])
                for creative in ad['creatives']:
                    tracking = self.vast_get_wrapper_tracking(selected_wrapper, creative['type'], creative['adid'])
                    if len(tracking) > 0:
                        creative['tracking'].extend(tracking)

        return wrapper_inline_ads

    def start_single_wrapper_request_thread(self, wrapper, url, timeout, request_random, request_data, max_redirects, redirects):
        retval = {'ads': None,
         'error': None}
        t = Thread(target=self.start_single_wrapper_request, args=[wrapper,
         retval,
         url,
         timeout,
         request_random,
         request_data,
         max_redirects,
         redirects])
        t.name = 'WrapperRequest' + t.name
        t.daemon = True
        return (t, retval)

    def start_single_wrapper_request(self, wrapper, retval, url, timeout, request_random, request_data, max_redirects, redirects):
        got_network_error = False
        try:
            if DEBUG:
                t = time.time()
                log('admanager::start_single_wrapper_request: start request to wrapper: url', url, 'timeout', timeout, 'cookies', self.cookie_jar)
            stream = urlOpenTimeout(url, timeout, cookiejar=self.cookie_jar)
            response = stream.read()
            stream.close()
            if DEBUG:
                log('admanager::start_single_wrapper_request: finished request to wrapper: url', url, 'cookies', self.cookie_jar, 'time', time.time() - t)
            wrapper_inline_ads, _ = self.parse_vast_response(url, response, request_random, request_data, max_redirects, redirects + 1)
            retval['ads'] = wrapper_inline_ads
        except BadResponseException as e:
            try:
                errmsg = str(e)
            except:
                errmsg = 'unknown error'

            if DEBUG:
                log('admanager::start_single_wrapper_request: failed to parse wrapper response: url', url, 'time', time.time() - t, 'err', errmsg)
                print_exc()
            self.send_error(wrapper['errors'], 100, errmsg, True)
            retval['error'] = e
        except Exception as e:
            try:
                errmsg = str(e)
            except:
                errmsg = 'unknown error'

            if DEBUG:
                log('admanager::start_single_wrapper_request: failed request to wrapper: url', url, 'time', time.time() - t, 'err', errmsg)
                print_exc()
            if isinstance(e, (HTTPError, URLError)):
                got_network_error = True
            self.send_error(wrapper['errors'], 301, errmsg, True)
            retval['error'] = e

        if got_network_error:
            if DEBUG:
                log('admanager::start_single_wrapper_request: got network error: url', url)
            self.inc_network_errors(url)
        else:
            if DEBUG:
                log('admanager::start_single_wrapper_request: reset network error: url', url)
            self.reset_network_errors(url)

    def get_network_errors(self):
        return self.network_errors

    def check_network_errors(self, url):
        urldata = urlparse(url)
        host = urldata.hostname
        errors = self.network_errors.get(host, 0)
        if errors >= self.AD_BLOCK_MAX_NETWORK_ERRORS:
            if DEBUG:
                log('admanager::check_network_errors: too much errors: host', host, 'errors', errors)
            return False
        return True

    def inc_network_errors(self, url):
        try:
            urldata = urlparse(url)
            host = urldata.hostname
            self.network_errors.setdefault(host, 0)
            self.network_errors[host] += 1
            if DEBUG:
                log('admanager::inc_network_errors: host', host, 'errors', self.network_errors[host])
        except:
            if DEBUG:
                print_exc()

    def reset_network_errors(self, url):
        try:
            urldata = urlparse(url)
            host = urldata.hostname
            self.network_errors[host] = 0
            if DEBUG:
                log('admanager::reset_network_errors: host', host, 'errors', self.network_errors[host])
        except:
            if DEBUG:
                print_exc()

    def format_vast_ads(self, vast_ads, ad_settings, include_interruptable_ads = True):
        formatted_ads = []
        for ad in vast_ads:
            if ad['type'] != 'inline':
                raise ValueError, 'Inline ad expected'
            impressions = []
            for impression in ad['impressions']:
                uri = impression['uri']
                if impression['id'] == self.TS_ADSYSTEM and ad['adsystem']['name'] != self.TS_ADSYSTEM:
                    uri = self.update_wrapper_tracking_uri(uri, ad['adsystem']['name'], None)
                impressions.append(uri)

            first_creative = True
            for creative in ad['creatives']:
                skip_ad = False
                events = {'error': ad['errors'],
                 'creativeView': [],
                 'start': [],
                 'firstQuartile': [],
                 'midpoint': [],
                 'thirdQuartile': [],
                 'complete': []}
                if creative['type'] != 'linear':
                    if DEBUG:
                        log('admanager::format_vast_ads: skip creative: type', creative['type'])
                    continue
                if creative['interruptable'] is not None and creative['interruptable'] == 'yes':
                    interruptable = True
                else:
                    interruptable = False
                if interruptable and not include_interruptable_ads:
                    if DEBUG:
                        log('admanager::format_vast_ads: skip interruptable ad')
                    continue
                if creative['wait_preload'] is not None and creative['wait_preload'] == 'yes':
                    wait_preload = True
                else:
                    wait_preload = False
                mediafile = self.select_media_file(creative['files'])
                if mediafile is None:
                    if DEBUG:
                        log('admanager::format_vast_ads:format: skip creative with no suitable files')
                    continue
                for tracking in creative['tracking']:
                    if events.has_key(tracking['event']):
                        uri = tracking['uri']
                        if len(uri) == 0:
                            continue
                        if tracking['adsystem'] == self.TS_ADSYSTEM and ad['adsystem']['name'] != self.TS_ADSYSTEM:
                            uri = self.update_wrapper_tracking_uri(uri, ad['adsystem']['name'], creative['adid'])
                        events[tracking['event']].append(uri)
                        if DEBUG:
                            log('admanager::format_vast_ads: set event handler: event', tracking['event'], 'uri', uri)
                    elif DEBUG:
                        log('admanager::format_vast_ads: unknown event', tracking['event'])

                if creative['placement'] is None:
                    placement = 'preroll'
                else:
                    placement = creative['placement']
                try:
                    sequence = int(creative['sequence'])
                except:
                    sequence = 1000

                if ad['check_duration']:
                    duration = self.duration_from_string(creative['duration'])
                    if DEBUG:
                        log('admanager::format_vast_ads: use vast duration:', duration)
                else:
                    if DEBUG:
                        log('admanager::format_vast_ads: no duration check, set zero duration')
                    duration = 0
                formatted_ad = {'adsystem': ad['adsystem']['name'],
                 'ad_server_url': ad['ad_server_url'],
                 'adsystem_version': ad['adsystem']['version'],
                 'duration': duration,
                 'click_through': creative.get('click_through', None),
                 'placement': placement,
                 'interruptable': interruptable,
                 'wait_preload': wait_preload,
                 'predownload': ad.get('predownload', False),
                 'tracking': {},
                 'sequence': sequence}
                if first_creative:
                    formatted_ad['tracking']['impression'] = impressions
                    first_creative = False
                formatted_ad['tracking'].update(events)
                if creative['ts_ad_id'] is not None:
                    formatted_ad['dltype'] = DLTYPE_TORRENT
                    formatted_ad['ad_id'] = creative['ts_ad_id']
                    tdef = self.baseapp.get_torrent_from_adid(creative['ts_ad_id'])
                    if tdef is None:
                        if DEBUG:
                            log('admanager::format_vast_ads: failed to get torrent from ad-id: ad_id', creative['ts_ad_id'])
                        skip_ad = True
                    else:
                        if DEBUG:
                            log('admanager::format_vast_ads: got torrent from ad-id: ad_id', creative['ts_ad_id'], 'infohash', binascii.hexlify(tdef.get_infohash()))
                        formatted_ad['tdef'] = tdef
                else:
                    if ad['check_ts_id']:
                        if DEBUG:
                            log('admanager::format_vast_ads: missing mandatory ts-ad-id, skip ad')
                        skip_ad = True
                    formatted_ad['dltype'] = DLTYPE_DIRECT
                    formatted_ad['url'] = mediafile['uri']
                if formatted_ad.has_key('ad_id'):
                    creative_id = formatted_ad['ad_id']
                else:
                    creative_id = formatted_ad['url']
                formatted_ad['creative_id'] = hashlib.sha1(creative_id).hexdigest()
                formatted_ad['count_first'] = self.ad_first_count.get(formatted_ad['creative_id'], 0)
                if not skip_ad:
                    formatted_ads.append(formatted_ad)

        if DEBUG:
            s = '\n'
            for ad in formatted_ads:
                s += ad['adsystem'] + '|d=' + str(ad['duration']) + '|t=' + str(ad['dltype']) + '|i=' + str(ad['interruptable']) + '|w=' + str(ad['wait_preload']) + '|seq=' + str(ad['sequence']) + '|first=' + str(ad['count_first']) + '|'
                if ad['dltype'] == DLTYPE_DIRECT:
                    s += ad['url']
                else:
                    s += binascii.hexlify(ad['tdef'].get_infohash())
                s += '\n'

            log('admanager::format_vast_ads: unsorted formatted ads:', s)
        formatted_ads.sort(key=lambda ad: (ad['sequence'], ad['count_first'], random.randint(1, sys.maxint)))
        main_ads = []
        additional_ads = []
        interruptable_ads = []
        main_block_duration = 0
        for ad in formatted_ads:
            if ad['interruptable']:
                interruptable_ads.append(ad)
            else:
                if main_block_duration < ad_settings['min_ads_duration'] and main_block_duration + ad['duration'] <= ad_settings['max_ads_duration']:
                    add_to_main_block = True
                else:
                    add_to_main_block = False
                if DEBUG:
                    log('admanager::format_vast_ads:sort: duration', ad['duration'], 'total', main_block_duration, 'min', ad_settings['min_ads_duration'], 'max', ad_settings['max_ads_duration'], 'add', add_to_main_block)
                if add_to_main_block:
                    main_ads.append(ad)
                    main_block_duration += ad['duration']
                else:
                    ad['interruptable'] = True
                    additional_ads.append(ad)

        formatted_ads = []
        formatted_ads.extend(main_ads)
        formatted_ads.extend(additional_ads)
        formatted_ads.extend(interruptable_ads)
        if len(formatted_ads):
            _id = formatted_ads[0]['creative_id']
            self.ad_first_count.setdefault(_id, 0)
            self.ad_first_count[_id] += 1
        if DEBUG:
            s = '\n'
            for ad in formatted_ads:
                s += ad['adsystem'] + '|d=' + str(ad['duration']) + '|t=' + str(ad['dltype']) + '|i=' + str(ad['interruptable']) + '|seq=' + str(ad['sequence']) + '|first=' + str(ad['count_first']) + '|'
                if ad['dltype'] == DLTYPE_DIRECT:
                    s += ad['url']
                else:
                    s += binascii.hexlify(ad['tdef'].get_infohash())
                s += '\n'

            log('admanager::format_vast_ads: sorted formatted ads:', s)
        return formatted_ads

    def select_media_file(self, files):
        if len(files) == 0:
            return
        if len(files) == 1:
            return files[0]
        selected_file = None
        max_bitrate = 0
        for f in files:
            if f['delivery'] == 'progressive':
                try:
                    bitrate = int(f['bitrate'])
                except:
                    bitrate = 0

                if selected_file is None:
                    selected_file = f
                elif bitrate > max_bitrate:
                    selected_file = f
                    max_bitrate = bitrate

        if DEBUG:
            log('admanager::select_media_file: files', files, 'selected_file', selected_file)
        return selected_file

    def vast_parse_redirect(self, vast_version, root):
        if vast_version == 2:
            e = domutils.get_single_element(root, 'VASTAdTagURI')
            redirect_uri = domutils.get_node_text(e)
        elif vast_version == 1:
            e = domutils.get_single_element(root, 'VASTAdTagURL')
            e = domutils.get_single_element(e, 'URL')
            redirect_uri = domutils.get_node_text(e)
        else:
            raise BadResponseException, 'Unknown vast version: ' + str(vast_version)
        redirect_uri = redirect_uri.strip(' \t\r\n')
        if DEBUG:
            log('%%%%', redirect_uri)
        return redirect_uri

    def vast_parse_adsystem(self, vast_version, root):
        e = domutils.get_single_element(root, 'AdSystem')
        return {'name': domutils.get_node_text(e),
         'version': e.getAttribute('version')}

    def vast_parse_impressions(self, vast_version, root):
        impressions = []
        if vast_version == 2:
            for e in domutils.get_children_by_tag_name(root, 'Impression'):
                uri = domutils.get_node_text(e)
                if uri:
                    impressions.append({'uri': uri,
                     'id': e.getAttribute('id')})

        elif vast_version == 1:
            e_impression = domutils.get_single_element(root, 'Impression', False)
            if e_impression is not None:
                for e in domutils.get_children_by_tag_name(e_impression, 'URL'):
                    uri = domutils.get_node_text(e)
                    if uri:
                        impressions.append({'uri': uri,
                         'id': e.getAttribute('id')})

        else:
            raise BadResponseException, 'Unknown vast version: ' + str(vast_version)
        return impressions

    def vast_parse_errors(self, vast_version, root):
        errors = []
        if vast_version == 2:
            for e in domutils.get_children_by_tag_name(root, 'Error'):
                url = domutils.get_node_text(e)
                if url:
                    errors.append(url)

        elif vast_version == 1:
            e_error = domutils.get_single_element(root, 'Error', False)
            if e_error is not None:
                for e in domutils.get_children_by_tag_name(e_error, 'URL'):
                    url = domutils.get_node_text(e)
                    if url:
                        errors.append(url)

        else:
            raise BadResponseException, 'Unknown vast version: ' + str(vast_version)
        return errors

    def vast_parse_ts_extension(self, root):
        ext_data = {'response_random': None,
         'response_sig': None,
         'max_redirects': None,
         'request_timeout': None,
         'check_ts_id': '',
         'predownload': 'no',
         'min_ads_duration': None,
         'max_ads_duration': None,
         'priority': 1000,
         'check_duration': False}
        e_extensions = domutils.get_single_element(root, 'Extensions', False)
        if e_extensions is not None:
            for e_extension in domutils.get_children_by_tag_name(e_extensions, 'Extension'):
                if e_extension.getAttribute('type') == self.TS_ADSYSTEM:
                    e_response_data = domutils.get_single_element(e_extension, 'ResponseData', False)
                    if e_response_data is not None:
                        value = domutils.get_node_text(e_response_data)
                        if len(value) > 0:
                            ext_data['response_random'] = value
                        value = e_response_data.getAttribute('sig')
                        if len(value) > 0:
                            ext_data['response_sig'] = value
                    e_max_redirects = domutils.get_single_element(e_extension, 'MaxRedirects', False)
                    if e_max_redirects is not None:
                        value = domutils.get_node_text(e_max_redirects)
                        if len(value) > 0:
                            try:
                                ext_data['max_redirects'] = int(value)
                            except:
                                pass

                    e_request_timeout = domutils.get_single_element(e_extension, 'RequestTimeout', False)
                    if e_request_timeout is not None:
                        value = domutils.get_node_text(e_request_timeout)
                        if len(value) > 0:
                            try:
                                ext_data['request_timeout'] = int(value)
                            except:
                                pass

                    e_min_ads_duration = domutils.get_single_element(e_extension, 'MinAdsDuration', False)
                    if e_min_ads_duration is not None:
                        value = domutils.get_node_text(e_min_ads_duration)
                        if len(value) > 0:
                            try:
                                ext_data['min_ads_duration'] = int(value)
                            except:
                                pass

                    e_max_ads_duration = domutils.get_single_element(e_extension, 'MaxAdsDuration', False)
                    if e_max_ads_duration is not None:
                        value = domutils.get_node_text(e_max_ads_duration)
                        if len(value) > 0:
                            try:
                                ext_data['max_ads_duration'] = int(value)
                            except:
                                pass

                    e_check_id = domutils.get_single_element(e_extension, 'CheckID', False)
                    if e_check_id is not None:
                        ext_data['check_ts_id'] = domutils.get_node_text(e_check_id)
                    e_predownload = domutils.get_single_element(e_extension, 'Predownload', False)
                    if e_predownload is not None:
                        ext_data['predownload'] = domutils.get_node_text(e_predownload)
                    e_priority = domutils.get_single_element(e_extension, 'Priority', False)
                    if e_priority is not None:
                        value = domutils.get_node_text(e_priority)
                        if len(value) > 0:
                            try:
                                ext_data['priority'] = int(value)
                            except:
                                pass

                    e_check_duration = domutils.get_single_element(e_extension, 'CheckDuration', False)
                    if e_check_duration is not None:
                        value = domutils.get_node_text(e_check_duration)
                        ext_data['check_duration'] = bool(value == 'yes')

        if DEBUG:
            log('admanager:vast_parse_ts_extension: ext_data', ext_data)
        return ext_data

    def vast_check_signature(self, response, request_random, response_random, response_sig):
        if DEBUG:
            log('admanager::vast_check_signature: response data: response_random', response_random, 'response_sig', response_sig)
        if response_random is None:
            raise BadResponseException, 'Missing response random'
        if response_sig is None:
            raise BadResponseException, 'Missing response sig'
        try:
            response_random = int(response_random)
        except:
            raise BadResponseException, 'Non-integer response random'

        if response_random != request_random:
            if DEBUG:
                log('admanager::vast_check_signature: bad response random: response_random', response_random, 'request_random', request_random)
            raise BadResponseException, 'Bad response random'
        try:
            payload = response.replace('<ResponseData sig="' + response_sig + '"', '<ResponseData')
            bio = BIO.MemoryBuffer(self.RESPONSE_PUBKEY)
            pubkey = RSA.load_pub_key_bio(bio)
            signature = base64.b64decode(response_sig)
            sign_ok = pubkey.verify(hashlib.sha1(payload).digest(), signature)
        except:
            if DEBUG:
                print_exc()
            raise BadResponseException, 'Failed to verify data'

        if not sign_ok:
            raise BadResponseException, 'Failed to verify data'
        return True

    def vast_get_wrapper_tracking(self, wrapper, creative_type, creative_ad_id = None):
        tracking = []
        for wrapper_creative in wrapper['creatives']:
            if wrapper_creative['type'] == creative_type:
                if wrapper_creative['adid'] is not None:
                    if creative_ad_id is None:
                        continue
                    if wrapper_creative['adid'] != creative_ad_id:
                        continue
                tracking.extend(wrapper_creative['tracking'])

        if DEBUG:
            log('admanager::vast_get_wrapper_tracking: wrapper', wrapper, 'creative_type', creative_type, 'creative_ad_id', creative_ad_id, 'tracking', tracking)
        return tracking

    def update_wrapper_tracking_uri(self, uri, adsystem, ad_id):
        if len(adsystem) == 0 and ad_id is None:
            return uri
        if uri.find('?') == -1:
            uri += '?'
        elif not uri.endswith('&'):
            uri += '&'
        if len(adsystem) > 0:
            uri += 'adsystem=' + urllib.quote_plus(adsystem) + '&'
        if ad_id is not None:
            uri += 'adid=' + urllib.quote_plus(ad_id) + '&'
        uri = uri[:-1]
        return uri

    def vast_parse_creatives(self, vast_version, root, is_wrapper, adsystem):
        if vast_version == 1:
            return self.vast_parse_creatives_vast_1(root, is_wrapper, adsystem)
        if vast_version == 2:
            return self.vast_parse_creatives_vast_2(root, is_wrapper, adsystem)
        raise BadResponseException, 'Unknown vast version: ' + str(vast_version)

    def vast_parse_creatives_vast_1(self, root, is_wrapper, adsystem):
        creatives = []
        tracking = []
        e_tracking_events = domutils.get_single_element(root, 'TrackingEvents', False)
        if e_tracking_events is not None:
            for e_tracking in domutils.get_children_by_tag_name(e_tracking_events, 'Tracking'):
                for e_url in domutils.get_children_by_tag_name(e_tracking, 'URL'):
                    tracking.append({'event': e_tracking.getAttribute('event'),
                     'uri': domutils.get_node_text(e_url),
                     'adsystem': adsystem})

        if is_wrapper:
            creatives.append({'type': 'linear',
             'adid': None,
             'tracking': tracking})
        else:
            e_video = domutils.get_single_element(root, 'Video', False)
            if e_video is not None:
                files = []
                placement = None
                interruptable = None
                ts_ad_id = None
                e_duration = domutils.get_single_element(e_video, 'Duration')
                e_ad_id = domutils.get_single_element(e_video, 'AdID', False)
                if e_ad_id is None:
                    ad_id = None
                else:
                    ad_id = domutils.get_node_text(e_ad_id)
                    if len(ad_id) == 0:
                        ad_id = None
                e_media_files = domutils.get_single_element(e_video, 'MediaFiles')
                for e_media_file in domutils.get_children_by_tag_name(e_media_files, 'MediaFile'):
                    e_url = domutils.get_single_element(e_media_file, 'URL')
                    files.append({'uri': domutils.get_node_text(e_url),
                     'id': e_media_file.getAttribute('id'),
                     'delivery': e_media_file.getAttribute('delivery'),
                     'type': e_media_file.getAttribute('type'),
                     'bitrate': e_media_file.getAttribute('bitrate'),
                     'width': e_media_file.getAttribute('width'),
                     'height': e_media_file.getAttribute('height'),
                     'apiFramework': e_media_file.getAttribute('apiFramework')})

                e_ad_parameters = domutils.get_single_element(e_video, 'AdParameters', False)
                if e_ad_parameters is not None:
                    e_placement = domutils.get_single_element(e_ad_parameters, 'Placement', False)
                    e_interruptable = domutils.get_single_element(e_ad_parameters, 'Interruptable', False)
                    e_ts_ad_id = domutils.get_single_element(e_ad_parameters, 'TSAdID', False)
                    if e_placement is not None:
                        placement = domutils.get_node_text(e_placement)
                    if e_interruptable is not None:
                        interruptable = domutils.get_node_text(e_interruptable)
                    if e_ts_ad_id is not None:
                        ts_ad_id = domutils.get_node_text(e_ts_ad_id)
                        if len(ts_ad_id) == 0:
                            ts_ad_id = None
                creatives.append({'type': 'linear',
                 'duration': domutils.get_node_text(e_duration),
                 'adid': ad_id,
                 'tracking': tracking,
                 'files': files,
                 'placement': placement,
                 'interruptable': interruptable,
                 'ts_ad_id': ts_ad_id})
        return creatives

    def vast_parse_creatives_vast_2(self, root, is_wrapper, adsystem):
        creatives = []
        e_creatives = domutils.get_single_element(root, 'Creatives')
        for e_creative in domutils.get_children_by_tag_name(e_creatives, 'Creative'):
            ad_id = e_creative.getAttribute('AdID')
            if len(ad_id) == 0:
                ad_id = None
            e_linear = domutils.get_single_element(e_creative, 'Linear', False)
            if e_linear is not None:
                duration = None
                tracking = []
                files = []
                placement = None
                interruptable = None
                ts_ad_id = None
                wait_preload = None
                click_through = None
                if not is_wrapper:
                    e_duration = domutils.get_single_element(e_linear, 'Duration')
                    duration = domutils.get_node_text(e_duration)
                    e_video_clicks = domutils.get_single_element(e_linear, 'VideoClicks', False)
                    if e_video_clicks is not None:
                        e_click_through = domutils.get_single_element(e_video_clicks, 'ClickThrough', False)
                        if e_click_through is not None:
                            click_through = domutils.get_node_text(e_click_through)
                e_tracking_events = domutils.get_single_element(e_linear, 'TrackingEvents', False)
                if e_tracking_events is not None:
                    a = domutils.get_children_by_tag_name(e_tracking_events, 'Tracking')
                    for e_tracking in a:
                        uri = domutils.get_node_text(e_tracking)
                        if uri:
                            tracking.append({'event': e_tracking.getAttribute('event'),
                             'uri': uri,
                             'adsystem': adsystem})

                if not is_wrapper:
                    e_ad_parameters = domutils.get_single_element(e_linear, 'AdParameters', False)
                    if e_ad_parameters is not None:
                        e_placement = domutils.get_single_element(e_ad_parameters, 'Placement', False)
                        e_interruptable = domutils.get_single_element(e_ad_parameters, 'Interruptable', False)
                        e_ts_ad_id = domutils.get_single_element(e_ad_parameters, 'TSAdID', False)
                        e_wait_preload = domutils.get_single_element(e_ad_parameters, 'WaitPreload', False)
                        if e_placement is not None:
                            placement = domutils.get_node_text(e_placement)
                        if e_interruptable is not None:
                            interruptable = domutils.get_node_text(e_interruptable)
                        if e_wait_preload is not None:
                            wait_preload = domutils.get_node_text(e_wait_preload)
                        if e_ts_ad_id is not None:
                            ts_ad_id = domutils.get_node_text(e_ts_ad_id)
                            if len(ts_ad_id) == 0:
                                ts_ad_id = None
                if not is_wrapper:
                    e_media_files = domutils.get_single_element(e_linear, 'MediaFiles')
                    for e_media_file in domutils.get_children_by_tag_name(e_media_files, 'MediaFile'):
                        files.append({'uri': domutils.get_node_text(e_media_file),
                         'id': e_media_file.getAttribute('id'),
                         'delivery': e_media_file.getAttribute('delivery'),
                         'type': e_media_file.getAttribute('type'),
                         'bitrate': e_media_file.getAttribute('bitrate'),
                         'width': e_media_file.getAttribute('width'),
                         'height': e_media_file.getAttribute('height'),
                         'apiFramework': e_media_file.getAttribute('apiFramework')})

                if is_wrapper:
                    creatives.append({'type': 'linear',
                     'adid': ad_id,
                     'tracking': tracking})
                else:
                    creatives.append({'type': 'linear',
                     'id': e_creative.getAttribute('id'),
                     'sequence': e_creative.getAttribute('sequence'),
                     'adid': ad_id,
                     'duration': duration,
                     'tracking': tracking,
                     'click_through': click_through,
                     'files': files,
                     'placement': placement,
                     'interruptable': interruptable,
                     'wait_preload': wait_preload,
                     'ts_ad_id': ts_ad_id})

        return creatives

    def parse_preload_ad_response(self, response, request_random):
        if len(response) < 8:
            raise BadResponseException('response too small')
        try:
            sig_len = int(base64.b64decode(response[0:8]), 16)
        except:
            if DEBUG:
                print_exc()
            raise BadResponseException('cannot get sign length')

        signature = response[8:8 + sig_len]
        data = response[8 + sig_len:]
        try:
            signature = base64.b64decode(signature)
        except:
            if DEBUG:
                print_exc()
            raise BadResponseException('failed to decode signature')

        try:
            data = base64.b64decode(data)
        except:
            if DEBUG:
                print_exc()
            raise BadResponseException('failed to decode data')

        try:
            bio = BIO.MemoryBuffer(self.RESPONSE_PUBKEY)
            pubkey = RSA.load_pub_key_bio(bio)
            sign_ok = pubkey.verify(hashlib.sha1(data).digest(), signature)
        except:
            if DEBUG:
                print_exc()
            raise BadResponseException('failed to verify data')

        if not sign_ok:
            raise BadResponseException('failed to verify data')
        response = json.loads(data)
        if type(response) != DictType:
            raise BadResponseException('response is not a dict')
        if 'r' not in response:
            raise BadResponseException('missing random in response')
        try:
            response_random = int(response['r'])
        except:
            raise BadResponseException('non-int random in response')

        if response_random != request_random:
            raise BadResponseException('bad random: response=%s request=%s' % (response_random, request_random))
        if DEBUG:
            log('AdManager::parse_preload_ad_response: got success:', response)
        if 'data' not in response:
            raise BadResponseException('missing data')
        if type(response['data']) != ListType:
            raise BadResponseException('data is not a list')
        ads = []
        for a in response['data']:
            if type(a) != DictType:
                raise BadResponseException('data item is not a dict')
            mandatory_fields = ['infohash', 'id']
            for field in mandatory_fields:
                if field not in a:
                    raise BadResponseException('missing ' + field)

            try:
                priority = int(a['priority'])
            except:
                priority = 0

            tdef = None
            try:
                infohash = binascii.unhexlify(a['infohash'])
                ret = self.baseapp.get_torrent_by_infohash(infohash)
                if ret is not None:
                    tdef = ret['tdef']
            except:
                if DEBUG:
                    print_exc()

            if tdef is None:
                if DEBUG:
                    log('AdManager::parse_preload_ad_response: cannot get torrent by infohash: infohash', binascii.hexlify(infohash))
                continue
            if binascii.hexlify(tdef.get_infohash()) != a['infohash']:
                if DEBUG:
                    log('AdManager::parse_preload_ad_response: infohash does not match: response_infohash', a['infohash'], 'tdef_infohash', binascii.hexlify(tdef.get_infohash()))
                raise BadResponseException('infohash does not match')
            try:
                if DEBUG:
                    log('admanager::parse_preload_ad_response: save ad-id: id', a['id'], 'infohash', binascii.hexlify(infohash))
                self.baseapp.save_adid2infohash_db(a['id'], infohash)
            except:
                if DEBUG:
                    print_exc()

            trackers = a.get('trackers', None)
            if DEBUG:
                log('admanager::parse_preload_ad_response: trackers: infohash', binascii.hexlify(infohash), 'trackers', trackers)
            ad = {'tdef': tdef,
             'dltype': DLTYPE_TORRENT,
             'priority': priority,
             'trackers': trackers}
            ads.append(ad)

        return ads

    def duration_from_string(self, string):
        a = string.split(':')
        if len(a) != 3:
            raise ValueError, 'Bad string duration ' + string
        try:
            hours = int(a[0])
            minutes = int(a[1])
            seconds = int(a[2])
        except:
            raise ValueError, 'Malformat string duration ' + string

        return hours * 3600 + minutes * 60 + seconds
