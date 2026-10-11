# Security policy

Maintainer: Modern Labyrinth. Camicus 0.1.0 is an experimental local checker and
bounded Mac audit. It does not certify a machine, sandbox an assistant, resist a
malicious same-user process/administrator, or authenticate unsigned receipts.
Only the latest alpha is maintained. There is no promised support period,
response time or patch SLA.

Report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/modernlabyrinth/camicus/security/advisories/new).
Do not put vulnerabilities, credentials, real project data, machine inventories
or private results in a public issue. If GitHub does not offer the private report
form, do not substitute a public issue or an unverified address; wait for the
maintainer to restore that channel.

Include affected version/archive digest, platform, expected/observed behavior
and a minimal fictional reproduction. The maintainer will reproduce, assess
scope and publish a versioned fix or explicit limitation when warranted.

The checker has no telemetry or runtime network calls. Your calling assistant,
cloud sync and backup software have their own data flows. Use authorized inputs
and storage and share evidence deliberately.
