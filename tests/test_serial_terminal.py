#!/usr/bin/env python3
"""Exercise the serial launcher through PTYs without touching the board."""
import errno
import fcntl
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def receive(fd, count=None, timeout=2):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], deadline - time.monotonic())
        if not readable:
            break
        try:
            chunk = os.read(fd, 65536 if count is None else count - len(data))
        except OSError as error:
            if error.errno == errno.EIO:
                break
            raise
        if not chunk:
            break
        data.extend(chunk)
        if count is not None and len(data) == count:
            break
    return bytes(data)


class SerialTerminalTest(unittest.TestCase):
    def setUp(self):
        self.serial_master, self.serial_slave = os.openpty()
        self.console_master, self.console_slave = os.openpty()
        self.serial_path = os.ttyname(self.serial_slave)
        previous = termios.tcgetattr(self.serial_slave)
        previous[2] |= termios.CSTOPB
        previous[0] |= termios.IXON | termios.IXOFF
        termios.tcsetattr(self.serial_slave, termios.TCSANOW, previous)
        self.serial_state = termios.tcgetattr(self.serial_slave)
        self.console_state = termios.tcgetattr(self.console_slave)
        self.resize(35, 149, notify=False)
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / 'scripts/serial_terminal.py'), self.serial_path],
            stdin=self.console_slave, stdout=self.console_slave, stderr=self.console_slave)
        deadline = time.monotonic() + 2
        while termios.tcgetattr(self.console_slave)[3] & termios.ICANON:
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.fail(receive(self.console_master, timeout=.1).decode(errors='replace'))
            time.sleep(.01)
        self.assertIn(b'Ctrl+]', receive(self.console_master, timeout=.05))

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for name in ('serial_master', 'serial_slave', 'console_master', 'console_slave'):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)

    def resize(self, rows, columns, notify=True):
        fcntl.ioctl(self.console_slave, termios.TIOCSWINSZ,
                    struct.pack('HHHH', rows, columns, 0, 0))
        if notify:
            os.kill(self.process.pid, signal.SIGWINCH)

    def assert_restored(self):
        self.assertEqual(termios.tcgetattr(self.console_slave), self.console_state)
        if self.serial_master is not None:
            self.assertEqual(termios.tcgetattr(self.serial_slave), self.serial_state)
            reopened = os.open(self.serial_path, os.O_RDWR | os.O_NOCTTY)
            os.close(reopened)

    def test_resize_preserves_display_and_queries(self):
        configured = termios.tcgetattr(self.serial_slave)
        self.assertFalse(configured[2] & (termios.PARENB | termios.CSTOPB))
        self.assertFalse(configured[0] & (termios.IXON | termios.IXOFF))
        self.assertEqual(configured[4:6], [termios.B115200, termios.B115200])
        story = b'\x1b[2;1HThe story stays visible.\r\n> '

        os.write(self.serial_master, story)
        self.assertEqual(receive(self.console_master, len(story)), story)
        for rows, columns in ((18, 80), (24, 100), (40, 180), (35, 149)):
            self.resize(rows, columns)
            # Minicom emits a screen clear here. The launcher emits nothing.
            self.assertEqual(receive(self.console_master, timeout=.05), b'')
            self.assertEqual(receive(self.serial_master, timeout=.05), b'')
            self.assertIsNone(self.process.poll())
            probe = b'\x1b7\x1b[999;999H\x1b[6n\x1b8'
            os.write(self.serial_master, probe)
            self.assertEqual(receive(self.console_master, len(probe)), probe)
            reply = f'\x1b[{rows};{columns}R'.encode()
            os.write(self.console_master, reply)
            self.assertEqual(receive(self.serial_master, len(reply)), reply)
        command = b'look\r\x1b[A\x7f'
        os.write(self.console_master, command)
        self.assertEqual(receive(self.serial_master, len(command)), command)
        next_text = b'\r\nThe story continues after resizing.\r\n> '
        os.write(self.serial_master, next_text)
        self.assertEqual(receive(self.console_master, len(next_text)), next_text)

    def test_exit_restores_terminal_and_releases_device(self):
        os.write(self.console_master, b'lo\x1dnot-sent')
        self.assertEqual(self.process.wait(timeout=2), 0)
        self.assertEqual(receive(self.serial_master, timeout=.05), b'lo')
        self.assertEqual(receive(self.console_master, timeout=.05), b'\x1b[0m\x1b[r\r\n')
        self.assert_restored()

    def test_termination_restores_terminal(self):
        self.process.terminate()
        self.assertEqual(self.process.wait(timeout=2), 128 + signal.SIGTERM)
        self.assert_restored()

    def test_disconnect_restores_terminal(self):
        os.close(self.serial_master)
        self.serial_master = None
        self.assertEqual(self.process.wait(timeout=2), 1)
        self.assertIn(b'Serial connection failed', receive(self.console_master, timeout=.05))
        self.assert_restored()


if __name__ == '__main__':
    unittest.main()
