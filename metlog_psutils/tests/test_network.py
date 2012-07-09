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

from metlog.config import client_from_text_config
from unittest2 import TestCase
from nose.tools import eq_
import json
import socket
import threading
import time


class TestNetworkLoad(TestCase):
    def setUp(self):
        cfg_txt = """
        [metlog]
        sender_class = metlog.senders.DebugCaptureSender

        [metlog_plugin_procinfo]
        provider=metlog_psutils.psutil_plugin:config_plugin
        """
        ###
        self.client = client_from_text_config(cfg_txt, 'metlog')

        self.HOST = 'localhost'        # Symbolic name meaning the local host
        self.PORT = 50007              # Arbitrary non-privileged port
        self.MAX_CONNECTIONS = 10
        self.wait_for_network_shutdown()

    def tearDown(self):
        self.wait_for_network_shutdown()

    def wait_for_network_shutdown(self):
        while True:
            self.client.sender.msgs.clear()
            self.client.procinfo(net=True)
            if len(list(self.client.sender.msgs)) > 0:
                time.sleep(1)
                print "Not all networks connections are closed...  waiting"
            else:
                print "Connections all closed - running testcase!"
                break

    def client_code(self):
        # Start the client up just so that the server will die gracefully

        def client_worker():
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect((self.HOST, self.PORT))
                client.send('Hello, world')
                client.recv(1024)
                time.sleep(1)
            except:
                pass
            finally:
                client.close()

        for i in range(self.MAX_CONNECTIONS):
            client_thread = threading.Thread(target=client_worker)
            client_thread.start()

    def echo_serv(self):
        SLEEP = 5
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        s.bind((self.HOST, self.PORT))
        s.listen(1)

        for i in range(self.MAX_CONNECTIONS):
            conn, addr = s.accept()

            def echoback(conn, addr):
                data = conn.recv(1024)
                conn.send(data)
                time.sleep(SLEEP)
                conn.close()
            worker = threading.Thread(target=echoback, args=[conn, addr])
            worker.start()

        s.close()

    def test_multi_conn(self):

        t = threading.Thread(target=self.echo_serv)
        t.start()

        tc = threading.Thread(target=self.client_code)
        tc.start()

        # Some connections should be established, some should be in
        # close_wait
        for i in range(3):
            self.client.procinfo(net=True)
            time.sleep(1)

        for i in range(30):
            tc = threading.Thread(target=self.client_code)
            tc.start()

        # Check that we have some connections in CLOSE_WAIT or
        # ESTABLISHED
        has_close_wait = False
        has_established = False
        for msg in self.client.sender.msgs:
            jdata = json.loads(msg)
            net_info = jdata['fields']['name']
            if net_info.endswith("ESTABLISHED"):
                has_established = True
            if net_info.endswith("CLOSE_WAIT"):
                has_close_wait = True

        assert has_close_wait and has_established


class TestNetworkConnections(TestCase):
    def setUp(self):
        cfg_txt = """
        [metlog]
        sender_class = metlog.senders.DebugCaptureSender

        [metlog_plugin_procinfo]
        provider=metlog_psutils.psutil_plugin:config_plugin
        """
        ###
        self.client = client_from_text_config(cfg_txt, 'metlog')

        self.HOST = 'localhost'        # Symbolic name meaning the local host
        self.PORT = 50007              # Arbitrary non-privileged port
        self.MAX_CONNECTIONS = 10
        self.wait_for_network_shutdown()

    def tearDown(self):
        self.wait_for_network_shutdown()

    def wait_for_network_shutdown(self):
        while True:
            self.client.sender.msgs.clear()
            self.client.procinfo(net=True)
            if len(list(self.client.sender.msgs)) > 0:
                time.sleep(1)
                print "Not all networks connections are closed...  waiting"
            else:
                print "Connections all closed - running testcase!"
                break

    def test_connections(self):
        def echo_serv():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.HOST, self.PORT))
            s.listen(1)
            conn, addr = s.accept()
            data = conn.recv(1024)
            conn.send(data)
            conn.close()
            s.close()

        t = threading.Thread(target=echo_serv)
        t.start()
        time.sleep(1)

        self.client.procinfo(net=True)
        details = self.client.sender.msgs
        eq_(len(details), 1)

        # Start the client up just so that the server will die gracefully
        tc = threading.Thread(target=self.client_code)
        tc.start()

    def client_code(self):
        # Start the client up just so that the server will die gracefully

        def client_worker():
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect((self.HOST, self.PORT))
                client.send('Hello, world')
                client.recv(1024)
                time.sleep(1)
            except:
                pass
            finally:
                client.close()

        for i in range(self.MAX_CONNECTIONS):
            client_thread = threading.Thread(target=client_worker)
            client_thread.start()
