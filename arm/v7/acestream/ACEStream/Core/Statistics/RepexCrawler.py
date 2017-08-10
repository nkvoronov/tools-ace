#Embedded file name: ACEStream\Core\Statistics\RepexCrawler.pyo
import sys
import cPickle
import base64
from time import strftime
from ACEStream.Core.BitTornado.BT1.MessageID import CRAWLER_REPEX_QUERY
from ACEStream.Core.Utilities.utilities import show_permid, show_permid_short
from ACEStream.Core.Statistics.Crawler import Crawler
from ACEStream.Core.DecentralizedTracking.repex import RePEXLogDB
DEBUG = False

class RepexCrawler:
    __single = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__single:
            cls.__single = cls(*args, **kargs)
        return cls.__single

    def __init__(self, session):
        crawler = Crawler.get_instance()
        if crawler.am_crawler():
            self._file = open('repexcrawler.txt', 'a')
            self._file.write(''.join(('# ',
             '*' * 78,
             '\n# ',
             strftime('%Y/%m/%d %H:%M:%S'),
             ' Crawler started\n')))
            self._file.flush()
            self._repexlog = None
        else:
            self._file = None
            self._repexlog = RePEXLogDB.getInstance(session)

    def query_initiator(self, permid, selversion, request_callback):
        if DEBUG:
            print >> sys.stderr, 'repexcrawler: query_initiator', show_permid_short(permid)
        request_callback(CRAWLER_REPEX_QUERY, '', callback=self._after_request_callback)

    def _after_request_callback(self, exc, permid):
        if not exc:
            if DEBUG:
                print >> sys.stderr, 'repexcrawler: request sent to', show_permid_short(permid)
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             'REQUEST',
             show_permid(permid),
             '\n')))
            self._file.flush()

    def handle_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'repexcrawler: handle_crawler_request', show_permid_short(permid), message
        try:
            repexhistory = self._repexlog.getHistoryAndCleanup()
        except Exception as e:
            reply_callback(str(e), error=1)
        else:
            reply_callback(cPickle.dumps(repexhistory, 2))

    def handle_crawler_reply(self, permid, selversion, channel_id, channel_data, error, message, request_callback):
        if error:
            if DEBUG:
                print >> sys.stderr, 'repexcrawler: handle_crawler_reply', error, message
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '  REPLY',
             show_permid(permid),
             str(error),
             message,
             '\n')))
            self._file.flush()
        else:
            if DEBUG:
                print >> sys.stderr, 'repexcrawler: handle_crawler_reply', show_permid_short(permid), cPickle.loads(message)
            self._file.write('; '.join((strftime('%Y/%m/%d %H:%M:%S'),
             '  REPLY',
             show_permid(permid),
             str(error),
             base64.b64encode(message),
             '\n')))
            self._file.flush()
