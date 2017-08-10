#Embedded file name: ACEStream\Core\DecentralizedTracking\mainlineDHTChecker.pyo
import sys
from threading import currentThread
from ACEStream.Core.CacheDB.CacheDBHandler import TorrentDBHandler
DEBUG = False

class mainlineDHTChecker:
    __single = None

    def __init__(self):
        if DEBUG:
            print >> sys.stderr, 'mainlineDHTChecker: initialization'
        if mainlineDHTChecker.__single:
            raise RuntimeError, 'mainlineDHTChecker is Singleton'
        mainlineDHTChecker.__single = self
        self.dht = None
        self.torrent_db = TorrentDBHandler.getInstance()

    def getInstance(*args, **kw):
        if mainlineDHTChecker.__single is None:
            mainlineDHTChecker(*args, **kw)
        return mainlineDHTChecker.__single

    getInstance = staticmethod(getInstance)

    def register(self, dht):
        self.dht = dht

    def lookup(self, infohash):
        if DEBUG:
            print >> sys.stderr, 'mainlineDHTChecker: Lookup', `infohash`
        if self.dht is not None:
            from ACEStream.Core.DecentralizedTracking.pymdht.core.identifier import Id, IdError
            try:
                infohash_id = Id(infohash)
                self.dht.get_peers(infohash, infohash_id, self.got_peers_callback)
            except IdError:
                print >> sys.stderr, 'Rerequester: _dht_rerequest: self.info_hash is not a valid identifier'
                return

        elif DEBUG:
            print >> sys.stderr, 'mainlineDHTChecker: No lookup, no DHT support loaded'

    def got_peers_callback(self, infohash, peers):
        if DEBUG:
            if peers:
                print >> sys.stderr, 'mainlineDHTChecker: Got', len(peers), 'peers for torrent', `infohash`, currentThread().getName()
            else:
                print >> sys.stderr, 'mainlineDHTChecker: Got no peers for torrent', `infohash`, currentThread().getName()
        if peers:
            torrent = self.torrent_db.getTorrent(infohash)
            if torrent['status'] != 'good':
                status = 'good'
                kw = {'status': status}
                self.torrent_db.updateTorrent(infohash, commit=True, **kw)
