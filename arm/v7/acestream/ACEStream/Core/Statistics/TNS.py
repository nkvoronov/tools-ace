#Embedded file name: ACEStream\Core\Statistics\TNS.pyo
import sys
import random
import time
import urllib
import binascii
import hashlib
from traceback import print_exc
from ACEStream.version import VERSION, VERSION_REV
from ACEStream.Utilities.TimedTaskQueue import TimedTaskQueue
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class TNSNotAllowedException(Exception):
    pass


class TNS:
    DEFAULT_ONLINE_INTERVAL = 60
    DEFAULT_CONTENT_TYPES = ['d', 'o']
    TYPE_VOD = 'd'
    TYPE_LIVE = 'o'
    TYPE_RADIO = 'r'

    def __init__(self, url_list, options, uid, cookie_jar, tdef, player_data = None):
        self.url_list = url_list
        self.uid = uid
        self.cookie_jar = cookie_jar
        self.version = 'ts' + VERSION + '-' + VERSION_REV
        self.screen_size = self.get_screen_size()
        if options is None:
            self.send_online_interval = TNS.DEFAULT_ONLINE_INTERVAL
            self.allowed_content_types = TNS.DEFAULT_CONTENT_TYPES
            self.only_license = True
        else:
            try:
                i = int(options.get('only_license', 1))
                self.only_license = i != 0
            except:
                self.only_license = True

            try:
                self.send_online_interval = int(options.get('online_interval', TNS.DEFAULT_ONLINE_INTERVAL))
            except:
                self.send_online_interval = 0

            self.allowed_content_types = options.get('allowed_content_types', TNS.DEFAULT_CONTENT_TYPES)
            if not isinstance(self.allowed_content_types, list):
                self.allowed_content_types = []
        if tdef.get_live():
            self.content_type = TNS.TYPE_LIVE
        else:
            self.content_type = TNS.TYPE_VOD
        if self.content_type not in self.allowed_content_types:
            if DEBUG:
                log('tns::__init__: not allowed: content_type', self.content_type, 'allowed', self.allowed_content_types)
            raise TNSNotAllowedException
        self.player_id = self.get_random()
        self.session_id = self.get_random()
        self.content_id = None
        if tdef.get_tns_enabled():
            provider_key = tdef.get_provider()
            if provider_key is not None:
                provider_content_id = tdef.get_content_id()
                if provider_content_id is None:
                    provider_content_id = ''
                try:
                    name = tdef.get_name_as_unicode()
                    name = name.encode('utf-8')
                except:
                    if DEBUG:
                        print_exc()
                    name = ''

                s = hashlib.sha1(provider_key + provider_key[0:4]).hexdigest()
                provider_key = s[:10] + '-' + s[10:20] + '-' + s[20:30] + '-' + s[30:]
                self.content_id = 'ts:' + name + ':' + provider_key + ':' + provider_content_id
                if DEBUG:
                    log('tns::__init__: tns enabled, content id:', self.content_id)
            elif DEBUG:
                log('tns::__init__: tns enabled, but missing provider key')
        if self.content_id is None:
            if self.only_license:
                if DEBUG:
                    log('tns::__init__: only licensed content allowed')
                raise TNSNotAllowedException
            self.content_id = 'ts:user_content'
            if DEBUG:
                log('tns::__init__: content id:', self.content_id)
        self.video_width = None
        self.video_height = None
        if player_data is not None:
            if player_data.has_key('width'):
                self.video_width = data['width']
            if player_data.has_key('height'):
                self.video_height = data['height']
        self.play_time = 0
        self.buffer_time = 0
        self.online_time = 0
        self.download_stopped = False
        self.stopped = False
        self.playing = False
        self.buffering = False
        self.last_buffering = 0
        self.tqueue = TimedTaskQueue(nameprefix='TNSTaskQueue', debug=False)

    def start(self):
        if DEBUG:
            log('tns::start: ---')
        self.send_event('READY')
        if self.send_online_interval:
            self.send_online()
        self.update_counters()
        self.tqueue.add_task(self.send_pixel)

    def stop(self):
        if DEBUG:
            log('tns::stop: stopped', self.stopped)
        if not self.stopped:
            self.send_event('STOP')
        self.tqueue.add_task('quit')
        self.download_stopped = True

    def send_online(self):
        if self.download_stopped:
            if DEBUG:
                log('tns::send_online: download stopped, exit')
            return
        try:
            if self.playing and not self.buffering:
                self.send_event('ONLINE')
            elif self.buffering and time.time() - self.last_buffering >= 30:
                self.send_event('BUFFER')
        except:
            if DEBUG:
                print_exc()
        finally:
            self.tqueue.add_task(self.send_online, self.send_online_interval)

    def update_counters(self):
        if self.download_stopped:
            if DEBUG:
                log('tns::update_counters: download stopped, exit')
            return
        if self.playing:
            self.play_time += 1
        if self.buffering:
            self.buffer_time += 1
        self.online_time += 1
        if DEBUG:
            log('tns::update_counters: playing', self.playing, 'buffering', self.buffering, 'onlinetime', self.online_time, 'playtime', self.play_time, 'buffer_time', self.buffer_time)
        self.tqueue.add_task(self.update_counters, 1)

    def send_event(self, event, event_data = None, delay = 0):
        if DEBUG:
            log('tns::send_event: event', event, 'playing', self.playing, 'stopped', self.stopped, 'download_stopped', self.download_stopped, 'event_data', event_data, 'delay', delay)
        if self.download_stopped:
            return
        event = event.upper()
        if event == 'PLAY':
            if self.playing:
                return
            self.stopped = False
            self.playing = True
            self.buffering = False
        elif event == 'BUFFER':
            self.buffering = True
            self.last_buffering = time.time()
        elif event == 'BUFFERFULL':
            self.buffering = False
        elif event == 'PAUSE':
            self.playing = False
            self.buffering = False
        elif event in ('STOP', 'COMPLETE', 'ERROR', 'CLOSE'):
            if self.stopped:
                return
            self.stopped = True
            self.playing = False
            self.buffering = False
        params = {'cookie': self.uid,
         'time': str(long(time.time())),
         'state': event,
         'value': 'http://acestream.org/local',
         'version': self.version,
         'pt': self.content_type,
         'player_id': str(self.player_id),
         'session_id': str(self.session_id),
         'file': self.content_id}
        if self.screen_size is not None:
            params['sw'] = str(self.screen_size[0])
            params['sh'] = str(self.screen_size[1])
        if self.play_time is not None:
            params['playtime'] = str(self.play_time)
        if self.buffer_time is not None:
            params['buffertime'] = str(self.buffer_time)
        if self.online_time is not None:
            params['onlinetime'] = str(self.online_time)
        if self.video_width is not None:
            params['vw'] = str(self.video_width)
        if self.video_height is not None:
            params['vh'] = str(self.video_height)
        if event_data is not None:
            if event_data.has_key('position'):
                params['position'] = str(event_data['position'])
            if event.startswith('AD'):
                for p in ['ads_link', 'ads_file', 'click_url']:
                    if event_data.get(p, None):
                        params[p] = event_data[p]

        send_request_lambda = lambda : self.send_request(params)
        self.tqueue.add_task(send_request_lambda, delay)

    def send_pixel(self, timeout = 5):
        for url in self.url_list['pixel']:
            try:
                if DEBUG:
                    log('tns::send_pixel: url', url)
                stream = urlOpenTimeout(url, timeout=timeout, cookiejar=self.cookie_jar)
                stream.read()
                stream.close()
            except:
                if DEBUG:
                    log('tns::send_pixel: failed')

    def send_request(self, params, timeout = 5):
        try:
            get_params = []
            if len(params):
                for k, v in params.iteritems():
                    get_params.append(k + '=' + urllib.quote_plus(v))

            query_string = ''
            if len(get_params):
                query_string = '?' + '&'.join(get_params)
            if DEBUG:
                log('tns::send_request: query_string', query_string)
            for url in self.url_list['default']:
                try:
                    url += query_string
                    if DEBUG:
                        log('tns::send_request: url', url)
                    stream = urlOpenTimeout(url, timeout=timeout, cookiejar=self.cookie_jar)
                    stream.read()
                    stream.close()
                except:
                    if DEBUG:
                        log('tns::send_request: failed: url', url)

        except:
            if DEBUG:
                print_exc()

    def get_screen_size(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        except:
            return

    def get_random(self):
        rand = random.randint(1, 1000000000)
        try:
            d = str(long(time.time()))
            return long(d[-8:]) + rand
        except:
            return rand
