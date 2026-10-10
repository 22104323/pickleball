"""Deploy an approved immutable Git commit using Vercel's REST API."""

import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tools.vercel_preflight import validate_website


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deployment_payload(environment, branch, sha, project):
    expected = {'staging': 'staging', 'production': 'main'}.get(environment)
    if expected is None or branch != expected:
        raise ValueError('Deployment environment does not match its approved branch.')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Deployments must identify one immutable commit SHA.')
    if not re.fullmatch(r'prj_[A-Za-z0-9]+', project):
        raise ValueError('Set VERCEL_PROJECT_ID to the connected Vercel project ID.')
    body = {'name': 'pickleball', 'project': project,
            'gitSource': {'type': 'github', 'repoId': '1412368090', 'ref': branch, 'sha': sha}}
    if environment == 'production':
        body['target'] = 'production'
    return body


def request_api(path, token, team, body=None):
    query = '?' + urlencode({'teamId': team}) if team else ''
    request = Request('https://api.vercel.com' + path + query,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                      method='POST' if body is not None else 'GET')
    try:
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise RuntimeError('Vercel returned an oversized response.')
            return json.loads(raw)
    except HTTPError as error:
        status = error.code
        error.close()
        raise RuntimeError(f'Vercel API returned HTTP {status}; inspect the Vercel dashboard. Response contents are withheld.') from None
    except (URLError, ValueError):
        raise RuntimeError('Vercel request failed; inspect the dashboard before retrying a deployment.') from None


def wait_ready(deployment, token, team, timeout=900):
    deadline = time.monotonic() + timeout
    while True:
        state = deployment.get('readyState') or deployment.get('status')
        if state == 'READY':
            return deployment
        if state in {'ERROR', 'CANCELED'}:
            raise RuntimeError('Vercel deployment did not become ready; inspect its build logs in Vercel.')
        if time.monotonic() >= deadline:
            raise RuntimeError('Vercel readiness timed out; deployment may still be running. Inspect it before retrying.')
        id_deployment = deployment.get('id')
        if not isinstance(id_deployment, str) or not re.fullmatch(r'dpl_[A-Za-z0-9]+', id_deployment):
            raise RuntimeError('Vercel did not return a valid deployment ID.')
        time.sleep(10)
        deployment = request_api('/v13/deployments/' + id_deployment, token, team)


def main():
    error = validate_website(Path(__file__).resolve().parent.parent)
    if error:
        print(error)
        return 1
    if os.environ.get('VERCEL_WEBSITE_READY') != 'true':
        print('A maintainer must complete the hosting review and set VERCEL_WEBSITE_READY=true in this GitHub environment.')
        return 1
    token = os.environ.get('VERCEL_TOKEN')
    if not token:
        print('Set VERCEL_TOKEN in the protected GitHub environment; never commit it.')
        return 1
    try:
        body = deployment_payload(os.environ.get('DEPLOY_ENVIRONMENT'), os.environ.get('GITHUB_REF_NAME'),
                                  os.environ.get('GITHUB_SHA', ''), os.environ.get('VERCEL_PROJECT_ID', ''))
        team = os.environ.get('VERCEL_TEAM_ID', '')
        deployment = request_api('/v13/deployments', token, team, body)
        wait_ready(deployment, token, team)
        print('Vercel deployment is READY. Commit: ' + os.environ['GITHUB_SHA'])
        return 0
    except (ValueError, RuntimeError) as error:
        print(str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
