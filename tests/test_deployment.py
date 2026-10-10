import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.deploy_vercel import deployment_payload, main, wait_ready
from tools.vercel_preflight import validate_website


class DeploymentTests(unittest.TestCase):
    def test_preview_and_production_are_distinct_and_pin_sha(self):
        sha = 'a' * 40
        preview = deployment_payload('staging', 'staging', sha, 'prj_example')
        self.assertNotIn('target', preview)
        self.assertEqual(preview['gitSource']['sha'], sha)
        self.assertEqual(deployment_payload('production', 'main', sha, 'prj_example')['target'], 'production')

    def test_wrong_branch_or_unpinned_ref_cannot_deploy(self):
        for environment, branch, sha in [('production', 'develop', 'a' * 40),
                                        ('staging', 'main', 'a' * 40),
                                        ('production', 'main', 'main')]:
            with self.assertRaises(ValueError):
                deployment_payload(environment, branch, sha, 'prj_example')

    def test_incomplete_website_fails_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNotNone(validate_website(root))
            (root / 'api').mkdir()
            (root / 'api' / 'attendees.py').write_text('# synthetic structural fixture')
            (root / 'web').mkdir()
            (root / 'web' / 'app.js').write_text('fetch("/api/sessions")')
            self.assertIsNotNone(validate_website(root))
            (root / 'web' / 'app.js').write_text('fetch("/api/attendees")')
            self.assertIsNone(validate_website(root))

    def test_current_project_cannot_send_a_deployment_request(self):
        with patch('tools.deploy_vercel.request_api') as request:
            self.assertEqual(main(), 1)
            request.assert_not_called()

    def test_queued_is_not_reported_as_ready(self):
        with patch('tools.deploy_vercel.time.sleep'), patch('tools.deploy_vercel.request_api', return_value={'id': 'dpl_test', 'readyState': 'READY'}) as request:
            result = wait_ready({'id': 'dpl_test', 'readyState': 'BUILDING'}, 'synthetic', '')
            self.assertEqual(result['readyState'], 'READY')
            request.assert_called_once()

    def test_failed_or_timed_out_build_is_not_success(self):
        with self.assertRaises(RuntimeError):
            wait_ready({'id': 'dpl_test', 'readyState': 'ERROR'}, 'synthetic', '')
        with self.assertRaises(RuntimeError):
            wait_ready({'id': 'dpl_test', 'readyState': 'BUILDING'}, 'synthetic', '', timeout=0)
