#Embedded file name: ACEStream\Core\Statistics\Crawler.pyo
import sys
import time
import random
from traceback import print_exc, print_stack
from ACEStream.Core.BitTornado.BT1.MessageID import CRAWLER_REQUEST, CRAWLER_REPLY, getMessageName
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import CrawlerDBHandler
from ACEStream.Core.Overlay.OverlayThreadingBridge import OverlayThreadingBridge
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_SEVENTH
from ACEStream.Core.Utilities.utilities import show_permid_short
DEBUG = False
MAX_PAYLOAD_LENGTH = 32768
CHANNEL_TIMEOUT = 3600
FREQUENCY_FLEXIBILITY = 5
MAX_ALLOWED_FAILURES = 26

class Crawler:
    __singleton = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__singleton:
            cls.__singleton = cls(*args, **kargs)
        return cls.__singleton

    def __init__(self, session):
        if self.__singleton:
            raise RuntimeError, 'Crawler is Singleton'
        self._overlay_bridge = OverlayThreadingBridge.getInstance()
        self._session = session
        self._crawler_db = CrawlerDBHandler.getInstance()
        self._message_handlers = {}
        self._crawl_initiators = []
        self._initiator_deadlines = []
        self._dialback_deadlines = {}
        self._channels = {}
        self._check_deadlines(True)
        self._check_channels()

    def register_crawl_initiator(self, initiator_callback, frequency = 3600, accept_frequency = None):
        if accept_frequency is None:
            accept_frequency = frequency
        self._crawl_initiators.append((initiator_callback, frequency, accept_frequency))

    def register_message_handler(self, id_, request_callback, reply_callback):
        self._message_handlers[id_] = (request_callback, reply_callback, 0)

    def am_crawler(self):
        return self._session.get_permid() in self._crawler_db.getCrawlers()

    def _acquire_channel_id(self, permid, channel_data):
        if permid in self._channels:
            channels = self._channels[permid]
        else:
            channels = {}
            self._channels[permid] = channels
        channel_id = random.randint(1, 255)
        attempt = 0
        while channel_id in channels:
            attempt += 1
            if attempt > 64:
                channel_id = 0
                break
            channel_id = random.randint(1, 255)

        if channel_id == 0:
            channel_id = 255
            while channel_id in channels and channel_id != 0:
                channel_id -= 1

        if channel_id:
            channels[channel_id] = [time.time() + CHANNEL_TIMEOUT, '', channel_data]
        return channel_id

    def _release_channel_id(self, permid, channel_id):
        if permid in self._channels:
            if channel_id in self._channels[permid]:
                del self._channels[permid][channel_id]
            if not self._channels[permid]:
                del self._channels[permid]

    def _post_connection_attempt(self, permid, success):
        if success:
            for tup in (tup for tup in self._initiator_deadlines if tup[4] == permid):
                tup[6] = 0

        else:

            def increase_failure_counter(tup):
                if tup[4] == permid:
                    if tup[6] > MAX_ALLOWED_FAILURES:
                        return False
                    else:
                        tup[6] += 1
                        return True
                else:
                    return True

            self._initiator_deadlines = filter(increase_failure_counter, self._initiator_deadlines)

    def send_request(self, permid, message_id, payload, frequency = 3600, callback = None, channel_data = None):
        channel_id = self._acquire_channel_id(permid, channel_data)

        def _after_connect(exc, dns, permid, selversion):
            self._post_connection_attempt(permid, not exc)
            if exc:
                if DEBUG:
                    print >> sys.stderr, 'crawler: could not connect', dns, show_permid_short(permid), exc
                self._release_channel_id(permid, channel_id)
                if callback:
                    callback(exc, permid)
            else:
                self._send_request(permid, message_id, channel_id, payload, frequency=frequency, callback=callback)

        if channel_id == 0:
            if DEBUG:
                print >> sys.stderr, 'crawler: send_request: Can not acquire channel-id', show_permid_short(permid)
        else:
            self._overlay_bridge.connect(permid, _after_connect)
        return channel_id

    def _send_request(self, permid, message_id, channel_id, payload, frequency = 3600, callback = None):

        def _after_send_request(exc, permid):
            if DEBUG:
                if exc:
                    print >> sys.stderr, 'crawler: could not send request to', show_permid_short(permid), exc
            if exc:
                self._release_channel_id(permid, channel_id)
            if callback:
                callback(exc, permid)

        if DEBUG:
            print >> sys.stderr, 'crawler: sending', getMessageName(CRAWLER_REQUEST + message_id), 'with', len(payload), 'bytes payload to', show_permid_short(permid)
        self._overlay_bridge.send(permid, ''.join((CRAWLER_REQUEST,
         message_id,
         chr(channel_id & 255),
         chr(frequency >> 8 & 255) + chr(frequency & 255),
         str(payload))), _after_send_request)
        return channel_id

    def handle_request(self, permid, selversion, message):
        if selversion >= OLPROTO_VER_SEVENTH and len(message) >= 5:
            message_id = message[1]
            channel_id = ord(message[2])
            frequency = ord(message[3]) << 8 | ord(message[4])
            if message_id in self._message_handlers:
                now = time.time()
                request_callback, reply_callback, last_request_timestamp = self._message_handlers[message_id]
                if last_request_timestamp + frequency < now + FREQUENCY_FLEXIBILITY:
                    if permid not in self._channels:
                        self._channels[permid] = {}
                    self._channels[permid][channel_id] = [time.time() + CHANNEL_TIMEOUT, '', None]
                    self._message_handlers[message_id] = (request_callback, reply_callback, now)

                    def send_reply_helper(payload = '', error = 0, callback = None):
                        return self.send_reply(permid, message_id, channel_id, payload, error=error, callback=callback)

                    try:
                        request_callback(permid, selversion, channel_id, message[5:], send_reply_helper)
                    except:
                        print_exc()

                    self._dialback_deadlines[message_id] = (now + frequency, permid)
                    return True
                else:
                    self.send_reply(permid, message_id, channel_id, 'frequency error', error=254)
                    return True
            else:
                self.send_reply(permid, message_id, channel_id, 'unknown message', error=253)
                return True
        else:
            return False

    def send_reply(self, permid, message_id, channel_id, payload, error = 0, callback = None):

        def _after_connect(exc, dns, permid, selversion):
            self._post_connection_attempt(permid, not exc)
            if exc:
                if DEBUG:
                    print >> sys.stderr, 'crawler: could not connect', dns, show_permid_short(permid), exc
                if callback:
                    callback(exc, permid)
            else:
                self._send_reply(permid, message_id, channel_id, payload, error=error, callback=callback)

        self._overlay_bridge.connect(permid, _after_connect)

    def _send_reply(self, permid, message_id, channel_id, payload, error = 0, callback = None):
        if len(payload) > MAX_PAYLOAD_LENGTH:
            remaining_payload = payload[MAX_PAYLOAD_LENGTH:]

            def _after_send_reply(exc, permid):
                if DEBUG:
                    print >> sys.stderr, 'crawler: _after_send_reply', show_permid_short(permid), exc
                if not exc:
                    self.send_reply(permid, message_id, channel_id, remaining_payload, error=error)
                if callback:
                    callback(exc, permid)

            parts_left = min(255, int(len(payload) / MAX_PAYLOAD_LENGTH))
            payload = payload[:MAX_PAYLOAD_LENGTH]
        else:

            def _after_send_reply(exc, permid):
                if DEBUG:
                    if exc:
                        print >> sys.stderr, 'crawler: could not send request', show_permid_short(permid), exc
                if callback:
                    callback(exc, permid)

            parts_left = 0
            if permid in self._channels and channel_id in self._channels[permid]:
                del self._channels[permid][channel_id]
                if not self._channels[permid]:
                    del self._channels[permid]
        if DEBUG:
            print >> sys.stderr, 'crawler: sending', getMessageName(CRAWLER_REPLY + message_id), 'with', len(payload), 'bytes payload to', show_permid_short(permid)
        self._overlay_bridge.send(permid, ''.join((CRAWLER_REPLY,
         message_id,
         chr(channel_id & 255),
         chr(parts_left & 255),
         chr(error & 255),
         str(payload))), _after_send_reply)
        return channel_id

    def handle_reply(self, permid, selversion, message):
        if selversion >= OLPROTO_VER_SEVENTH and len(message) >= 5 and message[1] in self._message_handlers:
            message_id = message[1]
            channel_id = ord(message[2])
            parts_left = ord(message[3])
            error = ord(message[4])
            if permid in self._channels and channel_id in self._channels[permid]:
                self._channels[permid][channel_id][1] += message[5:]
                if parts_left:
                    if DEBUG:
                        print >> sys.stderr, 'crawler: received', getMessageName(CRAWLER_REPLY + message_id), 'with', len(message), 'bytes payload from', show_permid_short(permid), 'with', parts_left, 'parts left'
                    return True
                else:
                    timestamp, payload, channel_data = self._channels[permid].pop(channel_id)
                    if DEBUG:
                        if error == 253:
                            print >> sys.stderr, 'crawler: received', getMessageName(CRAWLER_REPLY + message_id), 'with', len(message), 'bytes payload from', show_permid_short(permid), 'indicating an unknown message error'
                        if error == 254:
                            print >> sys.stderr, 'crawler: received', getMessageName(CRAWLER_REPLY + message_id), 'with', len(message), 'bytes payload from', show_permid_short(permid), 'indicating a frequency error'
                        else:
                            print >> sys.stderr, 'crawler: received', getMessageName(CRAWLER_REPLY + message_id), 'with', len(payload), 'bytes payload from', show_permid_short(permid)
                    if not self._channels[permid]:
                        del self._channels[permid]

                    def send_request_helper(message_id, payload, frequency = 3600, callback = None, channel_data = None):
                        return self.send_request(permid, message_id, payload, frequency=frequency, callback=callback, channel_data=channel_data)

                    try:
                        self._message_handlers[message_id][1](permid, selversion, channel_id, channel_data, error, payload, send_request_helper)
                    except:
                        print_exc()

                    return True
            elif DEBUG:
                print >> sys.stderr, 'crawler: received', getMessageName(CRAWLER_REPLY + message_id), 'with', len(payload), 'bytes payload from', show_permid_short(permid), 'from unknown peer or unused channel'
        if DEBUG:
            if len(message) >= 2:
                message_id = message[1]
            else:
                message_id = ''
            print >> sys.stderr, 'crawler: received', getMessageName(CRAWLER_REPLY + message_id), 'with', len(message), 'bytes from', show_permid_short(permid), 'from unknown peer or unused channel'
        return False

    def handle_connection(self, exc, permid, selversion, locally_initiated):
        if exc:
            if DEBUG:
                print >> sys.stderr, 'crawler: overlay connection lost', show_permid_short(permid), exc
                print >> sys.stderr, repr(permid)
        elif selversion >= OLPROTO_VER_SEVENTH:
            already_known = False
            for tup in self._initiator_deadlines:
                if tup[4] == permid:
                    already_known = True
                    break

            if not already_known:
                if DEBUG:
                    print >> sys.stderr, 'crawler: new overlay connection', show_permid_short(permid)
                    print >> sys.stderr, repr(permid)
                for initiator_callback, frequency, accept_frequency in self._crawl_initiators:
                    self._initiator_deadlines.append([0,
                     frequency,
                     accept_frequency,
                     initiator_callback,
                     permid,
                     selversion,
                     0])

                self._initiator_deadlines.sort()
                self._check_deadlines(False)
        elif DEBUG:
            print >> sys.stderr, 'crawler: new overlay connection (can not use version %d)' % selversion, show_permid_short(permid)
            print >> sys.stderr, repr(permid)

    def _check_deadlines(self, resubmit):
        now = time.time()
        if self._initiator_deadlines:
            for tup in self._initiator_deadlines:
                deadline, frequency, accept_frequency, initiator_callback, permid, selversion, failure_counter = tup
                if now > deadline + FREQUENCY_FLEXIBILITY:

                    def send_request_helper(message_id, payload, frequency = accept_frequency, callback = None, channel_data = None):
                        return self.send_request(permid, message_id, payload, frequency=frequency, callback=callback, channel_data=channel_data)

                    try:
                        initiator_callback(permid, selversion, send_request_helper)
                    except Exception:
                        print_exc()

                    tup[0] = now + frequency
                else:
                    break

            self._initiator_deadlines.sort()
        if self._dialback_deadlines:

            def _after_connect(exc, dns, permid, selversion):
                if DEBUG:
                    if exc:
                        print >> sys.stderr, 'crawler: dialback to crawler failed', dns, show_permid_short(permid), exc
                    else:
                        print >> sys.stderr, 'crawler: dialback to crawler established', dns, show_permid_short(permid)

            for message_id, (deadline, permid) in self._dialback_deadlines.items():
                if now > deadline + FREQUENCY_FLEXIBILITY:
                    self._overlay_bridge.connect(permid, _after_connect)
                    del self._dialback_deadlines[message_id]

        if resubmit:
            self._overlay_bridge.add_task(lambda : self._check_deadlines(True), 5)

    def _check_channels(self):
        now = time.time()
        to_remove_permids = []
        for permid in self._channels:
            to_remove_channel_ids = []
            for channel_id, (deadline, _, _) in self._channels[permid].iteritems():
                if now > deadline:
                    to_remove_channel_ids.append(channel_id)

            for channel_id in to_remove_channel_ids:
                del self._channels[permid][channel_id]

            if not self._channels[permid]:
                to_remove_permids.append(permid)

        for permid in to_remove_permids:
            del self._channels[permid]

        self._overlay_bridge.add_task(self._check_channels, 60)
