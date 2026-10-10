import unittest
from unittest.mock import patch

from picklequeue.engine import Problem
from picklequeue.reclub import preview_event, reference_from_url


class ReclubPreviewTests(unittest.TestCase):
    def test_only_public_reclub_event_links_are_accepted(self):
        self.assertEqual(reference_from_url('https://reclub.co/m/aBc123?share=1'), 'ABC123')
        for value in (
            'http://reclub.co/m/ABC123',
            'https://reclub.co.attacker.invalid/m/ABC123',
            'https://user@reclub.co/m/ABC123',
            'https://reclub.co:99999/m/ABC123',
            'https://reclub.co/groups/ABC123',
        ):
            with self.subTest(value=value), self.assertRaises(Problem):
                reference_from_url(value)

    def test_preview_keeps_signups_and_guest_slots_distinct(self):
        event = {
            'name': 'Synthetic open play',
            'groupId': 42,
            'participants': [
                {'referenceType': 1, 'referenceId': 12345, 'status': 1},
                {'referenceType': 1, 'referenceId': 98765, 'status': 3},
                {'referenceType': 2, 'referenceId': 12345, 'status': 1},
                {'referenceType': 3, 'referenceId': 12345, 'status': 1,
                 'externalReference': {'name': 'Synthetic guest', 'gender': 'F'}},
                {'referenceType': 3, 'referenceId': None, 'status': 1,
                 'externalReference': None},
            ],
        }

        def response(path):
            if path.startswith('/meets/by-ref/'):
                return event
            if path.startswith('/players/userIds?'):
                return {'players': [{'userId': 12345, 'name': 'Synthetic member', 'gender':'M'}]}
            self.fail(f'Unexpected fixed Reclub API path: {path}')

        with patch('picklequeue.reclub._get_json', side_effect=response) as get_json:
            result = preview_event('https://reclub.co/m/ABC123')

        self.assertEqual(result['club_key'], 'group:42')
        self.assertEqual([p['name'] for p in result['players']],
                         ['Synthetic member', 'Guest (name unavailable)', 'Synthetic guest', 'Guest (name unavailable)'])
        self.assertEqual(len({p['external_id'] for p in result['players']}), 4)
        self.assertEqual([player['gender'] for player in result['players']],['M',None,'F',None])
        self.assertEqual(get_json.call_count, 2)

    def test_invalid_upstream_shape_is_rejected(self):
        with patch('picklequeue.reclub._get_json', return_value={'participants': None}):
            with self.assertRaises(Problem):
                preview_event('https://reclub.co/m/ABC123')


if __name__ == '__main__':
    unittest.main()
