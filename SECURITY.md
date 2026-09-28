# Security policy

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, private keys, personal paths,
job output, or account-specific SCNet data.

Use GitHub's private security-advisory reporting for this repository. Include the affected
version or commit, reproduction steps, and the expected impact. Replace all usernames,
HOME paths, job IDs, tokens, AK/SK values, and service URLs with placeholders.

## Credential boundary

- OpenAPI AK/SK belong in macOS Keychain, Linux Secret Service, or process environment.
- Region tokens are ephemeral and must not be persisted.
- SSH private keys belong under the user's `~/.ssh` directory with mode `0600`.
- Public issues and logs must use `$REMOTE_HOME` in place of personal absolute paths.
- Container inference must set `SCNET_SERVER_API_KEY`.

If a credential was exposed, revoke or rotate it before reporting the incident.
