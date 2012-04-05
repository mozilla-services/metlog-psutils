# ***** BEGIN LICENSE BLOCK *****
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
# ***** END LICENSE BLOCK *****

import psutil
import socket
import json
import os
import sys
from subprocess import Popen, PIPE
import re
import socket


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

        # Delete any methods that we don't support on the current platform
        if not supports_iocounters():
            del self.__class__.get_io_counters

        if not check_osx_perm():
            del self.__class__.get_cpu_info
            del self.__class__.get_memory_info
            del self.__class__.get_thread_cpuinfo

    @property
    def process(self):
        if self._process is None:
            self._process = psutil.Process(self.pid)
            if 'darwin' in sys.platform and os.getpid() == self.pid:
                raise InvalidPIDError("Can't run process inspection on itself")
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

    def get_io_counters(self):
        """
        Return the number of bytes read, written and the number of
        read and write syscalls that have invoked.
        """
        if not supports_iocounters():
            sys.exit('platform not supported')

        io = self.process.get_io_counters()

        statsd_msgs = []
        ns = 'psutil.io.%s.%s' % (self.host, self.pid),
        statsd_msgs.append({'ns': ns,
                            'key': 'read_bytes', 
                            'value': io.read_bytes,
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'write_bytes', 
                            'value': io.write_bytes,
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'read_count', 
                            'value': io.read_count,
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'write_count', 
                            'value': io.write_count,
                            'rate': '',
                            })

        return statsd_msgs


    def get_memory_info(self):
        """
        Return the percentage of physical memory used, RSS and VMS
        memory used
        """
        # TODO: move this out into the constructor and just delete the
        # method instead of checking it each time
        if not check_osx_perm():
            raise OSXPermissionFailure("OSX requires root for memory info")

        meminfo = self.process.get_memory_info()
        statsd_msgs = []
        ns = 'psutil.meminfo.%s.%s' % (self.host, self.pid)
        statsd_msgs.append({'ns': ns,
                            'key': 'pcnt', 
                            'value': self.process.get_memory_percent(),
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'rss', 
                            'value': meminfo.rss,
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'vms', 
                            'value': meminfo.vms,
                            'rate': '',
                            })
        return statsd_msgs


    def get_cpu_info(self):
        """
        Return CPU usages in seconds split by system and user for the
        whole process.  Also provides CPU % used for a 0.1 second
        interval.

        Note that this method will *block* for 0.1 seconds.
        """
        if not check_osx_perm():
            raise OSXPermissionFailure("OSX requires root for memory info")

        cputimes = self.process.get_cpu_times()
        cpu_pcnt = self.process.get_cpu_percent()

        statsd_msgs = []

        ns = 'psutil.cpu.%s.%s' % (self.host, self.pid),
        statsd_msgs.append({'ns': ns,
                            'key': 'user', 
                            'value': cputimes.user,
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'sys', 
                            'value': cputimes.system,
                            'rate': '',
                            })
        statsd_msgs.append({'ns': ns,
                            'key': 'pcnt', 
                            'value': cpu_pcnt,
                            'rate': '',
                            })
        return statsd_msgs

    def get_thread_cpuinfo(self):
        """
        Return CPU usages in seconds split by system and user on a
        per thread basis.
        """
        if not check_osx_perm():
            raise OSXPermissionFailure("OSX requires root for memory info")

        statsd_msgs = []

        for thread in self.process.get_threads():
            ns = 'psutil.thread.%s.%s' % (self.host, self.pid)

            statsd_msgs.append({'ns': ns,
                                'key': '%s.sys' % thread.id,
                                'value': thread.system_time,
                                'rate': '',
                                })
            statsd_msgs.append({'ns': ns,
                                'key': '%s.user' % thread.id, 
                                'value': thread.user_time,
                                'rate': '',
                                })
        return statsd_msgs


    def _add_port(self, server_stats, server_port):
        if not server_stats.has_key(server_port):
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
                sys.stderr.write("WARNING: missing a local address for server port in logging module")
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
                key = "%s.%s" % (addr.replace(".", '_'), status_name),
                statsd_msgs.append({'ns': ns,
                                    'key': key,
                                    'value': conn_count,
                                    'rate': 1,
                                    })
        return statsd_msgs

    def write_json(self, net=False, io=False, cpu=False, mem=False, threads=False, 
        output_stdout=True):
        data = {}

        if net:
            data['net'] = self.summarize_network(self.get_connections())

        if io:
            data['io'] = self.get_io_counters()

        if cpu:
            data['cpu'] = self.get_cpu_info()

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
                    server_addr=None):
    """
    psutils doesn't work on it's own process.  Run psutils through a subprocess
    so that we don't have to deal with the process issues
    """
    if pid is None:
        pid = os.getpid()

    if 'darwin' in sys.platform:
        return _popen_process_details(pid, net, io, cpu, mem, threads,
                server_addr)
    else:
        return _inproc_process_details(pid, net, io, cpu, mem,
                threads, server_addr)

def _inproc_process_details(pid=None, net=False, io=False,
                    cpu=False, mem=False, threads=False,
                    server_addr=None):
    interp = sys.executable
    lp = LazyPSUtil(pid, server_addr)
    data = lp.write_json(net, io, cpu, mem, threads, output_stdout=False)
    return data

def _popen_process_details(pid=None, net=False, io=False,
                    cpu=False, mem=False, threads=False,
                    server_addr=None):
    interp = sys.executable
    cmd = ['from metlog_psutils.psutil_plugin import LazyPSUtil',
           'LazyPSUtil(%(pid)d, %(server_addr)r).write_json(net=%(net)s, io=%(io)s, cpu=%(cpu)s, mem=%(mem)s, threads=%(threads)s)']
    cmd = ';'.join(cmd)
    rdict = {'pid': pid,
            'server_addr': server_addr,
            'net': int(net),
            'io': int(io),
            'cpu': int(cpu),
            'mem': int(mem),
            'threads': int(threads)}
    cmd = cmd % rdict
    proc = Popen([interp, '-c', cmd], stdout=PIPE, stderr=PIPE)
    result = proc.communicate()
    stdout, stderr = result[0], result[1]
    return json.loads(stdout)

def config_plugin(config):
    """
    Configure the metlog plugin prior to binding it to the
    metlog client.
    """
    config_net = config.pop('net', False)
    config_io = config.pop('io', False)
    config_cpu = config.pop('cpu', False)
    config_mem = config.pop('mem', False)
    config_threads = config.pop('threads', False)
    default_server_addr = config.pop('server_addr', None)

    if config:
        raise SyntaxError('Invalid arguments: %s' % str(config))

    def metlog_procinfo(self, pid=None, net=False, io=False,
            cpu=False, mem=False, threads=False,
            server_addr=default_server_addr):
        '''
        This is a metlog extension method to place process data into the metlog
        fields dictionary
        '''
        if not ((net and config_net) or
                (io and config_io) or
                (cpu and config_cpu) or
                (mem and config_mem) or
                (threads and config_threads)):
            # Nothing is going to be logged - stop right now
            return

        if pid is None:
            pid = os.getpid()

        details = process_details(pid,
                net and config_net,
                io and config_io,
                cpu and config_cpu, 
                mem and config_mem, 
                threads and config_threads,
                server_addr)

        # Send all the collected metlog messages over
        for k, msgs in details.items():
            for m in msgs:
                self.metlog('procinfo', 
                        fields={'logger': m['ns'],
                                'name': m['key'],
                                'rate': m['rate']},
                        payload=m['value'])


    return metlog_procinfo
