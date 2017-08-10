#Embedded file name: ACEStream\Core\Statistics\PunctureCrawler.pyo
from ACEStream.Core.Session import Session
from ACEStream.Core.Statistics.Crawler import Crawler
from ACEStream.Core.BitTornado.BT1.MessageID import CRAWLER_PUNCTURE_QUERY
from ACEStream.Core.Utilities.utilities import show_permid, show_permid_short
import os
import time
import sys
import zlib
import thread
DEBUG = False

def get_reporter_instance():
    return SimpleFileReporter.get_instance()


class SimpleFileReporter:
    __single = None
    lock = thread.allocate_lock()

    @classmethod
    def get_instance(cls, *args, **kw):
        cls.lock.acquire()
        try:
            if not cls.__single:
                cls.__single = cls()
        finally:
            cls.lock.release()

        return cls.__single

    def __init__(self):
        self.file = None
        self.path = os.path.join(Session.get_instance().get_state_dir(), 'udppuncture.log')

    def add_event(self, ignore, msg):
        SimpleFileReporter.lock.acquire()
        try:
            if not self.file:
                self.file = open(self.path, 'a+b')
            self.file.write('%.2f %s\n' % (time.time(), msg))
            self.file.flush()
        except:
            if DEBUG:
                print >> sys.stderr, 'Error writing puncture log'
        finally:
            SimpleFileReporter.lock.release()


class PunctureCrawler:
    __single = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__single:
            cls.__single = cls(*args, **kargs)
        return cls.__single

    def __init__(self):
        crawler = Crawler.get_instance()
        if crawler.am_crawler():
            self._file = open('puncturecrawler.txt', 'a')
            self._file.write('# Crawler started at %.2f\n' % time.time())
            self._file.flush()
            self._repexlog = None
        else:
            self.reporter = get_reporter_instance()

    def query_initiator(self, permid, selversion, request_callback):
        request_callback(CRAWLER_PUNCTURE_QUERY, '', callback=self._after_request_callback)

    def _after_request_callback(self, exc, permid):
        if not exc:
            if DEBUG:
                print >> sys.stderr, 'puncturecrawler: request sent to', show_permid_short(permid)
            self._file.write('REQUEST %s %.2f\n' % (show_permid(permid), time.time()))
            self._file.flush()

    def handle_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'puncturecrawler: handle_crawler_request', show_permid_short(permid), message
        SimpleFileReporter.lock.acquire()
        try:
            if not self.reporter.file:
                try:
                    self.reporter.file = open(self.reporter.path, 'a+b')
                except Exception as e:
                    reply_callback(str(e), error=1)
                    return

            file = self.reporter.file
            try:
                file.seek(0)
                result = '%.2f CRAWL\n' % time.time() + file.read()
                result = zlib.compress(result)
                reply_callback(result)
                file.truncate(0)
            except Exception as e:
                reply_callback(str(e), error=1)

            try:
                file.seek(0, os.SEEK_END)
            except:
                pass

        finally:
            SimpleFileReporter.lock.release()

    def handle_crawler_reply(self, permid, selversion, channel_id, channel_data, error, message, request_callback):
        try:
            if error:
                if DEBUG:
                    print >> sys.stderr, 'puncturecrawler: handle_crawler_reply', error, message
                self._file.write('ERROR %s %.2f %d %s\n' % (show_permid(permid),
                 time.time(),
                 error,
                 message))
                self._file.flush()
            else:
                if DEBUG:
                    print >> sys.stderr, 'puncturecrawler: handle_crawler_reply', show_permid_short(permid)
                data = zlib.decompress(message)
                filtered = filter(lambda char: char != '\x00', data)
                self._file.write('REPLY %s %.2f\n' % (show_permid(permid), time.time()))
                self._file.write('# reply sizes: on-the-wire=%d, decompressed=%d, filtered=%d\n' % (len(message), len(data), len(filtered)))
                self._file.write(filtered)
                self._file.flush()
        except:
            if DEBUG:
                print >> sys.stderr, 'puncturecrawler: error writing to file'
