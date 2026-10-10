"""Bounded read-only compatibility adapter for public Reclub event links."""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .engine import Problem

API = 'https://api.reclub.co'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Courtside/1.0)',
    'x-output-casing': 'camelCase',
    'Accept': 'application/json',
}
MAX_RESPONSE = 2_000_000
MAX_PLAYERS = 200
MAX_EVENT_PARTICIPANTS = 1000
PROFILE_BATCH_SIZE = 50
PUBLIC_REQUEST_TIMEOUT = 5
REFERENCE = re.compile(r'^[A-Za-z0-9]{4,12}$')
AVATAR_HOSTS = frozenset({'assets.reclub.co', 'd1upr18ac2olqz.cloudfront.net'})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_API_OPENER = build_opener(_NoRedirect())


def _open_api(request, timeout):
    return _API_OPENER.open(request, timeout=timeout)


def reference_from_url(value):
    if not isinstance(value, str) or len(value) > 500:
        raise Problem('Paste a public Reclub event link.')
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise Problem('That Reclub link is not valid.') from error
    if parsed.scheme != 'https' or parsed.hostname not in ('reclub.co','www.reclub.co') or parsed.username or parsed.password or port not in (None,443):
        raise Problem('Use an HTTPS link from reclub.co.')
    parts = parsed.path.strip('/').split('/')
    if len(parts) != 2 or parts[0] != 'm' or not REFERENCE.fullmatch(parts[1]):
        raise Problem('Use a public event link in the form https://reclub.co/m/ABC123.')
    return parts[1].upper()


def _get_json(path, timeout=8):
    request = Request(f'{API}{path}', headers=HEADERS)
    for attempt in range(2):
        try:
            with _open_api(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
            break
        except HTTPError as error:
            if error.code == 429 and attempt == 0:
                try:
                    delay = min(max(float(error.headers.get('Retry-After', '1')), 0), 1)
                except (AttributeError, TypeError, ValueError):
                    delay = 1
                error.close()
                time.sleep(delay)
                continue
            error.close()
            raise Problem(f'Reclub could not load this event (HTTP {error.code}).',502) from error
        except (URLError, TimeoutError, OSError) as error:
            raise Problem('Reclub could not be reached. Try again later.',502) from error
    else:
        raise Problem('Reclub could not be reached. Try again later.',502)
    if len(raw) > MAX_RESPONSE:
        raise Problem('The Reclub response was too large to review.',502)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise Problem('Reclub returned an unreadable event response.',502) from error


def _profiles(user_ids, timeout=8):
    found = {}
    for start in range(0,len(user_ids),PROFILE_BATCH_SIZE):
        batch = user_ids[start:start+PROFILE_BATCH_SIZE]
        ids = ','.join(str(value) for value in batch)
        payload = _get_json(f'/players/userIds?userIds={ids}&scopes=BASIC_PROFILE', timeout=timeout)
        players = payload.get('players') if isinstance(payload,dict) else None
        if not isinstance(players,list):
            raise Problem('Reclub returned an invalid player profile list.',502)
        for player in players:
            if not isinstance(player,dict) or type(player.get('userId')) is not int:
                continue
            name = player.get('name')
            if isinstance(name,str) and name.strip():
                gender = player.get('gender') if player.get('gender') in ('M','F') else None
                found[player['userId']] = {
                    'name':name.strip()[:80],
                    'gender':gender,
                    'avatar_url':_avatar_url(player.get('imageUrl')),
                }
    return found


def _avatar_url(value):
    if not isinstance(value,str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname.lower() if parsed.hostname else None
    if (parsed.scheme != 'https' or host not in AVATAR_HOSTS or parsed.username
            or parsed.password or port not in (None,443) or not parsed.path.startswith('/')
            or parsed.query or parsed.fragment):
        return None
    return urlunsplit(('https',host,parsed.path,'',''))


def _slot_id(item, index):
    value = item.get('id')
    if value is None:
        value = item.get('participantId')
    if type(value) is int and value >= 0:
        return str(value)
    if isinstance(value,str) and 0 < len(value.strip()) <= 100 and not any(ord(char) < 32 for char in value):
        return value.strip()
    stable_fields = {
        'index':index,
        'referenceType':item.get('referenceType') if type(item.get('referenceType')) is int else None,
        'referenceId':item.get('referenceId') if type(item.get('referenceId')) is int else None,
        'createdAt':item.get('createdAt') if isinstance(item.get('createdAt'),str) else None,
        'lastStatusUpdatedAt':item.get('lastStatusUpdatedAt') if isinstance(item.get('lastStatusUpdatedAt'),str) else None,
    }
    digest = hashlib.sha256(json.dumps(stable_fields,sort_keys=True).encode()).hexdigest()[:24]
    return f'derived:{digest}'


def public_attendee_feed(event_reference):
    """Return an allow-listed, read-only feed for one configured public event."""
    if not isinstance(event_reference,str) or not REFERENCE.fullmatch(event_reference):
        raise Problem('Reclub sign-ups are not configured for this website.',503)
    reference = event_reference.upper()
    payload = _get_json(f'/meets/by-ref/{reference}', timeout=PUBLIC_REQUEST_TIMEOUT)
    if not isinstance(payload,dict) or not isinstance(payload.get('participants'),list):
        raise Problem('Reclub returned an unsupported event format.',502)
    participants = payload['participants']
    if len(participants) > MAX_EVENT_PARTICIPANTS:
        raise Problem('This Reclub event is too large to load safely.',502)
    unsupported_statuses = any(
        not isinstance(item,dict) or type(item.get('status')) is not int or item['status'] != 1
        for item in participants
    )
    signups = [item for item in participants
               if isinstance(item,dict) and type(item.get('status')) is int and item['status'] == 1]
    if len(signups) > MAX_PLAYERS:
        raise Problem('This Reclub event has too many sign-ups to load safely.',502)
    user_ids = sorted({item.get('referenceId') for item in signups
                       if type(item.get('referenceType')) is int and item['referenceType'] == 1
                       and type(item.get('referenceId')) is int and item['referenceId'] > 0})
    profiles = _profiles(user_ids, timeout=PUBLIC_REQUEST_TIMEOUT) if user_ids else {}
    missing_profiles = any(user_id not in profiles for user_id in user_ids)
    output = []
    unsupported_slots = False
    for index,item in enumerate(signups):
        kind = item.get('referenceType')
        reference_id = item.get('referenceId')
        external = item.get('externalReference')
        avatar_url = None
        if type(kind) is int and kind == 1 and type(reference_id) is int and reference_id > 0:
            profile = profiles.get(reference_id)
            name = profile['name'] if profile else 'Player (name unavailable)'
            avatar_url = profile['avatar_url'] if profile else None
        elif type(kind) is int and kind in (2,3):
            if (kind == 3 and isinstance(external,dict) and isinstance(external.get('name'),str)
                    and external['name'].strip()):
                name = external['name'].strip()[:80]
            else:
                name = 'Guest (name unavailable)'
        else:
            unsupported_slots = True
            continue
        output.append({
            'slotId':_slot_id(item,index),
            'status':1,
            'name':name,
            'avatarUrl':avatar_url,
        })
    title = payload.get('name')
    if not isinstance(title,str) or not title.strip():
        title = f'Reclub event {reference}'
    warnings = []
    if missing_profiles:
        warnings.append('Some player profiles were unavailable; neutral names are shown for those sign-ups.')
    if unsupported_statuses:
        warnings.append('Only participants with Reclub status 1 are shown; other statuses were omitted.')
    if unsupported_slots:
        warnings.append('Some sign-ups used an unsupported participant type and were omitted.')
    fetched_at = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    return {'event':{'title':title.strip()[:120]},'signups':output,'warnings':warnings,'fetchedAt':fetched_at}


def preview_event(value):
    reference = reference_from_url(value)
    payload = _get_json(f'/meets/by-ref/{reference}')
    if not isinstance(payload,dict) or not isinstance(payload.get('participants'),list):
        raise Problem('Reclub returned an unsupported event format.',502)
    raw_participants = payload['participants']
    if len(raw_participants) > 1000:
        raise Problem('This Reclub event is too large to review safely.',502)
    confirmed = [(index,item) for index,item in enumerate(raw_participants)
                 if isinstance(item,dict) and item.get('status') == 1]
    if len(confirmed) > MAX_PLAYERS:
        raise Problem('Review events with at most 200 confirmed players.',413)
    user_ids = sorted({item.get('referenceId') for _,item in confirmed
                       if item.get('referenceType') == 1 and type(item.get('referenceId')) is int and item['referenceId'] > 0})
    profile_names = _profiles(user_ids) if user_ids else {}
    output = []
    for index,item in confirmed:
        kind = item.get('referenceType')
        reference_id = item.get('referenceId')
        external = item.get('externalReference')
        if kind == 1 and type(reference_id) is int and reference_id > 0:
            external_id = f'user:{reference_id}'
            profile = profile_names.get(reference_id,{'name':'Player (name unavailable)','gender':None})
            name = profile['name']
            gender = profile['gender']
        elif kind == 3 and isinstance(external,dict) and isinstance(external.get('name'),str) and external['name'].strip():
            name = external['name'].strip()[:80]
            gender = external.get('gender') if external.get('gender') in ('M','F') else None
            stable = item.get('id') or item.get('participantId')
            if not isinstance(stable,(str,int)) or isinstance(stable,bool):
                stamp = f"{item.get('createdAt','')}|{item.get('lastStatusUpdatedAt','')}|{name}|{index}"
                stable = hashlib.sha256(stamp.encode()).hexdigest()[:20]
            external_id = f'slot:{stable}'
        elif kind in (2,3):
            name = 'Guest (name unavailable)'
            gender = None
            stamp = f"{kind}|{reference_id}|{item.get('createdAt','')}|{item.get('lastStatusUpdatedAt','')}|{index}"
            external_id = f'guest:{hashlib.sha256(stamp.encode()).hexdigest()[:20]}'
        else:
            continue
        output.append({'external_id':external_id,'name':name,'rating':None,'gender':gender,'club_group':None})
    title = payload.get('name')
    if not isinstance(title,str) or not title.strip():
        title = f'Reclub event {reference}'
    group_id = payload.get('groupId')
    club_key = f'group:{group_id}' if type(group_id) is int and group_id > 0 else f'event:{reference}'
    return {'reference':reference,'event_name':title.strip()[:120],'club_key':club_key,'players':output}
