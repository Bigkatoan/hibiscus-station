# Security policy

Hibiscus Station controls a machine that moves. Its web UI and API can start motions, so we treat
any way around its local security model (loopback binding, login token, Host/Origin allow-lists,
CSRF header) as a vulnerability. Thank you for helping keep its users safe.

## Supported versions

| Version | Supported |
|---|---|
| `main` | ✅ security fixes land here first |
| latest `0.x` release (wheel and images) | ✅ fixes are released as a patch version |
| older releases | ❌ please upgrade (`hibiscus-station-ctl update`) |

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a security problem.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/Bigkatoan/hibiscus-station/security/advisories/new)
(*Security* tab → *Report a vulnerability*). Please include the version or commit, the install
type (Docker variant or wheel), a description and its impact, steps to reproduce (against your own
setup only) and any suggested fix.

| Step | Target |
|---|---|
| Acknowledgement | within 3 working days |
| Initial assessment and severity (CVSS v3.1) | within 7 days |
| Fix or mitigation for critical / high issues | within 30 days |
| Public advisory (GitHub Security Advisory, CVE when applicable) | when a fixed release is available |

We will keep you informed and, if you wish, credit you in the advisory. Please allow coordinated
disclosure (90 days by default).

## Scope

In scope: the code in this repository, the images built from `docker/`, and the default
deployment in `deploy/` (compose files, udev rule, `install.sh`, `hibiscus-station-ctl`, the
systemd unit).

Out of scope: vulnerabilities in LeRobot, PyTorch, NVIDIA base images or other upstream
dependencies (report them upstream; tell us if Station is affected), the Hibiscus server (report
to [Bigkatoan/Hibiscus](https://github.com/Bigkatoan/Hibiscus/security/advisories/new)), attacks
that need an already-valid login token (anyone with the token is allowed to move the robot), plain
HTTP sniffing in the opt-in LAN mode (documented), and physical access to the robot computer.

## Hardening guidance

* Keep the default: Station on `127.0.0.1`, reached locally or through an SSH tunnel.
* LAN mode only on a trusted network, with a random token (`secrets.token_urlsafe(32)`) and the
  exact host names; a TLS reverse proxy for anything wider; never expose Station to the Internet.
* Give the Station's server pairing a personal access token with the minimum scopes
  (`datasets:write`, `models:read`, `runs:read`), and revoke it on the server if the robot computer
  is lost.
* Backups made by `hibiscus-station-ctl` contain that token: keep them private (they are 0600).
* The e-stop is software. Keep a physical power switch for the arms.
