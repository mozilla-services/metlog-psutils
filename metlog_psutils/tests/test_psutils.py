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

import sys
from metlog_psutils.psutil_plugin import supports_iocounters
from nose.tools import eq_
from metlog.config import client_from_text_config
import json
from unittest2 import TestCase
import itertools
import time
import subprocess


class TestPsutil(TestCase):
    def setUp(self):
        cfg_txt = """
        [metlog]
        sender_class = metlog.senders.DebugCaptureSender

        [metlog_plugin_psutil]
        provider=metlog_psutils.psutil_plugin:config_plugin
        """
        self.client = client_from_text_config(cfg_txt, 'metlog')

    def test_cpu_info(self):
        self.client.procinfo(cpu=True)
        detail = list(self.client.sender.msgs)

        found_sys = False
        found_user = False

        for statsd in [json.loads(msg) for msg in detail]:
            if statsd['fields']['name'] == 'sys':
                found_sys = statsd['payload']
            if statsd['fields']['name'] == 'user':
                found_user = statsd['payload']
        assert found_sys and found_user

    def test_busy_info(self):
        found_total = False
        found_uptime = False
        proc = subprocess.Popen([sys.executable, '-m',
            'metlog_psutils.tests.cpuhog'])
        pid = proc.pid
        time.sleep(0.5)
        self.client.procinfo(pid=pid, busy=True)
        proc.communicate()

        detail = list(self.client.sender.msgs)

        assert len(detail) == 3
        for statsd in [json.loads(msg) for msg in detail]:
            if statsd['fields']['name'] == 'total_cpu':
                found_total = statsd['payload']
            if statsd['fields']['name'] == 'uptime':
                found_uptime = statsd['payload']

        assert found_total and found_uptime

    def test_thread_cpu_info(self):
        self.client.procinfo(threads=True)
        detail = list(self.client.sender.msgs)

        msgs = [json.loads(msg) for msg in detail]

        # Make sure that we have some thread info
        assert len(msgs) > 0

        # Group the msgs by thread ID number
        thread_groups = itertools.groupby(msgs, \
                lambda x: x['fields']['name'].split(".")[0])

        for k, g in thread_groups:
            g_list = list(g)

            # Each thread should have sys and user information
            eq_(len(g_list), 2)
            eq_(1, len([f for f in g_list if
                f['fields']['name'].endswith('.sys')]))
            eq_(1, len([f for f in g_list if
                f['fields']['name'].endswith('.user')]))

    def test_io_counters(self):
        if not supports_iocounters():
            self.skipTest("No IO counter support on this platform")

        self.client.procinfo(io=True)
        detail = [json.loads(msg) for msg in self.client.sender.msgs]

        found_rb = False
        found_wb = False
        found_rc = False
        found_wc = False
        for statsd in detail['io']:
            if statsd['fields']['name'] == 'read_bytes':
                found_rb = statsd['payload']
            if statsd['fields']['name'] == 'write_bytes':
                found_wb = statsd['payload']
            if statsd['fields']['name'] == 'read_count':
                found_rc = statsd['payload']
            if statsd['fields']['name'] == 'write_count':
                found_wc = statsd['payload']
        assert found_wc and found_rc and found_wb and found_rb

    def test_meminfo(self):
        found_pcnt = False
        found_rss = False
        found_vms = False

        self.client.procinfo(mem=True)
        detail = [json.loads(msg) for msg in self.client.sender.msgs]

        for statsd in detail:
            assert statsd['fields']['logger'].startswith('psutil.meminfo')
            if statsd['fields']['name'] == 'pcnt':
                found_pcnt = statsd['payload']
            if statsd['fields']['name'] == 'rss':
                found_rss = statsd['payload']
            if statsd['fields']['name'] == 'vms':
                found_vms = True

        assert found_pcnt and found_rss and found_vms


class TestConfiguration(object):
    """
    Configuration for plugin based loggers should *override* what the developer
    uses.  IOTW - developers are overridden by ops.
    """
    logger = 'tests'

    def setUp(self):
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
    """

    client = client_from_text_config(cfg_txt, 'metlog')
    client.procinfo(cpu=True)

    eq_(len(client.sender.msgs), 2)
    msgs = [json.loads(m) for m in client.sender.msgs]
    for m in msgs:
        del m['timestamp']

    for m in msgs:
        assert m['fields']['logger'].startswith('psutil.cpu')
        assert m['fields']['name'] in ('user', 'sys')
        assert isinstance(m['payload'], float)
