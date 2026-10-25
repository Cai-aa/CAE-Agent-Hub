import unittest
from pathlib import Path
from tools.shared_desktop import commands

class SharedDesktopTests(unittest.TestCase):
    def test_server_and_desktop_share_endpoint_and_preferences(self):
        root=Path('installation'); runtime=Path('runtime')
        server,desktop=commands(root,runtime,2037)
        self.assertTrue(server[0].endswith('comsolmphserver.exe'))
        self.assertEqual(server[server.index('-port')+1],'2037')
        self.assertEqual(desktop[desktop.index('-port')+1],'2037')
        self.assertEqual(server[server.index('-prefsdir')+1],desktop[desktop.index('-prefsdir')+1])
        self.assertEqual(server[server.index('-multi')+1],'on')
        self.assertIn('-configuration',desktop)
        self.assertNotIn('-configuration',server)

if __name__=='__main__': unittest.main()
