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

from metlog.client import MetlogClient
from metlog_psutils.psutil_plugin import check_osx_perm
from metlog_psutils.psutil_plugin import config_plugin
from metlog_psutils.psutil_plugin import process_details
from metlog_psutils.psutil_plugin import supports_iocounters
from mock import Mock
from nose.tools import eq_
from testbase import wait_for_network_shutdown
from unittest2 import TestCase
import itertools
import socket
import threading
import time

class TestProcessLogs(TestCase):

    def test_connections(self):
        HOST = 'localhost'                 # Symbolic name meaning the local host
        PORT = 50007              # Arbitrary non-privileged port
        def echo_serv():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            s.bind((HOST, PORT))
            s.listen(1)

            conn, addr = s.accept()
            data = conn.recv(1024)
            conn.send(data)
            conn.close()
            s.close()

        t = threading.Thread(target=echo_serv)
        t.start()
        time.sleep(1)

        def client_code():
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((HOST, PORT))
            client.send('Hello, world')
            data = client.recv(1024)
            client.close()
            time.sleep(1)

        details = process_details(net=True,
                                  server_addr=['%s:%s' % (HOST, PORT)])
        eq_(len(details['net']), 1)

        # Start the client up just so that the server will die gracefully
        tc = threading.Thread(target=client_code)
        tc.start()

    def test_cpu_info(self):
        if not check_osx_perm():
            self.skipTest("OSX needs root")
        detail = process_details(cpu=True)

        found_pcnt= False
        found_sys= False
        found_user= False
        for statsd in detail['cpu']:
            if statsd['key'] == 'pcnt':
                found_pcnt = True
            if statsd['key'] == 'sys':
                found_sys = True
            if statsd['key'] == 'user':
                found_user = True
        assert found_pcnt and found_sys and found_user

    def test_thread_cpu_info(self):
        if not check_osx_perm():
            self.skipTest("OSX needs root")
        detail = process_details(threads=True)

        msgs = [statsd for statsd in detail['threads'] \
                if statsd['key'] in ('sys', 'user')]

        assert len(msgs) > 0
        for k, g in itertools.groupby(msgs, lambda x: x['ns']):
            g_list = list(g)
            eq_(len(g_list), 2)
            assert 'sys' in [f['key'] for f in g_list]
            assert 'user' in [f['key'] for f in g_list]

    def test_io_counters(self):
        if not supports_iocounters():
            self.skipTest("No IO counter support on this platform")

        detail = process_details(io=True)

        found_rb = False
        found_wb = False
        found_rc = False
        found_wc = False
        for statsd in detail['io']:
            # Check the structure
            assert len(statsd) == 4
            assert 'key' in statsd
            assert isinstance(statsd['key'], basestring)
            assert 'ns' in statsd
            assert isinstance(statsd['ns'], basestring)
            assert 'value' in statsd
            assert isinstance(statsd['value'], type(1))
            assert 'rate' in statsd
            eq_(statsd['rate'], '')

            if statsd['key'] == 'read_bytes':
                found_rb = True
            if statsd['key'] == 'write_bytes':
                found_wb = True
            if statsd['key'] == 'read_count':
                found_rc = True
            if statsd['key'] == 'write_count':
                found_wc = True
        assert found_wc and found_rc and found_wb and found_rb

    def test_meminfo(self):
        if not check_osx_perm():
            self.skipTest("OSX needs root")

        found_pcnt = False
        found_rss = False
        found_vms = False
        detail = process_details(mem=True)
        for statsd in detail['mem']:
            eq_(len(statsd), 4)
            assert statsd['ns'] == 'psutil#meminfo'
            assert 'key' in statsd
            assert isinstance(statsd['key'], basestring)
            assert 'value' in statsd
            assert isinstance(statsd['value'], float) or isinstance(statsd['value'], int)
            assert 'rate' in statsd
            eq_(statsd['rate'], '')

            if statsd['key'] == 'pcnt':
                found_pcnt = True
            if statsd['key'] == 'rss':
                found_rss = True
            if statsd['key'] == 'vms':
                found_vms = True

    def test_invalid_metlog_arg(self):
        with self.assertRaises(SyntaxError):
            plugin = config_plugin({'thread_io':True})

class TestMetlog(object):
    logger = 'tests'

    def setUp(self):
        self.mock_sender = Mock()
        self.client = MetlogClient(self.mock_sender, self.logger)
        # overwrite the class-wide threadlocal w/ an instance one
        # so values won't persist btn tests
        self.client.timer._local = threading.local()

        plugin = config_plugin({'net':True})
        self.client.add_method('procinfo', plugin)

        wait_for_network_shutdown()

    def test_add_procinfo(self):
        HOST = 'localhost'                 # Symbolic name meaning the local host
        PORT = 50017              # Arbitrary non-privileged port
        def echo_serv():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            s.bind((HOST, PORT))
            s.listen(1)

            conn, addr = s.accept()
            data = conn.recv(1024)
            conn.send(data)
            conn.close()
            s.close()

        t = threading.Thread(target=echo_serv)
        t.start()
        time.sleep(1)

        def client_code():
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((HOST, PORT))
            client.send('Hello, world')
            data = client.recv(1024)
            client.close()
            time.sleep(1)

        self.client.procinfo(net=True, server_addr='localhost:50017')
        eq_(1, len(self.client.sender.method_calls))
        fields = self.client.sender.method_calls[0][1][0]['fields']
        eq_(fields,  {'net': [{'rate': 1, 
                               'ns': 'psutil#net#127.0.0.1:50017', 
                               'value': 1,
                               'key': 'LISTEN'}]})

        # Start the client up just so that the server will die gracefully
        tc = threading.Thread(target=client_code)
        tc.start()


class TestConfiguration(object):
    """
    Configuration for plugin based loggers should *override* what the developer
    uses.  IOTW - developers are overridden by ops.
    """
    logger = 'tests'

    def setUp(self):
        self.mock_sender = Mock()
        self.client = MetlogClient(self.mock_sender, self.logger)
        # overwrite the class-wide threadlocal w/ an instance one
        # so values won't persist btn tests
        self.client.timer._local = threading.local()

        plugin = config_plugin({'net':False})
        self.client.add_method('procinfo', plugin)

        wait_for_network_shutdown()

    def test_no_netlogging(self):
        self.client.procinfo(net=True)
        eq_(0, len(self.client.sender.method_calls))


def test_plugins_config():
    cfg_txt = """
    [metlog]
    sender_class = metlog.senders.DebugCaptureSender

    [metlog_plugin_procinfo]
    provider=metlog_psutils.psutil_plugin:config_plugin
    net=True
    """
    from metlog.config import client_from_text_config
    import json

    client = client_from_text_config(cfg_txt, 'metlog')
    client.procinfo(net=True)
    assert len(client.sender.msgs) == 1
    actual = json.loads(client.sender.msgs[0])
    del actual['timestamp']
    expected = {"severity": 6, 
     "fields": {"net": []}, 
     "logger": "", 
     "type": "procinfo", 
     "payload": "",
     "env_version": "0.8"}
    assert actual == expected
