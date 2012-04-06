# ***** BEGIN LICENSE BLOCK *****
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
# ***** END LICENSE BLOCK *****

"""
Process specific logging tests

We are initially interested in :
    * network connections with each connection status,
    * CPU utilization,
    * thread counts,
    * child process counts,
    * memory utilization.
"""


from unittest2 import TestCase
from metlog_psutils.psutil_plugin import process_details
from metlog_psutils.psutil_plugin import check_osx_perm
from metlog_psutils.psutil_plugin import supports_iocounters
import time
import socket
import threading
from nose.tools import eq_

from mock import Mock
from metlog.client import MetlogClient
import pkg_resources

from testbase import wait_for_network_shutdown


class TestNetworkLoad(TestCase):

    def setUp(self):
        wait_for_network_shutdown()

    def test_multi_conn(self):
        SLEEP=5
        HOST = 'localhost'                 # Symbolic name meaning the local host
        PORT = 50007              # Arbitrary non-privileged port
        MAX_CONNECTIONS=30

        def echo_serv():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            s.bind((HOST, PORT))
            s.listen(1)

            for i in range(MAX_CONNECTIONS):
                conn, addr = s.accept()
                def echoback(conn, addr):
                    data = conn.recv(1024)
                    conn.send(data)
                    time.sleep(SLEEP)
                    conn.close()
                worker = threading.Thread(target=echoback, args=[conn, addr])
                worker.start()

            s.close()

        t = threading.Thread(target=echo_serv)
        t.start()

        def client_code():
            # Start the client up just so that the server will die gracefully
            def client_worker():
                HOST = 'localhost'                 # Symbolic name meaning the local host
                PORT = 50007              # Arbitrary non-privileged port
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect((HOST, PORT))
                client.send('Hello, world')
                data = client.recv(1024)
                time.sleep(1)
                client.close()

            for i in range(MAX_CONNECTIONS):
                client_thread = threading.Thread(target=client_worker)
                client_thread.start()

        tc = threading.Thread(target=client_code)
        tc.start()

        # Some connections should be established, some should be in
        # close_wait
        has_close_wait = False
        has_established = False
        for i in range(3):
            details = process_details(net=True, server_addr='localhost:50007')
            if details.has_key('net'):
                for net_details in details['net']:
                    if net_details['key'].endswith("ESTABLISHED"):
                        has_established = net_details
                    if net_details['key'].endswith("CLOSE_WAIT"):
                        has_close_wait = net_details

            time.sleep(1)

        # Check that we have some connections in CLOSE_WAIT or
        # ESTABLISHED
        assert has_close_wait and has_established
