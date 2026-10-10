"""Validate contribution names and the reviewed promotion route."""

import os
import re


def validate(title, head, base, same_repo=True, base_repo=''):
    if not re.fullmatch(r'(feat|fix|docs|ci|chore|test|refactor|perf|build|revert)\(#[1-9][0-9]*\): .+', title):
        return 'Use a Conventional Commit title with the real issue number, such as ci(#1): ...'
    if base == 'staging':
        if head != 'develop' or not same_repo:
            return 'Staging accepts promotion pull requests from this repository\'s develop branch only.'
    elif base == 'main':
        if head == 'staging' and same_repo:
            return None
        if base_repo == '22104323/pickleball':
            branch = re.fullmatch(r'(feature|bugfix|hotfix|release|docs)/#([1-9][0-9]*)', head)
            if not branch or branch.group(2) != re.search(r'\(#([1-9][0-9]*)\)', title).group(1):
                return 'Public main accepts issue-linked fork contributions or this repository\'s release/#<issue-number> branch.'
            if same_repo and branch.group(1) != 'release':
                return 'Maintainer-authored public changes use a temporary release/#<issue-number> branch.'
            return None
        if not same_repo:
            return 'Production accepts promotion pull requests from this repository\'s staging branch only.'
        return 'Production accepts promotion pull requests from this repository\'s staging branch only.'
    elif base == 'develop':
        branch = re.fullmatch(r'(feature|bugfix|hotfix|release|docs)/#([1-9][0-9]*)', head)
        if not branch:
            return 'Contributions use <type>/#<issue-number> and target develop.'
        if branch.group(2) != re.search(r'\(#([1-9][0-9]*)\)', title).group(1):
            return 'The PR title and contribution branch must reference the same real issue.'
    else:
        return 'Pull requests target develop, staging, or main.'
    return None


def main():
    error = validate(os.environ['PR_TITLE'], os.environ['HEAD_BRANCH'], os.environ['BASE_BRANCH'],
                     os.environ['HEAD_REPO'] == os.environ['BASE_REPO'], os.environ['BASE_REPO'])
    if error:
        print(error)
        return 1
    print('Pull request naming and promotion route passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
