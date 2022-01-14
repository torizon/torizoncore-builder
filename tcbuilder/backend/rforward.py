#!/usr/bin/env python

# Copyright (C) 2008  Robey Pointer <robeypointer@gmail.com>
#
# This file is part of paramiko.
#
# Paramiko is free software; you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 2.1 of the License, or (at your option)
# any later version.
#
# Paramiko is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Paramiko; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA.

"""
Sample script showing how to do remote port forwarding over paramiko.

This script connects to the requested SSH server and sets up remote port
forwarding (the openssh -R option) from a remote port through a tunneled
connection to a destination reachable from the local machine.
"""

import select
import socket
import threading
import logging

SSH_PORT = 22
DEFAULT_PORT = 4000

log = logging.getLogger("torizon." + __name__)


def handler(chan, host, port):
    sock = socket.socket()
    sock.connect((host, port))

    log.debug(f"Tunnel connected {chan.origin_addr} -> {chan.getpeername()} -> {(host, port)}")
    while True:
        # pylint: disable=invalid-name
        r, _w, _x = select.select([sock, chan], [], [])
        # pylint: enable=invalid-name
        if sock in r:
            data = sock.recv(1024)
            if len(data) == 0:
                break
            chan.send(data)
        if chan in r:
            data = chan.recv(1024)
            if len(data) == 0:
                break
            sock.send(data)
    chan.close()
    sock.close()
    log.debug(f"Tunnel closed from {chan.origin_addr}")

def request_port_forward(transport):
    """
    Create an SSH reverse port forward tunnel.

    :param transport: The SSH connection transport
    :returns:
        The TCP port number opened for the SSH reverse tunnel.
    """
    return transport.request_port_forward("", 0)


def reverse_forward_tunnel(remote_host, remote_port, transport):
    while True:
        chan = transport.accept(1000)
        if chan is None:
            continue
        thr = threading.Thread(
            target=handler, args=(chan, remote_host, remote_port)
        )
        thr.setDaemon(True)
        thr.start()
