#Embedded file name: ACEStream\Core\NATFirewall\UDPPuncture.pyo
import guessip
import time
import socket
import sys
import errno
import random
from collections import deque
import TimeoutFinder
import os
DEBUG = False
if sys.platform == 'win32':
    SOCKET_BLOCK_ERRORCODE = 10035
else:
    SOCKET_BLOCK_ERRORCODE = errno.EWOULDBLOCK

class UDPHandler():
    TRACKER_ADDRESS = 'm23trial-udp.tribler.org'
    CONNECT = chr(0)
    YOUR_IP = chr(1)
    FW_CONNECT_REQ = chr(2)
    REV_CONNECT = chr(3)
    PEX_ADD = chr(4)
    PEX_DEL = chr(5)
    CLOSE = chr(6)
    UPDATE_NATFW_STATE = chr(7)
    PEER_UNKNOWN = chr(8)
    KEEP_ALIVE = chr(9)
    CLOSE_NORMAL = chr(0)
    CLOSE_TOO_MANY = chr(1)
    CLOSE_LEN = chr(2)
    CLOSE_PROTO_VER, = chr(3)
    CLOSE_GARBAGE = chr(4)
    CLOSE_NOT_CONNECTED = chr(5)
    CLOSE_STATE_CORRUPT = chr(6)
    NAT_UNKNOWN, NAT_NONE, NAT_APDM = range(0, 3)
    FILTER_UNKNOWN, FILTER_NONE, FILTER_APDF = range(0, 3)
    RECV_CONNECT_THRESHOLD = 4
    RECV_CONNECT_SCALE_THRESHOLD = 64
    FIXED_THRESHOLD = 7

    def __init__(self, rawserver, check_crawler, port = 0):
        self.connections = {}
        if check_crawler:
            from ACEStream.Core.Statistics.Crawler import Crawler
            crawler = Crawler.get_instance()
            if crawler.am_crawler():
                return
        self.connections = {}
        self.rawserver = rawserver
        self.socket = rawserver.create_udpsocket(port, '0.0.0.0')
        self.known_peers = {}
        self.nat_type = UDPHandler.NAT_UNKNOWN
        self.filter_type = UDPHandler.FILTER_UNKNOWN
	current_file_path = os.path.dirname(os.path.realpath(__file__))
	maxconnections_file = os.path.join(os.path.split(os.path.split(current_file_path)[0])[0],"values","maxconnections.txt")
	f = open(maxconnections_file, "r")
	string = f.read()
        self.max_connections = int(string)
        self.connect_threshold = 75
        self.recv_unsolicited = 0
        self.recv_connect_total = 0
        self.recv_address = 0
        self.recv_different_address = 0
        self.sendqueue = deque([])
        self.last_connect = 0
        self.last_info_dump = time.time()
        self.natfw_version = 1
        self.keepalive_intvl = 100
        self.done = False
        self.reporter = None
        self.last_sends = {}
        rawserver.start_listening_udp(self.socket, self)
        if port == 9473:
            self.tracker = True
            self.id = '\x00\x00\x00\x00'
            self.max_connections = 1000
            rawserver.add_task(self.check_for_timeouts, 10)
        else:
            self.tracker = False
            self.id = chr(random.getrandbits(8)) + chr(random.getrandbits(8)) + chr(random.getrandbits(8)) + chr(random.getrandbits(8))
            if DEBUG:
                debug('My ID: %s' % self.id.encode('hex'))
            rawserver.add_task(self.bootstrap, 5)
            TimeoutFinder.TimeoutFinder(rawserver, False, self.timeout_report)
            TimeoutFinder.TimeoutFinder(rawserver, True, self.timeout_report)
            if not DEBUG:
                if check_crawler:
                    from ACEStream.Core.Statistics.PunctureCrawler import get_reporter_instance
                self.reporter = get_reporter_instance()
        if self.reporter:
            my_wan_ip = guessip.get_my_wan_ip()
            if my_wan_ip == None and sys.platform == 'win32':
                try:
                    import os
                    for line in os.popen('netstat -nr').readlines():
                        words = line.split()
                        if words[0] == '0.0.0.0':
                            my_wan_ip = words[3]
                            break

                except:
                    pass

            if my_wan_ip == None:
                my_wan_ip = 'Unknown'
            self.reporter.add_event('UDPPuncture', 'ID:%s;IP:%s' % (self.id.encode('hex'), my_wan_ip))

    def shutdown(self):
        self.done = True
        for connection in self.connections.values():
            self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_NORMAL, connection.address)
            self.delete_closed_connection(connection)

    def data_came_in(self, packets):
        for address, data in packets:
            if DEBUG:
                debug('Data came (%d) in from address %s:%d' % (ord(data[0]), address[0], address[1]))
            connection = self.connections.get(address)
            if not connection:
                if data[0] == UDPHandler.CLOSE:
                    continue
                if data[0] != UDPHandler.CONNECT:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_NOT_CONNECTED, address)
                    continue
                if len(data) != 8:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN, address)
                    continue
                if data[1] != chr(0):
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_PROTO_VER, address)
                    continue
                if self.check_connection_count():
                    if self.reporter:
                        self.reporter.add_event('UDPPuncture', 'OCTM:%s,%d,%s' % (address[0], address[1], data[2:6].encode('hex')))
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_TOO_MANY, address)
                    continue
                id = data[2:6]
                connection = self.known_peers.get(id)
                if not connection:
                    connection = UDPConnection(address, id, self)
                    self.known_peers[id] = connection
                elif connection.address != address:
                    if connection.connection_state == UDPConnection.CONNECT_ESTABLISHED:
                        self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_STATE_CORRUPT, address)
                        continue
                    try:
                        del self.connections[connection.address]
                    except:
                        pass

                    connection.address = address
                if address not in self.last_sends:
                    self.incoming_connect(address, True)
                self.connections[address] = connection
            if not connection.handle_msg(data):
                self.delete_closed_connection(connection)

    def check_connection_count(self):
        if len(self.connections) < self.max_connections:
            return False
        if DEBUG:
            debug('  Connection threshold reached, trying to find an old connection')
        oldest = None
        oldest_time = 1e+308
        for connection in self.connections.itervalues():
            if not connection.tracker and connection.connected_since < oldest_time:
                oldest_time = connection.connected_since
                oldest = connection

        if not oldest:
            return True
        if not self.tracker and oldest.connected_since > time.time() - 300:
            if DEBUG:
                debug('  All connections are under 5 minutes old')
            return True
        if DEBUG:
            debug('  Closing connection to %s %s:%d' % (oldest.id.encode('hex'), oldest.address[0], oldest.address[1]))
        oldest.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_NORMAL)
        self.delete_closed_connection(oldest)
        return False

    def incoming_connect(self, address, unsolicited):
        if self.tracker:
            return
        if unsolicited:
            self.recv_unsolicited += 1
        self.recv_connect_total += 1
        if self.recv_connect_total > UDPHandler.RECV_CONNECT_SCALE_THRESHOLD:
            self.recv_connect_total >>= 1
            self.recv_unsolicited >>= 1
        if self.recv_connect_total > UDPHandler.RECV_CONNECT_THRESHOLD:
            if DEBUG:
                debug('Setting filter state (recv total %d, recv unsol %d)' % (self.recv_connect_total, self.recv_unsolicited))
            update_filter = False
            if self.recv_unsolicited > self.recv_connect_total / 2 or self.recv_unsolicited > UDPHandler.FIXED_THRESHOLD:
                if self.filter_type != UDPHandler.FILTER_NONE or self.nat_type != UDPHandler.NAT_NONE:
                    update_filter = True
                    self.filter_type = UDPHandler.FILTER_NONE
                    self.nat_type = UDPHandler.NAT_NONE
            elif self.filter_type != UDPHandler.FILTER_APDF:
                update_filter = True
                self.filter_type = UDPHandler.FILTER_APDF
            if update_filter:
                self.natfw_version += 1
                if self.natfw_version > 255:
                    self.natfw_version = 0
                if self.reporter:
                    self.reporter.add_event('UDPPuncture', 'UNAT:%d,%d,%d' % (self.nat_type, self.filter_type, self.natfw_version))
                map(lambda x: x.readvertise_nat(), self.connections.itervalues())

    def incoming_ip(self, address):
        if self.tracker:
            return
        self.recv_address += 1
        if self.recv_address == 1:
            self.reported_wan_address = address
            return
        if self.recv_address > UDPHandler.RECV_CONNECT_SCALE_THRESHOLD:
            self.recv_address >>= 1
            self.recv_different_address >>= 1
        if self.reported_wan_address != address:
            self.reported_wan_address = address
            self.recv_different_address += 1
        if self.recv_address > UDPHandler.RECV_CONNECT_THRESHOLD:
            if DEBUG:
                debug('Setting nat state (recv addr %d, recv diff %d)' % (self.recv_address, self.recv_different_address))
            update_nat = False
            if self.recv_different_address > self.recv_address / 2:
                if self.nat_type != UDPHandler.NAT_APDM:
                    update_nat = True
                    self.nat_type = UDPHandler.NAT_APDM
                    self.filter_type = UDPHandler.FILTER_APDF
            elif self.nat_type != UDPHandler.NAT_NONE:
                update_nat = True
                self.nat_type = UDPHandler.NAT_NONE
            if update_nat:
                self.natfw_version += 1
                if self.natfw_version > 255:
                    self.natfw_version = 0
                if self.reporter:
                    self.reporter.add_event('UDPPuncture', 'UNAT:%d,%d,%d' % (self.nat_type, self.filter_type, self.natfw_version))
                map(lambda x: x.readvertise_nat(), self.connections.itervalues())

    def bootstrap(self):
        if DEBUG:
            debug('Starting bootstrap')
        try:
            address = socket.gethostbyname(UDPHandler.TRACKER_ADDRESS)
        except:
            return

        if address == '130.161.211.245':
            return
        tracker = UDPConnection((address, 9473), '\x00\x00\x00\x00', self)
        tracker.advertised_by[('0.0.0.0', 0)] = 1e+308
        tracker.nat_type = UDPHandler.NAT_NONE
        tracker.filter_type = UDPHandler.FILTER_NONE
        tracker.tracker = True
        self.known_peers[tracker.id] = tracker
        self.check_for_timeouts()

    def sendto(self, data, address):
        if DEBUG:
            debug('Sending data (%d) to address %s:%d' % (ord(data[0]), address[0], address[1]))
        if len(self.sendqueue) > 0:
            self.sendqueue.append((data, address))
            return
        try:
            self.socket.sendto(data, address)
        except socket.error as error:
            if error[0] == SOCKET_BLOCK_ERRORCODE:
                self.sendqueue.append((data, address))
                self.rawserver.add_task(self.process_sendqueue, 0.1)

    def process_sendqueue(self):
        while len(self.sendqueue) > 0:
            data, address = self.sendqueue[0]
            try:
                self.socket.sendto(data, address)
            except socket.error as error:
                if error[0] == SOCKET_BLOCK_ERRORCODE:
                    self.rawserver.add_task(self.process_sendqueue, 0.1)
                    return

            self.sendqueue.popleft()

    def check_nat_compatible(self, peer):
        if self.nat_type == UDPHandler.NAT_APDM and peer.filter_type == UDPHandler.FILTER_APDF:
            return False
        return True

    def check_for_timeouts(self):
        if self.done:
            return
        now = time.time()
        close_list = []
        for address in self.last_sends.iterkeys():
            if self.last_sends[address] < now - 300:
                close_list.append(address)

        for address in close_list:
            del self.last_sends[address]

        if not self.tracker and len(self.connections) >= self.connect_threshold:
            if DEBUG:
                debug('Closing connections older than 10 minutes')
            close_list = []
            for connection in self.connections.itervalues():
                if not connection.tracker and connection.connected_since < now - 600:
                    if DEBUG:
                        debug('  Closing connection to %s %s:%d' % (connection.id.encode('hex'), connection.address[0], connection.address[1]))
                    close_list.append(connection)

            for connection in close_list:
                connection.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_NORMAL)
                self.delete_closed_connection(connection)
                if len(self.connections) < self.connect_threshold / 1.5:
                    break

        if not self.tracker and len(self.connections) < self.connect_threshold and self.last_connect < now - 20:
            unconnected_peers = list(set(self.known_peers.iterkeys()) - set(ConnectionIteratorByID(self.connections)))
            random.shuffle(unconnected_peers)
            while len(unconnected_peers) > 0:
                peer = self.known_peers[unconnected_peers.pop()]
                if peer.connection_state != UDPConnection.CONNECT_NONE:
                    continue
                if not self.check_nat_compatible(peer):
                    continue
                if peer.last_comm > now - 300:
                    continue
                if not self.try_connect(peer):
                    continue
                self.last_connect = now
                break

        need_advert_time = now - self.keepalive_intvl
        timeout_time = now - 250
        can_advert_time = now - 30
        close_list = []
        pex_only = 0
        for connection in self.connections.itervalues():
            if connection.connection_state == UDPConnection.CONNECT_SENT and connection.last_received < can_advert_time:
                if connection.connection_tries < 0:
                    if DEBUG:
                        debug('Dropping connection with %s:%d (timeout)' % (connection.address[0], connection.address[1]))
                    close_list.append(connection)
                elif not self.try_connect(connection):
                    if DEBUG:
                        debug('Too many retries %s:%d' % (connection.address[0], connection.address[1]))
                    close_list.append(connection)
            elif connection.last_received < timeout_time:
                if DEBUG:
                    debug('Dropping connection with %s:%d (timeout)' % (connection.address[0], connection.address[1]))
                close_list.append(connection)

        for connection in close_list:
            self.delete_closed_connection(connection)

        for connection in self.connections.itervalues():
            if connection.last_send < need_advert_time:
                if connection.advertise_nat or len(connection.pex_add) != 0 or len(connection.pex_del) != 0:
                    connection.send_pex() or connection.sendto(UDPHandler.KEEP_ALIVE)
                else:
                    connection.sendto(UDPHandler.KEEP_ALIVE)
            elif connection.advertise_nat or (len(connection.pex_add) != 0 or len(connection.pex_del) != 0) and connection.last_advert < can_advert_time and pex_only < 35:
                if connection.send_pex():
                    pex_only += 1

        self.rawserver.add_task(self.check_for_timeouts, 10)
        if DEBUG:
            if self.last_info_dump + 60 < now:
                self.last_info_dump = now
                for connection in self.known_peers.itervalues():
                    msg = 'Peer %d %s %s:%d,%d,%d: Advertisers:' % (connection.connection_state,
                     connection.id.encode('hex'),
                     connection.address[0],
                     connection.address[1],
                     connection.nat_type,
                     connection.filter_type)
                    for advertiser in connection.advertised_by.iterkeys():
                        msg += ' %s:%d' % (advertiser[0], advertiser[1])

                    debug(msg)

    def try_connect(self, peer):
        if peer.filter_type != UDPHandler.FILTER_NONE and len(peer.advertised_by) == 0:
            return False
        if peer.connection_tries > 2:
            return False
        peer.connection_tries += 1
        if DEBUG:
            debug('Found compatible peer at %s:%d attempt %d' % (peer.address[0], peer.address[1], peer.connection_tries))
        if self.reporter:
            self.reporter.add_event('UDPPuncture', 'OCON%d:%s,%d,%s,%d,%d,%d' % (peer.connection_tries,
             peer.address[0],
             peer.address[1],
             peer.id.encode('hex'),
             peer.nat_type,
             peer.filter_type,
             peer.natfw_version))
        peer.sendto(UDPHandler.CONNECT + chr(0) + self.id + natfilter_to_byte(self.nat_type, self.filter_type) + chr(self.natfw_version))
        if peer.filter_type != UDPHandler.FILTER_NONE:
            if DEBUG:
                debug('Rendez-vous needed')
            rendezvous_peers = list(peer.advertised_by.iterkeys())
            random.shuffle(rendezvous_peers)
            rendezvous_addr = rendezvous_peers[0]
            rendezvous = self.connections.get(rendezvous_addr)
            if rendezvous:
                if self.reporter:
                    self.reporter.add_event('UDPPuncture', 'OFWC:%s,%d,%s,%s' % (rendezvous.address[0],
                     rendezvous.address[1],
                     rendezvous.id.encode('hex'),
                     peer.id.encode('hex')))
                rendezvous.sendto(UDPHandler.FW_CONNECT_REQ + peer.id)
        peer.connection_state = UDPConnection.CONNECT_SENT
        peer.last_received = time.time()
        self.connections[peer.address] = peer
        return True

    def delete_closed_connection(self, connection):
        del self.connections[connection.address]
        orig_state = connection.connection_state
        connection.connection_state = UDPConnection.CONNECT_NONE
        connection.last_comm = time.time()
        if connection.last_send > time.time() - 300:
            self.last_sends[connection.address] = connection.last_send
        connection.last_send = 0
        connection.last_received = 0
        connection.last_advert = 0
        if connection.id == '\x00\x00\x00\x00':
            connection.nat_type = UDPHandler.NAT_NONE
            connection.filter_type = UDPHandler.FILTER_NONE
            connection.natfw_version = 0
        else:
            connection.nat_type = UDPHandler.NAT_UNKNOWN
            connection.filter_type = UDPHandler.FILTER_UNKNOWN
            connection.natfw_version = 0
            connection.pex_add.clear()
            connection.pex_del.clear()
            connection.connection_tries = -1
        if len(connection.advertised_by) == 0:
            try:
                del self.known_peers[connection.id]
            except:
                pass

        map(lambda x: x.remove_advertiser(connection.address), self.known_peers.itervalues())
        if orig_state == UDPConnection.CONNECT_ESTABLISHED:
            map(lambda x: x.pex_del.append(connection), self.connections.itervalues())

    def timeout_report(self, timeout, initial_ping):
        if DEBUG:
            debug('Timeout reported: %d %d' % (timeout, initial_ping))
        if self.reporter:
            self.reporter.add_event('UDPPuncture', 'TOUT:%d,%d' % (timeout, initial_ping))
        if initial_ping:
            if timeout > 45 and timeout - 15 < self.keepalive_intvl:
                self.keepalive_intvl = timeout - 15


class ConnectionIteratorByID():

    def __init__(self, connections):
        self.value_iterator = connections.itervalues()

    def __iter__(self):
        return self

    def next(self):
        value = self.value_iterator.next()
        return value.id


class UDPConnection():
    CONNECT_NONE, CONNECT_SENT, CONNECT_ESTABLISHED = range(0, 3)

    def __init__(self, address, id, handler):
        self.address = address
        self.handler = handler
        self.connection_state = UDPConnection.CONNECT_NONE
        self.nat_type = UDPHandler.NAT_UNKNOWN
        self.filter_type = UDPHandler.FILTER_UNKNOWN
        self.natfw_version = 0
        self.advertised_by = {}
        self.pex_add = deque([])
        self.pex_del = deque([])
        self.last_comm = 0
        self.last_send = 0
        self.last_advert = 0
        self.last_received = 0
        self.connected_since = 0
        self.advertise_nat = False
        self.tracker = False
        self.id = id
        self.connection_tries = -1

    def sendto(self, data):
        self.handler.sendto(data, self.address)
        self.last_send = time.time()

    def handle_msg(self, data):
        self.last_received = time.time()
        if data[0] == UDPHandler.CONNECT:
            if DEBUG:
                debug('  Message %d' % ord(data[0]))
            if len(data) != 8:
                self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                return False
            if ord(data[1]) != 0:
                self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_PROTO_VER)
                return False
            if data[2:6] != self.id or self.connection_state == UDPConnection.CONNECT_ESTABLISHED:
                self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_STATE_CORRUPT)
                return False
            if self.handler.reporter:
                self.handler.reporter.add_event('UDPPuncture', 'ICON-AC:%s,%d,%s' % (self.address[0], self.address[1], data[2:6].encode('hex')))
            if self.handler.tracker:
                peers = self.handler.connections.values()
                random.shuffle(peers)
                self.pex_add.extend(peers)
            else:
                self.pex_add.extend(self.handler.connections.itervalues())
            self.connected_since = time.time()
            message = UDPHandler.YOUR_IP + address_to_string(self.address)
            message += self.pex_string(self.pex_add, 1024 - len(message), True)
            self.sendto(message)
            self.last_advert = self.connected_since
            self.nat_type, self.filter_type = byte_to_natfilter(data[6])
            self.natfw_version = ord(data[7])
            self.connection_state = UDPConnection.CONNECT_ESTABLISHED
            map(lambda x: x.pex_add.append(self), self.handler.connections.itervalues())
            self.pex_add.pop()
            return True
        if self.connection_state == UDPConnection.CONNECT_NONE:
            return False
        while len(data) > 0:
            if DEBUG:
                debug('  Message %d len %d' % (ord(data[0]), len(data)))
            if data[0] == UDPHandler.YOUR_IP:
                if len(data) < 7:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                my_addres = string_to_address(data[1:7])
                if DEBUG:
                    debug('    My IP: %s:%d' % (my_addres[0], my_addres[1]))
                if self.handler.reporter:
                    self.handler.reporter.add_event('UDPPuncture', 'IYIP:%s,%d,%s' % (my_addres[0], my_addres[1], self.id.encode('hex')))
                self.handler.incoming_ip(my_addres)
                if self.connection_state == UDPConnection.CONNECT_SENT:
                    self.pex_add.extend(self.handler.connections.itervalues())
                    message = UDPHandler.YOUR_IP + address_to_string(self.address)
                    message += self.pex_string(self.pex_add, 1024 - len(message), True)
                    self.sendto(message)
                    self.last_advert = time.time()
                    self.connected_since = time.time()
                    self.connection_state = UDPConnection.CONNECT_ESTABLISHED
                    map(lambda x: x.pex_add.append(self), self.handler.connections.itervalues())
                    self.pex_add.pop()
                data = data[7:]
            elif data[0] == UDPHandler.FW_CONNECT_REQ:
                if len(data) < 5:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                remote = data[1:5]
                connection = self.handler.known_peers.get(remote)
                if connection:
                    if DEBUG:
                        debug('    Rendez vous requested for peer %s %s:%d' % (remote.encode('hex'), connection.address[0], connection.address[1]))
                    if self.handler.reporter:
                        self.handler.reporter.add_event('UDPPuncture', 'IFRQ:%s,%d,%s,%s,%d,%s' % (self.address[0],
                         self.address[1],
                         self.id.encode('hex'),
                         connection.address[0],
                         connection.address[1],
                         remote.encode('hex')))
                else:
                    if DEBUG:
                        debug('    Rendez vous requested for peer %s (unknown)' % remote.encode('hex'))
                    if self.handler.reporter:
                        self.handler.reporter.add_event('UDPPuncture', 'IFRQ:%s,%d,%s,Unknown,Unknown,%s' % (self.address[0],
                         self.address[1],
                         self.id.encode('hex'),
                         remote.encode('hex')))
                if connection:
                    connection.sendto(UDPHandler.REV_CONNECT + self.id + address_to_string(self.address) + natfilter_to_byte(self.nat_type, self.filter_type) + chr(self.natfw_version))
                else:
                    self.sendto(UDPHandler.PEER_UNKNOWN + remote)
                data = data[5:]
            elif data[0] == UDPHandler.REV_CONNECT:
                if len(data) < 13:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                remote = string_to_address(data[5:11])
                if self.handler.reporter:
                    self.handler.reporter.add_event('UDPPuncture', 'IRRQ:%s,%d,%s,%s,%d,%s' % (self.address[0],
                     self.address[1],
                     self.id.encode('hex'),
                     remote[0],
                     remote[1],
                     data[1:5].encode('hex')))
                connection = self.handler.connections.get(remote)
                if connection:
                    pass
                elif self.handler.check_connection_count():
                    if self.handler.reporter:
                        self.handler.reporter.add_event('UDPPuncture', 'OCTM-IRRQ:%s,%d,%s' % (connection.address[0], connection.address[1], connection.id.encode('hex')))
                    self.handler.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_TOO_MANY, remote)
                else:
                    self.handler.incoming_connect(remote, False)
                    remote_id = data[1:5]
                    connection = self.handler.known_peers.get(remote_id)
                    if not connection:
                        connection = UDPConnection(remote, remote_id, self.handler)
                        self.handler.known_peers[remote_id] = connection
                    elif connection.address != remote:
                        self.sendto(UDPHandler.PEER_UNKNOWN + remote_id)
                        data = data[13:]
                        continue
                    if compare_natfw_version(ord(data[12]), connection.natfw_version):
                        connection.nat_type, connection.filter_type = byte_to_natfilter(data[11])
                        connection.natfw_version = ord(data[12])
                    self.handler.connections[remote] = connection
                    connection.connection_state = UDPConnection.CONNECT_SENT
                    if self.handler.reporter:
                        self.handler.reporter.add_event('UDPPuncture', 'OCON-IRRQ:%s,%d,%s' % (connection.address[0], connection.address[1], connection.id.encode('hex')))
                    connection.sendto(UDPHandler.CONNECT + chr(0) + self.handler.id + natfilter_to_byte(self.handler.nat_type, self.handler.filter_type) + chr(self.natfw_version))
                data = data[13:]
            elif data[0] == UDPHandler.PEX_ADD:
                if len(data) < 2:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                addresses = ord(data[1])
                if len(data) < 2 + 12 * addresses:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                for i in range(0, addresses):
                    id = data[2 + i * 12:2 + i * 12 + 4]
                    address = string_to_address(data[2 + i * 12 + 4:2 + i * 12 + 10])
                    peer = self.handler.known_peers.get(id)
                    if not peer:
                        peer = UDPConnection(address, id, self.handler)
                        peer.natfw_version = ord(data[2 + i * 12 + 11])
                        peer.nat_type, peer.filter_type = byte_to_natfilter(data[2 + i * 12 + 10])
                        self.handler.known_peers[id] = peer
                    peer.advertised_by[self.address] = time.time()
                    if DEBUG:
                        nat_type, filter_type = byte_to_natfilter(data[2 + i * 12 + 10])
                        debug('    Received peer %s %s:%d NAT/fw:%d,%d' % (id.encode('hex'),
                         address[0],
                         address[1],
                         nat_type,
                         filter_type))
                    if compare_natfw_version(ord(data[2 + i * 12 + 11]), peer.natfw_version):
                        peer.natfw_version = ord(data[2 + i * 12 + 11])
                        peer.nat_type, peer.filter_type = byte_to_natfilter(data[2 + i * 12 + 10])
                        if peer.connection_state == UDPConnection.CONNECT_ESTABLISHED:
                            map(lambda x: x.pex_add.append(peer), self.handler.connections.itervalues())
                            peer.pex_add.pop()

                data = data[2 + addresses * 12:]
            elif data[0] == UDPHandler.PEX_DEL:
                if len(data) < 2:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                addresses = ord(data[1])
                if len(data) < 2 + 4 * addresses:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                    return False
                for i in range(0, addresses):
                    id = data[2 + i * 6:2 + i * 6 + 4]
                    if DEBUG:
                        debug('    Received peer %s' % id.encode('hex'))
                    peer = self.handler.known_peers.get(id)
                    if not peer or self.address not in peer.advertised_by:
                        continue
                    del peer.advertised_by[self.address]
                    if len(peer.advertised_by) == 0 and peer.connection_state == UDPConnection.CONNECT_NONE:
                        del self.handler.known_peers[id]

                data = data[2 + addresses * 6:]
            else:
                if data[0] == UDPHandler.CLOSE:
                    if DEBUG:
                        debug('    Reason %d' % ord(data[1]))
                    if len(data) == 2 and data[1] == UDPHandler.CLOSE_TOO_MANY and self.handler.reporter:
                        self.handler.reporter.add_event('UDPPuncture', 'ICLO:%s,%d,%s' % (self.address[0], self.address[1], self.id.encode('hex')))
                    return False
                if data[0] == UDPHandler.UPDATE_NATFW_STATE:
                    if len(data) < 3:
                        self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                        return False
                    if compare_natfw_version(ord(data[2]), self.natfw_version):
                        self.natfw_version = ord(data[2])
                        self.nat_type, self.filter_type = byte_to_natfilter(data[1])
                        if DEBUG:
                            debug('    Type: %d, %d' % (self.nat_type, self.filter_type))
                        map(lambda x: x.pex_add.append(self), self.handler.connections.itervalues())
                        self.pex_add.pop()
                    data = data[3:]
                elif data[0] == UDPHandler.PEER_UNKNOWN:
                    if len(data) < 5:
                        self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_LEN)
                        return False
                    remote = data[1:5]
                    peer = self.handler.known_peers.get(remote)
                    if not peer:
                        data = data[5:]
                        continue
                    if self.address in peer.advertised_by:
                        del peer.advertised_by[self.address]
                        if len(peer.advertised_by) == 0 and peer.connection_state == UDPConnection.CONNECT_NONE:
                            del self.handler.known_peers[remote]
                            data = data[5:]
                            continue
                    if len(peer.advertised_by) > 0 and peer.connection_state == UDPConnection.CONNECT_SENT:
                        rendezvous_addr = peer.advertised_by.iterkeys().next()
                        rendezvous = self.handler.connections.get(rendezvous_addr)
                        if rendezvous:
                            if self.handler.reporter:
                                self.handler.reporter.add_event('UDPPuncture', 'OFWC-RTR:%s,%d,%s,%s' % (rendezvous.address[0],
                                 rendezvous.address[1],
                                 rendezvous.id.encode('hex'),
                                 peer.id.encode('hex')))
                            rendezvous.sendto(UDPHandler.FW_CONNECT_REQ + remote)
                    data = data[5:]
                elif data[0] == UDPHandler.KEEP_ALIVE:
                    data = data[1:]
                else:
                    self.sendto(UDPHandler.CLOSE + UDPHandler.CLOSE_GARBAGE)
                    return False

        return True

    def readvertise_nat(self):
        self.advertise_nat = True

    def remove_advertiser(self, address):
        try:
            del self.advertised_by[address]
        except:
            pass

    def send_pex(self):
        self.last_advert = time.time()
        message = ''
        if self.advertise_nat:
            self.advertise_nat = False
            message += UDPHandler.UPDATE_NATFW_STATE + natfilter_to_byte(self.handler.nat_type, self.handler.filter_type) + chr(self.handler.natfw_version)
        if self.tracker:
            self.pex_add.clear()
            self.pex_del.clear()
        else:
            if len(self.pex_add) > 0:
                message += self.pex_string(self.pex_add, 1023, True)
            if len(self.pex_del) > 0:
                message += self.pex_string(self.pex_del, 1023 - len(message), False)
        if len(message) > 0:
            self.sendto(message)
            return True
        return False

    def pex_string(self, items, max_size, add):
        retval = ''
        num_added = 0
        added = set()
        if add:
            max_size = (max_size - 2) / 12
        else:
            max_size = (max_size - 2) / 4
        while len(items) > 0 and max_size > num_added:
            connection = items.popleft()
            if DEBUG:
                debug('- peer %s:%d (%d, %d) state %d' % (connection.address[0],
                 connection.address[1],
                 connection.nat_type,
                 connection.filter_type,
                 connection.connection_state))
            if connection != self and not connection.tracker and connection.address not in added and (add and connection.connection_state == UDPConnection.CONNECT_ESTABLISHED or not add and connection.connection_state != UDPConnection.CONNECT_ESTABLISHED):
                added.add(connection.address)
                if add:
                    retval += connection.id + address_to_string(connection.address) + natfilter_to_byte(connection.nat_type, connection.filter_type) + chr(connection.natfw_version)
                else:
                    retval += connection.id
                num_added += 1

        if DEBUG:
            debug('- created pex string: ' + retval.encode('hex'))
        if num_added == 0:
            return ''
        elif add:
            return UDPHandler.PEX_ADD + chr(num_added) + retval
        else:
            return UDPHandler.PEX_DEL + chr(num_added) + retval


def address_to_string(address):
    return socket.inet_aton(address[0]) + chr(address[1] >> 8) + chr(address[1] & 255)


def string_to_address(address):
    return (socket.inet_ntoa(address[0:4]), (ord(address[4]) << 8) + ord(address[5]))


def natfilter_to_byte(nat_type, filter_type):
    return chr((nat_type & 3) + ((filter_type & 3) << 2))


def byte_to_natfilter(byte):
    return (ord(byte) & 3, ord(byte) >> 2 & 3)


def compare_natfw_version(a, b):
    return (a - b + 256) % 256 < (b - a + 256) % 256


if __name__ == '__main__':
    import ACEStream.Core.BitTornado.RawServer as RawServer
    from threading import Event
    import thread
    from traceback import print_exc
    import os

    def fail(e):
        print 'Fatal error: ' + str(e)
        print_exc()


    def error(e):
        print 'Non-fatal error: ' + str(e)


    DEBUG = True

    def debug(msg):
        if 'log' in globals():
            log.write('%.2f: %s\n' % (time.time(), msg))
            log.flush()
        print '%.2f: %s' % (time.time(), msg)
        sys.stdout.flush()


    if len(sys.argv) == 2:
        log = open('log-%s.txt' % sys.argv[1], 'w')
    else:
        log = open('log-%d.txt' % os.getpid(), 'w')
    rawserver = RawServer.RawServer(Event(), 60.0, 300.0, False, failfunc=fail, errorfunc=error)
    thread.start_new_thread(rawserver.listen_forever, (None,))
    if len(sys.argv) < 2:
        port = 0
    else:
        port = int(sys.argv[1])
    udp_handler = UDPHandler(rawserver, False, port)
    if sys.argv == '12345':
        udp_handler.connect_threshold = 0
    print 'UDPHandler started, press enter to quit'
    sys.stdin.readline()
    udp_handler.shutdown()
    print 'Log left in ' + log.name
