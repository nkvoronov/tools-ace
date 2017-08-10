#Embedded file name: ACEStream\Core\Statistics\SeedingStatsCrawler.pyo
import sys
import cPickle
from ACEStream.Core.BitTornado.BT1.MessageID import CRAWLER_SEEDINGSTATS_QUERY
from ACEStream.Core.CacheDB.SqliteSeedingStatsCacheDB import *
DEBUG = False

class SeedingStatsCrawler:
    __single = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__single:
            cls.__single = cls(*args, **kargs)
        return cls.__single

    def __init__(self):
        self._sqlite_cache_db = SQLiteSeedingStatsCacheDB.getInstance()

    def query_initiator(self, permid, selversion, request_callback):
        if DEBUG:
            print >> sys.stderr, 'crawler: SeedingStatsDB_update_settings_initiator'
        read_query = 'SELECT * FROM SeedingStats WHERE crawled = 0'
        write_query = 'UPDATE SeedingStats SET crawled = 1 WHERE crawled = 0'
        return request_callback(CRAWLER_SEEDINGSTATS_QUERY, cPickle.dumps([('read', read_query), ('write', write_query)], 2))

    def update_settings_initiator(self, permid, selversion, request_callback):
        if DEBUG:
            print >> sys.stderr, 'crawler: SeedingStatsDB_update_settings_initiator'
        try:
            sql_update = 'UPDATE SeedingStatsSettings SET crawling_interval=%s WHERE crawling_enabled=%s' % (1800, 1)
        except:
            print_exc()
        else:
            return request_callback(CRAWLER_SEEDINGSTATS_QUERY, cPickle.dumps(sql_update, 2))

    def handle_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'crawler: handle_crawler_request', len(message)
        results = []
        try:
            items = cPickle.loads(message)
            if DEBUG:
                print >> sys.stderr, 'crawler: handle_crawler_request', items
            for action, query in items:
                if action == 'read':
                    cursor = self._sqlite_cache_db.execute_read(query)
                elif action == 'write':
                    cursor = self._sqlite_cache_db.execute_write(query)
                else:
                    raise Exception('invalid payload')
                if cursor:
                    results.append(list(cursor))
                else:
                    results.append(None)

        except Exception as e:
            if DEBUG:
                print >> sys.stderr, 'crawler: handle_crawler_request', e
            results.append(str(e))
            reply_callback(cPickle.dumps(results, 2), 1)
        else:
            reply_callback(cPickle.dumps(results, 2))

        return True

    def handle_crawler_reply(self, permid, selversion, channel_id, channel_data, error, message, reply_callback):
        if error:
            if DEBUG:
                print >> sys.stderr, 'seedingstatscrawler: handle_crawler_reply'
                print >> sys.stderr, 'seedingstatscrawler: error', error
        else:
            try:
                results = cPickle.loads(message)
                if DEBUG:
                    print >> sys.stderr, 'seedingstatscrawler: handle_crawler_reply'
                    print >> sys.stderr, 'seedingstatscrawler:', results
                if results[0]:
                    values = map(tuple, results[0])
                    self._sqlite_cache_db.insertMany('SeedingStats', values)
            except Exception as e:
                f = open('seedingstats-EOFError.data', 'ab')
                f.write('--\n%s\n--\n' % message)
                f.close()
                print_exc()
                return False

        return True

    def handle_crawler_update_settings_request(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'crawler: handle_crawler_SeedingStats_request', message
        sql_update = cPickle.loads(message)
        try:
            self._sqlite_cache_db.execute_write(sql_update)
        except Exception as e:
            reply_callback(str(e), 1)
        else:
            reply_callback(cPickle.dumps('Update succeeded.', 2))

        return True

    def handle_crawler_update_setings_reply(self, permid, selversion, channel_id, message, reply_callback):
        if DEBUG:
            print >> sys.stderr, 'olapps: handle_crawler_SeedingStats_reply'
        return True
