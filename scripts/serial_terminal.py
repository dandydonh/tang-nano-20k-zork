#!/usr/bin/env python3
"""Connect an ANSI desktop terminal directly to the FPGA's UART."""
import argparse
import errno
import fcntl
import os
import select
import signal
import sys
import termios
import tty

EXIT_KEY = b'\x1d'  # Ctrl+]
COMMAND_KEY = 0x01  # Ctrl+A, followed by X to exit (as in Minicom)


def write_all(fd, data):
    while data:
        try:
            written = os.write(fd, data)
        except BlockingIOError:
            select.select([], [fd], [])
            continue
        if not written:
            raise OSError('connection closed while writing')
        data = data[written:]


def connect(device, baud, console_in=0, console_out=1):
    """Forward bytes, including ANSI queries/replies, without a screen buffer."""
    if not os.isatty(console_in) or not os.isatty(console_out):
        raise OSError('run this command in an interactive desktop terminal')
    serial_fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    serial_state = console_state = None
    exclusive = False
    try:
        # Avoid two copies of this launcher sharing the device. TIOCEXCL also
        # prevents later opens by other ordinary serial clients.
        fcntl.flock(serial_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(serial_fd, termios.TIOCEXCL)
        exclusive = True
        serial_state = termios.tcgetattr(serial_fd)
        tty.setraw(serial_fd, termios.TCSANOW)
        attrs = termios.tcgetattr(serial_fd)
        attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)
        attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB |
                      getattr(termios, 'CRTSCTS', 0))
        attrs[2] |= termios.CLOCAL | termios.CREAD | termios.CS8
        attrs[4] = attrs[5] = getattr(termios, 'B' + str(baud))
        termios.tcsetattr(serial_fd, termios.TCSANOW, attrs)
        print(f'Connected to {device} at {baud}. Waiting for board output.',
              file=sys.stderr, flush=True)
        console_state = termios.tcgetattr(console_in)
        tty.setraw(console_in, termios.TCSANOW)
        command_pending = False
        while True:
            ready, _, _ = select.select([console_in, serial_fd], [], [])
            for fd in ready:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                if not data:
                    return
                if fd == serial_fd:
                    write_all(console_out, data)
                else:
                    outgoing = bytearray()
                    exiting = False
                    for key in data:
                        if key == EXIT_KEY[0]:
                            exiting = True
                            break
                        if command_pending:
                            command_pending = False
                            if key in (ord('x'), ord('X')):
                                exiting = True
                                break
                            outgoing.append(COMMAND_KEY)
                            # Ctrl+A twice sends one literal Ctrl+A.
                            if key == COMMAND_KEY:
                                continue
                        elif key == COMMAND_KEY:
                            command_pending = True
                            continue
                        outgoing.append(key)
                    write_all(serial_fd, outgoing)
                    if exiting:
                        return
    finally:
        try:
            if console_state is not None:
                try:
                    write_all(console_out, b'\x1b[0m\x1b[r\r\n')
                except OSError:
                    pass
                termios.tcsetattr(console_in, termios.TCSANOW, console_state)
        finally:
            try:
                if serial_state is not None:
                    termios.tcsetattr(serial_fd, termios.TCSANOW, serial_state)
            finally:
                # Release exclusivity even if a disconnected device rejects
                # restoring its termios settings.
                try:
                    if exclusive:
                        fcntl.ioctl(serial_fd, termios.TIOCNXCL)
                finally:
                    os.close(serial_fd)


def terminate(signum, _frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', nargs='?', default='/dev/ttyUSB1')
    parser.add_argument('--baud', type=int, default=115200,
                        choices=[9600, 19200, 38400, 57600, 115200])
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGHUP, terminate)
    # SIGWINCH deliberately has no display handler: the desktop terminal owns
    # its existing text and scrollback. The FPGA detects size at its next probe.
    print(f'Connecting to {args.device} at {args.baud}. '
          'Exit with Ctrl+] or Ctrl+A then X.',
          file=sys.stderr, flush=True)
    try:
        connect(args.device, args.baud)
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        if error.errno in (errno.EBUSY, errno.EWOULDBLOCK):
            print('Serial port is busy; close Minicom or the other serial client.',
                  file=sys.stderr)
        else:
            print(f'Serial connection failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
