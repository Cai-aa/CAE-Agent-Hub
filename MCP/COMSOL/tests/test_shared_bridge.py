from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from tools.shared_bridge import SharedComsolBackend,checked_script

class SharedBridgeTests(unittest.TestCase):
    def test_script_rejects_escape_and_wrong_type(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'scripts'; root.mkdir(); good=root/'good.py'; good.write_text('def run(context): return {}')
            self.assertEqual(checked_script(str(good),root),good.resolve())
            with self.assertRaises(ValueError): checked_script(str(root/'..'/'outside.py'),root)
            wrong=root/'data.txt'; wrong.write_text('x')
            with self.assertRaises(ValueError): checked_script(str(wrong),root)

    def test_shutdown_disconnects_without_clearing_shared_models(self):
        backend=SharedComsolBackend(); backend.client=Mock()
        client=backend.client
        self.assertTrue(backend.handle('shutdown',{})['server_models_preserved'])
        client.disconnect.assert_called_once(); client.clear.assert_not_called(); client.remove.assert_not_called()

    def test_new_model_never_replaces_existing_tag(self):
        backend=SharedComsolBackend(); backend.client=Mock(); backend.client.java.tags.return_value=['DesktopModel']
        with self.assertRaisesRegex(ValueError,'already exists'): backend.handle('newModel',{'tag':'DesktopModel'})
        backend.client.java.create.assert_not_called()

    def test_attach_failure_restores_previous_tag(self):
        backend=SharedComsolBackend(model_tag='keep'); backend.info=Mock(side_effect=ValueError('missing'))
        with self.assertRaises(ValueError): backend.handle('attachModel',{'tag':'missing'})
        self.assertEqual(backend.model_tag,'keep')

    def test_endpoint_change_does_not_reuse_old_connection(self):
        backend=SharedComsolBackend(port=2036)
        with self.assertRaisesRegex(ValueError,'separate bridge'): backend.handle('connect',{'host':'127.0.0.1','port':2037})

if __name__=='__main__': unittest.main()
