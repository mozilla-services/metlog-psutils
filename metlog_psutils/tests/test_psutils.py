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

from metlog_psutils.psutil_plugin import check_osx_perm
import sys
from metlog_psutils.psutil_plugin import process_details
from metlog_psutils.psutil_plugin import supports_iocounters
from mock import Mock
from nose.tools import eq_
from metlog.config import client_from_text_config
import json

from unittest2 import TestCase
import itertools
import socket
import threading
import time
import subprocess


class TestProcessLogs(TestCase):

    def test_cpu_info(self):
        detail = process_details(cpu=True)

        found_pcnt = False
        found_sys = False
        found_user = False
        for statsd in detail['cpu']:
            if statsd['key'] == 'pcnt':
                found_pcnt = True
            if statsd['key'] == 'sys':
                found_sys = True
            if statsd['key'] == 'user':
                found_user = True
        assert found_pcnt and found_sys and found_user

    def test_busy_info(self):
        found_total = False
        found_uptime = False
        found_pcnt = False
        proc = subprocess.Popen([sys.executable, '-m',
            'metlog_psutils.tests.cpuhog'])
        pid = proc.pid
        time.sleep(1)
        detail = process_details(pid=pid, busy=True)
        proc.communicate()

        assert len(detail['busy']) == 3
        for statsd in detail['busy']:
            if statsd['key'] == 'total_cpu':
                found_total = True
            if statsd['key'] == 'uptime':
                found_uptime = True
            if statsd['key'] == 'pcnt':
                found_pcnt = True

        assert found_total and found_uptime and found_pcnt

    def test_thread_cpu_info(self):
        detail = process_details(threads=True)

        msgs = detail['threads']

        assert len(msgs) > 0
        for k, g in itertools.groupby(msgs,\
                lambda x: x['ns'] + '.' + x['key'].split(".")[0]):
            g_list = list(g)
            eq_(len(g_list), 2)
            eq_(1, len([f['key'] for f in g_list if
                f['key'].endswith('.sys')]))
            eq_(1, len([f['key'] for f in g_list if
                f['key'].endswith('.user')]))

    def test_io_counters(self):
        if not supports_iocounters():
            self.skipTest("No IO counter support on this platform")

        detail = process_details(io=True)

        found_rb = False
        found_wb = False
        found_rc = False
        found_wc = False
        for statsd in detail['io']:
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
        found_pcnt = False
        found_rss = False
        found_vms = False
        detail = process_details(mem=True)
        for statsd in detail['mem']:
            eq_(len(statsd), 4)
            assert statsd['ns'].startswith('psutil.meminfo')
            if statsd['key'] == 'pcnt':
                found_pcnt = True
            if statsd['key'] == 'rss':
                found_rss = True
            if statsd['key'] == 'vms':
                found_vms = True

        assert found_pcnt and found_rss and found_vms


class TestMetlog(object):
    logger = 'tests'

    def setUp(self):

        cfg_txt = """
        [metlog]
        sender_class = metlog.senders.DebugCaptureSender

        [metlog_plugin_procinfo]
        provider=metlog_psutils.psutil_plugin:config_plugin
        net=True
        """
        ###
        self.client = client_from_text_config(cfg_txt, 'metlog')

    def test_add_procinfo(self):
        HOST = 'localhost'         # Symbolic name meaning the local host
        PORT = 50017               # Arbitrary non-privileged port

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
            client.recv(1024)
            client.close()
            time.sleep(1)

        self.client.procinfo(net=True, server_addr='localhost:50017')

        msgs = list(self.client.sender.msgs)
        eq_(len(msgs), 1)
        msg = json.loads(msgs[0])

        assert msg['fields']['logger'].startswith("psutil.net")
        assert msg['fields']['name'] == '127_0_0_1:50017.LISTEN'

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

        cfg_txt = """
        [metlog]
        sender_class = metlog.senders.DebugCaptureSender

        [metlog_plugin_psutil]
        provider=metlog_psutils.psutil_plugin:config_plugin
        """
        self.client = client_from_text_config(cfg_txt, 'metlog')

    def test_no_netlogging(self):
        self.client.procinfo(net=True)
        eq_(0, len(self.client.sender.msgs))


def test_plugins_config():
    cfg_txt = """
    [metlog]
    sender_class = metlog.senders.DebugCaptureSender

    [metlog_plugin_procinfo]
    provider=metlog_psutils.psutil_plugin:config_plugin
    cpu=True
    """

    client = client_from_text_config(cfg_txt, 'metlog')
    client.procinfo(cpu=True)

    eq_(len(client.sender.msgs), 3)
    msgs = [json.loads(m) for m in client.sender.msgs]
    for m in msgs:
        del m['timestamp']

    keys = set([m['fields']['name'] for m in msgs])
    eq_(3, len(keys))
    for m in msgs:
        assert m['fields']['logger'].startswith('psutil.cpu')
        assert m['fields']['name'] in ('user', 'sys', 'pcnt')
        assert isinstance(m['payload'], float)
