import unittest

from tools.check_repository import forbidden_path, problems


class RepositorySafetyTests(unittest.TestCase):
    def test_private_artifacts_are_rejected_at_any_depth(self):
        for name in ['.env', '.env.local', 'web/.env.production', 'deploy/runtime.env',
                     'local.sqlite3', 'local.sqlite3-wal', 'snapshot.db', 'deploy/key.pem',
                     'id_ed25519', '.vercel/project.json', 'data/roster.csv']:
            with self.subTest(name=name):
                self.assertTrue(forbidden_path(name))

    def test_public_source_and_ignore_rules_are_allowed(self):
        for name in ['.gitignore', '.github/CODEOWNERS', 'picklequeue/schema.sql',
                     'web/app.js', 'examples/roster.csv']:
            with self.subTest(name=name):
                self.assertFalse(forbidden_path(name))

    def test_credentials_are_detected_without_echoing_values(self):
        fixtures = [b'gh' + b'p_' + b'A' * 36,
                    b'-----BEGIN ' + b'OPENSSH PRIVATE KEY-----',
                    b'AK' + b'IA' + b'A' * 16,
                    b'https://' + b'account:password@database.invalid']
        for secret in fixtures:
            found = problems('source.py', secret)
            self.assertTrue(found)
            self.assertFalse(any(secret.decode() in message for message in found))

    def test_redacted_examples_do_not_trigger(self):
        self.assertEqual(problems('README.md', b'VERCEL_TOKEN is stored in GitHub secrets.'), [])


if __name__ == '__main__':
    unittest.main()
