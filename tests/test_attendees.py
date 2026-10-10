import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from api.attendees import ERROR_HEADERS, SUCCESS_HEADERS, handler, response_for_event
from picklequeue.engine import Problem
from picklequeue.reclub import _API_OPENER, _NoRedirect, _avatar_url, _get_json, public_attendee_feed


class PublicAttendeeFeedTests(unittest.TestCase):
    def test_feed_returns_only_confirmed_signups_and_approved_fields(self):
        event = {
            'name':'<Synthetic open play>',
            'accessToken':'must not be copied',
            'participants':[
                {'id':101,'referenceType':1,'referenceId':123,'status':1},
                {'id':102,'referenceType':1,'referenceId':456,'status':3},
                {'id':103,'referenceType':2,'referenceId':123,'status':1},
                {'id':104,'referenceType':3,'referenceId':123,'status':1,
                 'externalReference':{'name':'Synthetic guest'}},
                {'id':105,'referenceType':3,'referenceId':None,'status':1,'externalReference':None},
                {'id':106,'referenceType':99,'referenceId':123,'status':1},
                {'id':107,'referenceType':1,'referenceId':456,'status':1},
                {'id':108,'referenceType':1,'referenceId':789,'status':True},
            ],
        }

        def response(path, timeout):
            if path == '/meets/by-ref/ABC123':
                return event
            if path == '/players/userIds?userIds=123,456&scopes=BASIC_PROFILE':
                return {'players':[{'userId':123,'name':'Synthetic player',
                                    'imageUrl':'https://assets.reclub.co/avatar/sample.jpg',
                                    'accessToken':'must not be copied'}]}
            self.fail(f'Unexpected upstream request: {path}')

        with patch('picklequeue.reclub._get_json', side_effect=response) as get_json:
            result = public_attendee_feed('abc123')

        self.assertEqual(result['event']['title'],'<Synthetic open play>')
        self.assertEqual([signup['slotId'] for signup in result['signups']],
                         ['101','103','104','105','107'])
        self.assertEqual([signup['name'] for signup in result['signups']],
                         ['Synthetic player','Guest (name unavailable)','Synthetic guest',
                          'Guest (name unavailable)','Player (name unavailable)'])
        self.assertEqual(result['signups'][0]['avatarUrl'],'https://assets.reclub.co/avatar/sample.jpg')
        self.assertEqual({key for signup in result['signups'] for key in signup},
                         {'slotId','status','name','avatarUrl'})
        self.assertTrue(all(signup['status'] == 1 for signup in result['signups']))
        self.assertEqual(len({signup['slotId'] for signup in result['signups']}),5)
        self.assertEqual(len(result['warnings']),3)
        self.assertRegex(result['fetchedAt'],r'^\d{4}-\d\d-\d\dT.*Z$')
        self.assertNotIn('accessToken',json.dumps(result))
        self.assertEqual(get_json.call_count,2)
        self.assertTrue(all(call.kwargs['timeout'] == 5 for call in get_json.call_args_list))

    def test_profiles_are_requested_in_batches_of_fifty(self):
        event = {'name':'Synthetic event','participants':[
            {'id':index,'referenceType':1,'referenceId':index,'status':1}
            for index in range(1,52)
        ]}
        profile_paths = []

        def response(path, timeout):
            if path.startswith('/meets/by-ref/'):
                return event
            profile_paths.append(path)
            ids = path.split('userIds=',1)[1].split('&',1)[0]
            return {'players':[{'userId':int(value),'name':f'Synthetic {value}'} for value in ids.split(',')]}

        with patch('picklequeue.reclub._get_json', side_effect=response):
            result = public_attendee_feed('ABCD')

        self.assertEqual(len(profile_paths),2)
        self.assertEqual(len(profile_paths[0].split('userIds=',1)[1].split('&',1)[0].split(',')),50)
        self.assertEqual(len(profile_paths[1].split('userIds=',1)[1].split('&',1)[0].split(',')),1)
        self.assertEqual(len(result['signups']),51)
        self.assertEqual(result['warnings'],[])

    def test_invalid_reference_does_not_contact_reclub(self):
        with patch('picklequeue.reclub._get_json') as get_json:
            with self.assertRaises(Problem):
                public_attendee_feed('https://attacker.invalid/m/ABC123')
        get_json.assert_not_called()

    def test_invalid_event_shape_and_limits_are_errors_not_empty_feeds(self):
        with patch('picklequeue.reclub._get_json', return_value={'participants':None}):
            with self.assertRaises(Problem):
                public_attendee_feed('ABC123')
        too_many = {'participants':[{'status':1,'referenceType':2} for _ in range(201)]}
        with patch('picklequeue.reclub._get_json', return_value=too_many):
            with self.assertRaises(Problem):
                public_attendee_feed('ABC123')
        oversized = {'participants':[{} for _ in range(1001)]}
        with patch('picklequeue.reclub._get_json', return_value=oversized):
            with self.assertRaises(Problem):
                public_attendee_feed('ABC123')

    def test_only_validated_reclub_cdn_avatars_are_returned(self):
        self.assertEqual(_avatar_url('https://assets.reclub.co/image.jpg'),
                         'https://assets.reclub.co/image.jpg')
        self.assertEqual(_avatar_url('https://d1upr18ac2olqz.cloudfront.net/user.png'),
                         'https://d1upr18ac2olqz.cloudfront.net/user.png')
        for value in (
            'http://assets.reclub.co/image.jpg',
            'https://assets.reclub.co.attacker.invalid/image.jpg',
            'https://user@assets.reclub.co/image.jpg',
            'https://assets.reclub.co/image.jpg?token=secret',
            'https://assets.reclub.co/image.jpg#fragment',
            'https://attacker.invalid/image.jpg',
        ):
            with self.subTest(value=value):
                self.assertIsNone(_avatar_url(value))

    def test_single_bounded_retry_is_used_for_upstream_rate_limit(self):
        error = HTTPError('https://api.reclub.co/meets/by-ref/ABC123',429,'rate limited',
                          {'Retry-After':'9'},None)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self,*args):
                return False

            def read(self,limit):
                return b'{"ok":true}'

        with patch('picklequeue.reclub._open_api',side_effect=[error,Response()]) as open_url, \
                patch('picklequeue.reclub.time.sleep') as sleep:
            self.assertEqual(_get_json('/health',timeout=5),{'ok':True})
        self.assertEqual(open_url.call_count,2)
        sleep.assert_called_once_with(1)

    def test_upstream_redirect_is_not_followed(self):
        redirect = next(item for item in _API_OPENER.handlers if isinstance(item,_NoRedirect))
        self.assertIsNone(redirect.redirect_request(None,None,302,'redirect',{},
                                                   'https://unrelated.invalid/'))

    def test_route_requires_configuration_and_never_caches_failures(self):
        status,payload,headers = response_for_event('')
        self.assertEqual(status,503)
        self.assertIn('error',payload)
        self.assertEqual(headers,ERROR_HEADERS)
        with patch('api.attendees.public_attendee_feed',side_effect=Problem('upstream unavailable',502)):
            status,payload,headers = response_for_event('ABC123')
        self.assertEqual(status,502)
        self.assertEqual(payload,{'error':'upstream unavailable'})
        self.assertEqual(headers,ERROR_HEADERS)

    def test_route_success_uses_short_lived_cdn_cache(self):
        feed = {'event':{'title':'Synthetic event'},'signups':[],'warnings':[],
                'fetchedAt':'2026-10-10T00:00:00Z'}
        with patch('api.attendees.public_attendee_feed',return_value=feed) as load:
            status,payload,headers = response_for_event('ABC123')
        self.assertEqual(status,200)
        self.assertEqual(payload,feed)
        self.assertEqual(headers,SUCCESS_HEADERS)
        load.assert_called_once_with('ABC123')
        self.assertIn('s-maxage=60',headers['Cache-Control'])
        self.assertIn('stale-if-error=600',headers['Cache-Control'])

    def test_http_route_is_read_only_and_rejects_query_based_event_selection(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_address[1]}/api/attendees'
        try:
            with patch.dict(os.environ,{'RECLUB_EVENT_REF':'ABC123'}), \
                    patch('api.attendees.public_attendee_feed') as feed:
                with self.assertRaises(HTTPError) as query_error:
                    urlopen(base + '?event=attacker-controlled')
                self.assertEqual(query_error.exception.code,400)
                query_error.exception.close()
                request = Request(base,data=b'{}',method='POST')
                with self.assertRaises(HTTPError) as post_error:
                    urlopen(request)
                self.assertEqual(post_error.exception.code,405)
                self.assertEqual(post_error.exception.headers.get('Allow'),'GET')
                post_error.exception.close()
                feed.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
