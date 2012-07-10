# ***** BEGIN LICENSE BLOCK *****
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
# ***** END LICENSE BLOCK *****
METLOG_METHOD_NAME = 'procinfo'

import datetime
import json
import os
import psutil
import re
import socket
import sys


class InvalidPIDError(StandardError):
    pass


class OSXPermissionFailure(StandardError):
    pass


def check_osx_perm():
    """
    psutil can't do the right thing on OSX because of weird permissioning rules
    in Darwin.

    http://code.google.com/p/psutil/issues/detail?id=108
    """
    return 'darwin' not in sys.platform or os.getuid() == 0


def supports_iocounters():
    if not hasattr(psutil.Process, 'get_io_counters') or os.name != 'posix':
        return False
    return True


class LazyPSUtil(object):
    """
    This class can only be used *outside* the process that is being inspected
    """

    def __init__(self, pid, server_addr=None):
        """
        :param pid: Process ID to monitor
        :param server_addr: A list of local host:port numbers that are
                             server sockets. Defaults None.
        """
        self.pid = pid
        self.host = socket.gethostname().replace('.', '_')

        self._process = None
        if server_addr is None:
            server_addr = []
        if isinstance(server_addr, basestring):
            server_addr = [server_addr]

        # Force all addresses to use IP instead of hostname
        for idx, addr in enumerate(server_addr):
            host, port = addr.split(":")
            if re.match('[a-z]', host, re.I):
                server_addr[idx] = "%s:%s" % (socket.gethostbyname(host), port)

        self._server_addr = server_addr

    @property
    def process(self):
        if self._process is None:
            self._process = psutil.Process(self.pid)
        return self._process

    def get_connections(self):
        """
        Return details of each network connection as a list of
        dictionaries.

        Keys in each connection dictionary are:

            local - host:port for the local side of the connection

            remote - host:port of the remote side of the connection

            status - TCP Connection status. One of :
                * "ESTABLISHED"
                * "SYN_SENT"
                * "SYN_RECV"
                * "FIN_WAIT1"
                * "FIN_WAIT2"
                * "TIME_WAIT"
                * "CLOSE"
                * "CLOSE_WAIT"
                * "LAST_ACK"
                * "LISTEN"
                * "CLOSING"
        """
        connections = []
        for conn in self.process.get_connections():
            if conn.type == socket.SOCK_STREAM:
                type = 'TCP'
            elif conn.type == socket.SOCK_DGRAM:
                type = 'UDP'
            else:
                type = 'UNIX'
            lip, lport = conn.local_address
            if not conn.remote_address:
                rip = rport = '*'
            else:
                rip, rport = conn.remote_address
            connections.append({
                'type': type,
                'status': conn.status,
                'local': '%s:%s' % (lip, lport),
                'remote': '%s:%s' % (rip, rport),
                })
        return connections

    def get_busy_stats(self):
        """
        Get process busy stats.

        Return 3 statsd messages for total_cpu time in seconds, total
        uptime in seconds, and the percentage of time the process has been
        active.
        """
        cputimes = self.process.get_cpu_times()
        total_cputime = (cputimes.user + cputimes.system)

        uptime = (datetime.datetime.now() -
                datetime.datetime.fromtimestamp(self.process.create_time))
        uptime = uptime.seconds + uptime.microseconds / 1000000.0
        if uptime == 0:
            uptime = 1 / 1000000.0

        statsd_msgs = []
        ns = 'psutil.busy.%s.%s' % (self.host, self.pid)
        statsd_msgs.append({'ns': ns,
                            'key': 'total_cpu',
                            'value': total_cputime,
                            'rate': 1,
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'uptime',
                            'value': uptime,
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'pcnt',
                            'value': (total_cputime / uptime),
                            'rate': '1',
                            })
        return statsd_msgs

    def get_io_counters(self):
        """
        Return the number of bytes read, written and the number of
        read and write syscalls that have invoked.
        """
        if not supports_iocounters():
            sys.exit('platform not supported')

        io = self.process.get_io_counters()

        statsd_msgs = []
        ns = 'psutil.io.%s.%s' % (self.host, self.pid)
        statsd_msgs.append({'ns': ns,
                            'key': 'read_bytes',
                            'value': io.read_bytes,
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'write_bytes',
                            'value': io.write_bytes,
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'read_count',
                            'value': io.read_count,
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'write_count',
                            'value': io.write_count,
                            'rate': '1',
                            })

        return statsd_msgs

    def get_memory_info(self):
        """
        Return the percentage of physical memory used, RSS and VMS
        memory used
        """
        meminfo = self.process.get_memory_info()
        statsd_msgs = []
        ns = 'psutil.meminfo.%s.%s' % (self.host, self.pid)
        statsd_msgs.append({'ns': ns,
                            'key': 'pcnt',
                            'value': self.process.get_memory_percent(),
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'rss',
                            'value': meminfo.rss,
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'vms',
                            'value': meminfo.vms,
                            'rate': '1',
                            })
        return statsd_msgs

    def get_cpu_info(self):
        """
        Return CPU usages in seconds split by system and user for the
        whole process.  Also provides CPU % used for a 0.1 second
        interval.

        Note that this method will *block* for 0.1 seconds.
        """
        cputimes = self.process.get_cpu_times()
        #cpu_pcnt = self.process.get_cpu_percent()

        statsd_msgs = []

        ns = 'psutil.cpu.%s.%s' % (self.host, self.pid)
        statsd_msgs.append({'ns': ns,
                            'key': 'user',
                            'value': cputimes.user,
                            'rate': '1',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'sys',
                            'value': cputimes.system,
                            'rate': '1',
                            })
        #statsd_msgs.append({'ns': ns,
        #                    'key': 'pcnt',
        #                    'value': cpu_pcnt,
        #                    'rate': '1',
        #                    })
        return statsd_msgs

    def get_thread_cpuinfo(self):
        """
        Return CPU usages in seconds split by system and user on a
        per thread basis.
        """
        statsd_msgs = []

        for thread in self.process.get_threads():
            ns = 'psutil.thread.%s.%s' % (self.host, self.pid)

            statsd_msgs.append({'ns': ns,
                                'key': '%s.sys' % thread.id,
                                'value': thread.system_time,
                                'rate': '1',
                                })
            statsd_msgs.append({'ns': ns,
                                'key': '%s.user' % thread.id,
                                'value': thread.user_time,
                                'rate': '1',
                                })
        return statsd_msgs

    def _add_port(self, server_stats, server_port):
        if not server_port in server_stats:
            server_stats[server_port] = {
                "ESTABLISHED": 0,
                "SYN_SENT": 0,
                "SYN_RECV": 0,
                "FIN_WAIT1": 0,
                "FIN_WAIT2": 0,
                "TIME_WAIT": 0,
                "CLOSE": 0,
                "CLOSE_WAIT": 0,
                "LAST_ACK": 0,
                "LISTEN": 0,
                "CLOSING": 0}

    def summarize_network(self, network_data):
        """
        Summarizes network connection information into something that
        is friendly to statsd.

        From a metrics standpoint, we only really care about the
        number of connections in each state.

        Connections are sorted into 2 buckets
            * server connections

            For each listening host:port, a dictionary of connection
            states to connection counts is created
        """

        server_stats = {}
        for server_port in self._server_addr:
            self._add_port(server_stats, server_port)

        for conn in network_data:
            status = conn['status']
            local_addr = conn['local']
            remote_addr = conn['remote']

            if remote_addr == '*:*' and local_addr not in self._server_addr:
                self._server_addr.append(local_addr)
                self._add_port(server_stats, local_addr)

            if local_addr in self._server_addr:
                server_stats[local_addr][status] += 1
            else:
                self._add_port(server_stats, remote_addr)
                server_stats[remote_addr][status] += 1

        statsd_msgs = []
        for addr, status_dict in server_stats.items():
            for status_name, conn_count in status_dict.items():
                if conn_count == 0:
                    continue
                ns = 'psutil.net.%s.%s' % (self.host, self.pid)
                key = "%s.%s" % (addr.replace(".", '_'), status_name)
                statsd_msgs.append({'ns': ns,
                                    'key': key,
                                    'value': conn_count,
                                    'rate': 1,
                                    })
        return statsd_msgs

    def write_json(self, net=False, io=False, cpu=False, mem=False,
            threads=False, busy=False, output_stdout=True):
        data = {}

        if net:
            data['net'] = self.summarize_network(self.get_connections())

        if io:
            data['io'] = self.get_io_counters()

        if cpu:
            data['cpu'] = self.get_cpu_info()

        if busy:
            data['busy'] = self.get_busy_stats()

        if mem:
            data['mem'] = self.get_memory_info()

        if threads:
            data['threads'] = self.get_thread_cpuinfo()

        if output_stdout:
            sys.stdout.write(json.dumps(data))
            sys.stdout.flush()
        else:
            return data


def process_details(pid=None, net=False, io=False,
                    cpu=False, mem=False, threads=False,
                    busy=False, server_addr=None):
    if pid is None:
        pid = os.getpid()

    lp = LazyPSUtil(pid, server_addr)
    data = lp.write_json(net=net, io=io, cpu=cpu, mem=mem,
            threads=threads, busy=busy, output_stdout=False)
    return data


def config_plugin(config):
    """
    Configure the metlog plugin prior to binding it to the
    metlog client.
    """
    if config:
        raise SyntaxError('Invalid arguments: %s' % str(config))

    def metlog_procinfo(self, pid=None, net=False, io=False,
            cpu=False, mem=False, threads=False,
            busy=False, server_addr=[]):
        '''
        This is a metlog extension method to place process data into the metlog
        fields dictionary
        '''
        if not (net or io or cpu or mem or threads or busy):
            # Nothing is going to be logged - stop right now
            return

        if pid is None:
            pid = os.getpid()

        details = process_details(pid, net, io, cpu, mem, threads,
                busy, server_addr)

        # Send all the collected metlog messages over
        for k, msgs in details.items():
            for m in msgs:
                self.metlog('procinfo',
                        fields={'logger': m['ns'],
                                'name': m['key'],
                                'rate': m['rate']},
                        payload=m['value'])
    metlog_procinfo.metlog_name = 'procinfo'

    return metlog_procinfo
