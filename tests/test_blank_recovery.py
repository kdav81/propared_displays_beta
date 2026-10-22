"""Exercise the recovery script shipped inside the standalone Pi installer."""
import json
from pathlib import Path
import struct
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


INSTALLER = (Path(__file__).resolve().parents[1] / 'install-client.sh').read_text(encoding='utf-8')
SOURCE = INSTALLER.split("<< 'BLANKRECOVERY'\n", 1)[1].split('\nBLANKRECOVERY\n', 1)[0]
recovery = types.ModuleType('blank_recovery')
exec(compile(SOURCE, 'recover-blank.py', 'exec'), recovery.__dict__)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.page = {'id': 'kiosk', 'type': 'page', 'url': 'https://server/dashboard',
                     'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/kiosk'}
        self.opener = MagicMock()
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps([self.page]).encode()
        self.client = MagicMock()
        self.client.call.return_value = {'result': {'value': 'about:blank'}}
        for target, value in [('urllib.request.build_opener', self.opener), ('DevTools', self.client)]:
            mock = patch.object(recovery, target, return_value=value) if '.' not in target else patch(
                'urllib.request.build_opener', return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        self.state = self.directory / 'blank-recovery-state.json'

    def run_recovery(self, now=100, path='/dashboard'):
        return recovery.recover({'display_url': path}, 'https://server', self.directory, now=now)

    def test_blank_gets_grace_then_navigates_to_assignment(self):
        self.assertFalse(self.run_recovery())
        self.assertFalse(self.run_recovery(now=159))
        self.assertTrue(self.run_recovery(now=160))
        self.client.call.assert_called_with('Page.navigate', {'url': 'https://server/dashboard'})
        self.assertFalse(self.run_recovery(now=161))

    def test_loaded_page_is_untouched_and_clears_state(self):
        self.run_recovery()
        self.client.call.return_value = {'result': {'value': 'https://server/dashboard'}}
        self.assertFalse(self.run_recovery(now=200))
        self.assertFalse(self.state.exists())
        self.assertTrue(all(c.args[0] == 'Runtime.evaluate' for c in self.client.call.call_args_list))

    def test_waiting_or_external_assignment_is_untouched(self):
        for path in ['', '//elsewhere/path', 'https://elsewhere/path', None]:
            self.assertFalse(self.run_recovery(path=path))
        self.opener.open.assert_not_called()

    def test_new_browser_target_and_backwards_clock_restart_grace(self):
        self.run_recovery()
        self.state.write_text(json.dumps({'target': 'old-browser', 'since': 0}))
        self.assertFalse(self.run_recovery(now=500))
        self.assertFalse(self.run_recovery(now=400))
        self.assertEqual(json.loads(self.state.read_text())['since'], 400)

    def test_corrupt_state_gets_fresh_grace(self):
        self.state.write_text('incomplete')
        self.assertFalse(self.run_recovery(now=500))

    def test_actual_blank_url_is_checked_even_if_target_url_is_blank(self):
        self.page['url'] = 'about:blank'
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps([self.page]).encode()
        self.run_recovery()
        self.assertTrue(self.run_recovery(now=160))

    def test_startup_target_with_empty_url_is_recovered(self):
        self.page['url'] = ''
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps([self.page]).encode()
        self.run_recovery()
        self.assertTrue(self.run_recovery(now=160))

    def test_navigation_error_is_not_reported_as_success_and_closes_socket(self):
        self.run_recovery()
        self.client.call.side_effect = [{'result': {'value': 'about:blank'}}, {'errorText': 'net::ERR_FAILED'}]
        with self.assertRaises(ValueError):
            self.run_recovery(now=160)
        self.client.close.assert_called()


class TransportTests(unittest.TestCase):
    def client(self, incoming=b''):
        client = recovery.DevTools.__new__(recovery.DevTools)
        client.deadline = recovery.time.monotonic() + 20
        client.next_id = 0
        client.sock = MagicMock()
        data = bytearray(incoming)
        def recv(count):
            result = bytes(data[:count])
            del data[:count]
            return result
        client.sock.recv.side_effect = recv
        return client

    def test_closed_socket_fails_instead_of_looping(self):
        with self.assertRaises(ConnectionError):
            self.client().read(2)

    def test_ignores_events_and_matches_command_id(self):
        messages = [b'{"method":"event"}', b'{"id":1,"result":{"ok":true}}']
        client = self.client(b''.join(bytes([129, len(m)]) + m for m in messages))
        self.assertEqual(client.call('Page.navigate', {'url': 'https://server/dashboard'}), {'ok': True})

    def test_fragmented_response_with_interleaved_ping(self):
        first, last = b'{"result":', b'"ok"}'
        client = self.client(bytes([1, len(first)]) + first + b'\x89\x01x' + bytes([128, len(last)]) + last)
        self.assertEqual(client.receive(), {'result': 'ok'})
        self.assertEqual(client.sock.sendall.call_args.args[0][0], 138)

    def test_client_frames_are_masked_for_short_and_extended_payloads(self):
        for size in [5, 200, 66000]:
            client = self.client()
            data = b'x' * size
            client.send(1, data)
            frame = client.sock.sendall.call_args.args[0]
            self.assertTrue(frame[1] & 128)
            offset = 2 if size < 126 else 4 if size < 65536 else 10
            if offset == 4:
                self.assertEqual(struct.unpack('!H', frame[2:4])[0], size)
            mask = frame[offset:offset + 4]
            self.assertEqual(bytes(c ^ mask[i % 4] for i, c in enumerate(frame[offset + 4:])), data)

    def test_remote_debugger_address_is_rejected(self):
        with self.assertRaises(ValueError):
            recovery.DevTools('ws://192.0.2.1:9222/page')


if __name__ == '__main__':
    unittest.main()
