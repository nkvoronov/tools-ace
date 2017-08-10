#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\message.pyo
import sys
import threading
import logging
import bencode
from identifier import Id, ID_SIZE_BYTES, IdError
from node import Node
import message_tools as mt
private_dht_name = None
logger = logging.getLogger('dht')
NEXTSHARE_VERSION = 'NS\x01\x18'
TYPE = 'y'
ARGS = 'a'
RESPONSE = 'r'
ERROR = 'e'
TID = 't'
QUERY = 'q'
VERSION = 'v'
QUERY = 'q'
RESPONSE = 'r'
ERROR = 'e'
PING = 'ping'
FIND_NODE = 'find_node'
GET_PEERS = 'get_peers'
ANNOUNCE_PEER = 'announce_peer'
ID = 'id'
TARGET = 'target'
INFO_HASH = 'info_hash'
PORT = 'port'
TOKEN = 'token'
ID = 'id'
NODES = 'nodes'
NODES2 = 'nodes2'
TOKEN = 'token'
PEERS = VALUES = 'values'
GENERIC_E = [201, 'Generic Error']
SERVER_E = [202, 'Server Error']
PROTOCOL_E = [203, 'Protocol Error']
UNKNOWN_E = [201, 'Method Unknown']

def matching_tid(query_tid, response_tid):
    return query_tid[0] == response_tid[0]


class MsgError(Exception):
    pass


class OutgoingMsgBase(object):

    def __init__(self):
        self._dict = {VERSION: NEXTSHARE_VERSION}
        if private_dht_name:
            self._dict['d'] = private_dht_name
        self._lock = threading.RLock()

    def __str__(self):
        return str(self._dict)

    def __repr__(self):
        return str(self.__class__) + str(self)

    def encode(self, tid):
        self._lock.acquire()
        self._dict[TID] = tid
        result = bencode.encode(self._dict)
        del self._dict[TID]
        self._lock.release()
        return result


class OutgoingQueryBase(OutgoingMsgBase):

    def __init__(self, sender_id):
        OutgoingMsgBase.__init__(self)
        self._dict[TYPE] = QUERY
        self._dict[ARGS] = {ID: str(sender_id)}

    @property
    def query(self):
        return self._dict[QUERY]


class OutgoingPingQuery(OutgoingQueryBase):

    def __init__(self, sender_id):
        OutgoingQueryBase.__init__(self, sender_id)
        self._dict[QUERY] = PING


class OutgoingFindNodeQuery(OutgoingQueryBase):

    def __init__(self, sender_id, target):
        OutgoingQueryBase.__init__(self, sender_id)
        self._dict[QUERY] = FIND_NODE
        self._dict[ARGS][TARGET] = str(target)


class OutgoingGetPeersQuery(OutgoingQueryBase):

    def __init__(self, sender_id, info_hash):
        OutgoingQueryBase.__init__(self, sender_id)
        self._dict[QUERY] = GET_PEERS
        self._dict[ARGS][INFO_HASH] = str(info_hash)


class OutgoingAnnouncePeerQuery(OutgoingQueryBase):

    def __init__(self, sender_id, info_hash, port, token):
        OutgoingQueryBase.__init__(self, sender_id)
        self._dict[QUERY] = ANNOUNCE_PEER
        self._dict[ARGS][INFO_HASH] = str(info_hash)
        self._dict[ARGS][PORT] = port
        self._dict[ARGS][TOKEN] = token


class OutgoingResponseBase(OutgoingMsgBase):

    def __init__(self, sender_id):
        OutgoingMsgBase.__init__(self)
        self._dict[TYPE] = RESPONSE
        self._dict[RESPONSE] = {ID: str(sender_id)}


class OutgoingPingResponse(OutgoingResponseBase):

    def __init__(self, sender_id):
        OutgoingResponseBase.__init__(self, sender_id)


class OutgoingFindNodeResponse(OutgoingResponseBase):

    def __init__(self, sender_id, nodes):
        OutgoingResponseBase.__init__(self, sender_id)
        self._dict[RESPONSE][NODES] = mt.compact_nodes(nodes)


class OutgoingGetPeersResponse(OutgoingResponseBase):

    def __init__(self, sender_id, token = None, nodes = None, peers = None):
        OutgoingResponseBase.__init__(self, sender_id)
        if token:
            self._dict[RESPONSE][TOKEN] = token
        if nodes:
            self._dict[RESPONSE][NODES] = mt.compact_nodes(nodes)
        if peers:
            self._dict[RESPONSE][VALUES] = mt.compact_peers(peers)


class OutgoingAnnouncePeerResponse(OutgoingResponseBase):

    def __init__(self, sender_id):
        OutgoingResponseBase.__init__(self, sender_id)


class OutgoingErrorMsg(OutgoingMsgBase):

    def __init__(self, error):
        OutgoingMsgBase.__init__(self)
        self._dict[TYPE] = ERROR
        self._dict[ERROR] = error


class IncomingMsg(object):

    def __init__(self, bencoded_msg, sender_addr):
        self.sender_addr = sender_addr
        try:
            self._msg_dict = bencode.decode(bencoded_msg)
            self._sanitize_common()
            if self.type == QUERY:
                self._sanitize_query()
            elif self.type == RESPONSE:
                self._sanitize_response()
            elif self.type == ERROR:
                self._sanitize_error()
            else:
                raise MsgError, 'Unknown TYPE value'
        except MsgError:
            raise
        except:
            logger.warning('This bencoded message is broken:\n%s' % repr(bencoded_msg))
            raise MsgError, 'Invalid message'

    def __repr__(self):
        return repr(self._msg_dict)

    def _get_value(self, k, kk = None, optional = False):
        try:
            v = self._msg_dict[k]
            if kk:
                v = v[kk]
        except KeyError:
            if optional:
                return None
            raise MsgError, 'Non-optional key (%s:%s) not found' % (k, kk)
        except TypeError:
            raise MsgError, 'Probably k (%r) is not a dictionary' % k

        return v

    def _get_str(self, k, kk = None, optional = False):
        v = self._get_value(k, kk, optional)
        if v is None:
            return
        if not isinstance(v, str):
            raise MsgError, 'Value (%s:%s,%s) must be a string' % (k, kk, v)
        return v

    def _get_id(self, k, kk = None):
        try:
            v = self._get_value(k, kk)
            v = Id(v)
        except IdError:
            raise MsgError, 'Value (%s:%s,%s) must be a valid Id' % (k, kk, v)

        return v

    def _get_int(self, k, kk = None):
        v = self._get_value(k, kk)
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise MsgError, 'Value (%s:%s,%s) must be an int' % (k, kk, v)

        return v

    def _sanitize_common(self):
        try:
            self.tid = self._msg_dict[TID]
        except TypeError:
            raise MsgError, 'decoded data is not a dictionary'
        except KeyError:
            raise MsgError, 'key TID not found'

        if not (isinstance(self.tid, str) and self.tid):
            raise MsgError, 'TID must be a non-empty binary string'
        try:
            self.type = self._msg_dict[TYPE]
        except KeyError:
            raise MsgError, 'key TYPE not found'

        if private_dht_name:
            try:
                if self._msg_dict['d'] != private_dht_name:
                    raise MsgError, 'invalid private DHT name'
            except (KeyError, TypeError):
                raise MsgError, 'invalid private DHT name'

        self.version = self._get_str(VERSION, optional=True)
        self.ns_node = self.version and self.version.startswith(NEXTSHARE_VERSION[:2])

    def _sanitize_query(self):
        self.sender_id = self._get_id(ARGS, ID)
        self.sender_node = Node(self.sender_addr, self.sender_id)
        self.query = self._get_str(QUERY)
        if self.query in [GET_PEERS, ANNOUNCE_PEER]:
            self.info_hash = self._get_id(ARGS, INFO_HASH)
            if self.query == ANNOUNCE_PEER:
                self.bt_port = self._get_int(ARGS, PORT)
                self.token = self._get_str(ARGS, TOKEN)
        elif self.query == FIND_NODE:
            self.target = self._get_id(ARGS, TARGET)

    def _sanitize_response(self):
        self.sender_id = self._get_id(RESPONSE, ID)
        self.sender_node = Node(self.sender_addr, self.sender_id)
        self.all_nodes = []
        c_nodes = self._get_str(RESPONSE, NODES, optional=True)
        if c_nodes:
            self.nodes = mt.uncompact_nodes(c_nodes)
            self.all_nodes = self.nodes
        try:
            c_nodes2 = self._msg_dict[RESPONSE][NODES2]
        except KeyError:
            self.nodes2 = None
        else:
            self.nodes2 = mt.uncompact_nodes2(c_nodes2)
            for n in self.nodes2:
                if n not in self.all_nodes:
                    self.all_nodes.append(n)

        self.token = self._get_str(RESPONSE, TOKEN, optional=True)
        self.peers = None
        c_peers = self._get_value(RESPONSE, PEERS, optional=True)
        if c_peers:
            self.peers = mt.uncompact_peers(c_peers)

    def _sanitize_error(self):
        try:
            self.error = [int(self._msg_dict[ERROR][0]), str(self._msg_dict[ERROR][1])]
        except:
            raise MsgError, 'Invalid error message'
