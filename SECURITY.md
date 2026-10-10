# Security

Report vulnerabilities through [GitHub's private vulnerability reporting](https://github.com/22104323/pickleball/security/advisories/new).
Do not include credentials or player records in public issues. No response-time promise
is made; this project has one current maintainer and is an early local MVP.

The current Python organizer server has no login and binds to loopback. It must not be
exposed publicly. Reclub's anonymous participant endpoints are a compatibility observation,
not an authenticated organizer API or proof of physical attendance.

GitHub branch rules, required reviews, least-privilege workflow permissions, environment
approval, secret scanning/push protection, and local path/credential checks reduce specific
risks. They are not a security audit or a guarantee that every secret will be detected.
Never bypass a secret warning. If a credential has been committed or uploaded, revoke
or rotate it at its provider immediately, then arrange reviewed cleanup of the exposure.
Ignore rules alone cannot remove it from history.
