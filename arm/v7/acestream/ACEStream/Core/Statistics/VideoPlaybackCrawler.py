#Embedded file name: ACEStream\Core\Statistics\VideoPlaybackCrawler.pyo
from time import strftime
import cPickle
import sys
import threading
import zlib
from ACEStream.Core.BitTornado.BT1.MessageID import CRAWLER_VIDEOPLAYBACK_INFO_QUERY, CRAWLER_VIDEOPLAYBACK_EVENT_QUERY
from ACEStream.Core.CacheDB.SqliteVideoPlaybackStatsCacheDB import VideoPlaybackDBHandler
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_EIGHTH, OLPROTO_VER_TENTH
from ACEStream.Core.Statistics.Crawler import Crawler
from ACEStream.Core.Utilities.utilities import show_permid, show_permid_short
DEBUG = False

class VideoPlaybackCrawler:
    __single = None
    lock = threading.Lock()

    @classmethod
    def get_instance(cls, *args, **kargs):
        if cls.__single is None:
            cls.lock.acquire()
            try:
                if cls.__single is None:
                    cls.__single = cls(*args, **kargs)
            finally:
                cls.lock.release()

        return cls.__single

    def __init__(self):
        if VideoPlaybackCrawler.__single is not None:
            raise RuntimeError, 'VideoPlaybackCrawler is singleton'
        crawler = Crawler.get_instance()
        if crawler.am_crawler():
            self._file = open('videoplaybackcrawler.txt', 'a')
            self._file.write(''.join(('# ',
             '*' * 80,
             '\n# ',
             strftime('%Y/%m/%d %H:%M:%S'),
             ' Crawler started\n')))
            self._file.flush()
            self._event_db = None
        else:
            self._file = None
            self._event_db = VideoPlaybackDBHandler.get_instance()

    def query_initiator(self, permid, selversion, request_callback):
        if selversion >= OLPROTO_VER_TENTH:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: query_initiator', show_permid_short(permid), 'version', selversion
            request_callback(CRAWLER_VIDEOPLAYBACK_EVENT_QUERY, 'SELECT key, timestamp, event FROM playback_event; DELETE FROM playback_event;', callback=self._after_event_request_callback)
        elif selversion >= OLPROTO_VER_EIGHTH:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: query_initiator', show_permid_short(permid), 'version', selversion
            request_callback(CRAWLER_VIDEOPLAYBACK_INFO_QUERY, 'SELECT key, timestamp, piece_size, num_pieces, bitrate, nat FROM playback_info ORDER BY timestamp DESC LIMIT 50', callback=self._after_info_request_callback)
        elif DEBUG:
            print >> sys.stderr, 'videoplaybackcrawler: query_info_initiator', show_permid_short(permid), 'unsupported overlay version'

    def _after_info_request_callback(self, exc, permid):
        if not exc:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: request send to', show_permid_short(permid)
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             'INFO REQUEST',
             show_permid(permid),
             '\n')))
            self._file.flush()

    def handle_info_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'videoplaybackcrawler: handle_info_crawler_request', show_permid_short(permid), message
        try:
            cursor = self._event_db._db.execute_read(message)
        except Exception as e:
            reply_callback(str(e), error=1)
        else:
            if cursor:
                reply_callback(zlib.compress(cPickle.dumps(list(cursor), 2), 9))
            else:
                reply_callback('error', error=2)

    def handle_info_crawler_reply(self, permid, selversion, channel_id, channel_data, error, message, request_callback):
        if error:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: handle_crawler_reply', error, message
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '   INFO REPLY',
             show_permid(permid),
             str(error),
             message,
             '\n')))
            self._file.flush()
        else:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: handle_crawler_reply', show_permid_short(permid), cPickle.loads(message)
            info = cPickle.loads(message)
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '   INFO REPLY',
             show_permid(permid),
             str(error),
             str(info),
             '\n')))
            self._file.flush()
            i = 0
            for key, timestamp, piece_size, num_pieces, bitrate, nat in info:
                i += 1
                if i == 1:
                    sql = "\nSELECT timestamp, origin, event FROM playback_event WHERE key = '%s' ORDER BY timestamp ASC LIMIT 50;\nDELETE FROM playback_event WHERE key = '%s';\n" % (key, key)
                else:
                    sql = "\nSELECT timestamp, origin, event FROM playback_event WHERE key = '%s' ORDER BY timestamp ASC LIMIT 50;\nDELETE FROM playback_event WHERE key = '%s';\nDELETE FROM playback_info WHERE key = '%s';\n" % (key, key, key)
                request_callback(CRAWLER_VIDEOPLAYBACK_EVENT_QUERY, sql, channel_data=key, callback=self._after_event_request_callback, frequency=0)

    def _after_event_request_callback(self, exc, permid):
        if not exc:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: request send to', show_permid_short(permid)
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             ' EVENT REQUEST',
             show_permid(permid),
             '\n')))
            self._file.flush()

    def handle_event_crawler_reply(self, permid, selversion, channel_id, channel_data, error, message, request_callback):
        if error:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: handle_crawler_reply', error, message
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '  EVENT REPLY',
             show_permid(permid),
             str(error),
             str(channel_data),
             message,
             '\n')))
            self._file.flush()
        elif selversion >= OLPROTO_VER_TENTH:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: handle_crawler_reply', show_permid_short(permid), len(message), 'bytes zipped'
            info = cPickle.loads(zlib.decompress(message))
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '  EVENT REPLY',
             show_permid(permid),
             str(error),
             str(channel_data),
             str(info),
             '\n')))
            self._file.flush()
        elif selversion >= OLPROTO_VER_EIGHTH:
            if DEBUG:
                print >> sys.stderr, 'videoplaybackcrawler: handle_crawler_reply', show_permid_short(permid), cPickle.loads(message)
            info = cPickle.loads(message)
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '  EVENT REPLY',
             show_permid(permid),
             str(error),
             str(channel_data),
             str(info),
             '\n')))
            self._file.flush()

    def handle_event_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'videoplaybackcrawler: handle_event_crawler_request', show_permid_short(permid), message
        try:
            cursor = self._event_db._db.execute_read(message)
        except Exception as e:
            reply_callback(str(e), error=1)
        else:
            if cursor:
                reply_callback(zlib.compress(cPickle.dumps(list(cursor), 2), 9))
            else:
                reply_callback('error', error=2)
