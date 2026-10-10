import unittest

from tools.check_pull_request import validate


class PullRequestPolicyTests(unittest.TestCase):
    def test_contribution_targets_develop(self):
        self.assertIsNone(validate('feat(#1): [Browser] add queue', 'feature/#1', 'develop', False))

    def test_production_cannot_skip_staging(self):
        self.assertIsNotNone(validate('ci(#1): promote', 'feature/#1', 'main'))
        self.assertIsNotNone(validate('ci(#1): promote', 'develop', 'main'))
        self.assertIsNone(validate('ci(#1): promote', 'staging', 'main'))

    def test_public_main_accepts_fork_contributions_and_maintainer_release_branches(self):
        public = '22104323/pickleball'
        self.assertIsNone(validate('feat(#3): add link flow', 'feature/#3', 'main', False, public))
        self.assertIsNone(validate('feat(#3): publish release', 'release/#3', 'main', True, public))
        self.assertIsNotNone(validate('feat(#3): add link flow', 'feature/#3', 'main', True, public))
        self.assertIsNotNone(validate('feat(#4): add link flow', 'feature/#3', 'main', False, public))
        self.assertIsNotNone(validate('ci(#3): skip staging', 'develop', 'main', True, public))

    def test_staging_accepts_only_internal_develop(self):
        self.assertIsNotNone(validate('ci(#1): promote', 'develop', 'staging', False))
        self.assertIsNone(validate('ci(#1): promote', 'develop', 'staging'))

    def test_invalid_title_branch_and_target_are_rejected(self):
        for title, head, base in [('update', 'feature/#1', 'develop'),
                                  ('feat(#1): change', 'random', 'develop'),
                                  ('feat(#2): change', 'feature/#1', 'develop'),
                                  ('feat(#1): change', 'feature/#1', 'other')]:
            self.assertIsNotNone(validate(title, head, base))
