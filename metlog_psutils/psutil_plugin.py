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

    def __init__(self, pid):
        self.pid = pid
        self._process = None

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

        return {'read_bytes': io.read_bytes,
                'write_bytes': io.write_bytes,
                'read_count': io.read_count,
                'write_count': io.write_count,
                }

    def get_memory_info(self):
        """
        Return the percentage of physical memory used, RSS and VMS
        memory used
        """
        if not check_osx_perm():
            raise OSXPermissionFailure("OSX requires root for memory info")

        meminfo = self.process.get_memory_info()
        mem_details = {'pcnt': self.process.get_memory_percent(),
                'rss': meminfo.rss,
                'vms': meminfo.vms,
                }
        return mem_details

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
        return {'cpu_pcnt': cpu_pcnt,
                'cpu_user': cputimes.user,
                'cpu_sys': cputimes.system}

    def get_thread_cpuinfo(self):
        """
        Return CPU usages in seconds split by system and user on a
        per thread basis.
        """
        if not check_osx_perm():
            raise OSXPermissionFailure("OSX requires root for memory info")

        thread_details = {}
        for thread in self.process.get_threads():
            thread_details[thread.id] = {'sys': thread.system_time,
                    'user': thread.user_time}
        return thread_details

    def write_json(self, net=False, io=False, cpu=False, mem=False, threads=False, 
        output_stdout=True):
        data = {}

        if net:
            data['net'] = self.get_connections()

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
                    cpu=False, mem=False, threads=False):
    """
    psutils doesn't work on it's own process.  Run psutils through a subprocess
    so that we don't have to deal with the process issues
    """
    if pid is None:
        pid = os.getpid()

    if 'darwin' in sys.platform:
        return _popen_process_details(pid, net, io, cpu, mem, threads)
    else:
        return _inproc_process_details(pid, net, io, cpu, mem, threads)

def _inproc_process_details(pid=None, net=False, io=False,
                    cpu=False, mem=False, threads=False):
    interp = sys.executable
    lp = LazyPSUtil(pid)
    data = lp.write_json(net, io, cpu, mem, threads, output_stdout=False)
    return data

def _popen_process_details(pid=None, net=False, io=False,
                    cpu=False, mem=False, threads=False):
    interp = sys.executable
    cmd = ['from metlog_psutils.psutil_plugin import LazyPSUtil',
           'LazyPSUtil(%(pid)d).write_json(net=%(net)s, io=%(io)s, cpu=%(cpu)s, mem=%(mem)s, threads=%(threads)s)']
    cmd = ';'.join(cmd)
    rdict = {'pid': pid,
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

    if config:
        raise SyntaxError('Invalid arguments: %s' % str(config))

    def metlog_procinfo(self, pid=None, net=False, io=False,
            cpu=False, mem=False, threads=False):
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

        fields = process_details(pid,
                net and config_net,
                io and config_io,
                cpu and config_cpu, 
                mem and config_mem, 
                threads and config_threads)
        self.metlog('procinfo', fields=fields)

    return metlog_procinfo
