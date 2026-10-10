"""Bounded read-only compatibility adapter for public Reclub event links."""

import hashlib
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .engine import Problem

API = 'https://api.reclub.co'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Courtside/1.0)',
    'x-output-casing': 'camelCase',
    'Accept': 'application/json',
}
MAX_RESPONSE = 2_000_000
MAX_PLAYERS = 200
REFERENCE = re.compile(r'^[A-Za-z0-9]{4,12}$')


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


def _get_json(path):
    request = Request(f'{API}{path}', headers=HEADERS)
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        raise Problem(f'Reclub could not load this event (HTTP {error.code}).',502) from error
    except (URLError, TimeoutError, OSError) as error:
        raise Problem('Reclub could not be reached. Try again later.',502) from error
    if len(raw) > MAX_RESPONSE:
        raise Problem('The Reclub response was too large to review.',502)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise Problem('Reclub returned an unreadable event response.',502) from error


def _profiles(user_ids):
    found = {}
    for start in range(0,len(user_ids),50):
        batch = user_ids[start:start+50]
        ids = ','.join(str(value) for value in batch)
        payload = _get_json(f'/players/userIds?userIds={ids}&scopes=BASIC_PROFILE')
        players = payload.get('players') if isinstance(payload,dict) else None
        if not isinstance(players,list):
            raise Problem('Reclub returned an invalid player profile list.',502)
        for player in players:
            if not isinstance(player,dict) or type(player.get('userId')) is not int:
                continue
            name = player.get('name')
            if isinstance(name,str) and name.strip():
                gender = player.get('gender') if player.get('gender') in ('M','F') else None
                found[player['userId']] = {'name':name.strip()[:80],'gender':gender}
    return found


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
