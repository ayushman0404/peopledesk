# PeopleDesk security boundaries

## Authentication and roles

Company accounts require a password or verified Google identity. Uninvited registrations need human approval; invitation links are random, hashed at rest, email-bound, expire after seven days and are usable once. Setup requires a random bootstrap token from the first launch. Access roles are checked on the server. HR cannot grant owner/HR privilege, and an owner cannot deactivate or demote their own active account. Deactivated accounts are rejected on subsequent API calls.

Session cookies are HttpOnly and SameSite=Lax, with Secure enabled for HTTPS. Sessions expire after eight hours and live in memory. Restarting the service signs everyone out. Changing a password revokes that person's sessions. Mutating API requests validate the exact Origin and Host. Passwords use salted PBKDF2-HMAC-SHA256 (240,000 iterations). Failed password attempts are limited per email; unauthenticated login/registration/OAuth requests also have a bounded per-connection-address rate limit. MFA, password recovery, enterprise SAML/SCIM and comprehensive abuse monitoring are not included.

Google sign-in uses state, a browser cookie, nonce and PKCE. The google-auth library verifies token signatures, issuer, audience and expiry. Sign-in membership uses the verified email only for an exact existing account match; subsequent identity links use the Google subject. User-entered role/domain claims never grant membership. Resource connections are separate, scoped to the member and stored under that member's identity. No test identity verifier is shipped in the application.

## Message encryption protocol

Each browser identity has an RSA-OAEP/SHA256 3072-bit encryption key and an ECDSA P-256 signing key, generated with WebCrypto. Each message gets a fresh AES-256-GCM key and random 96-bit IV. That AES key is wrapped separately for every fixed conversation participant. The signed, canonical envelope binds the protocol version, workspace, room, sender, message ID, roster digest, ciphertext and wrapped keys. AES additional authenticated data binds the same context. The browser verifies the sender's signature before displaying decrypted text.

The API checks the authenticated sender, membership, workspace/room/roster bindings, expected recipients and payload sizes. Repeated identical message IDs are idempotent; conflicting reuse is rejected. Signature authenticity is checked by recipient browsers, not by the storage service. Unauthorized room reads have no administrator bypass.

The encrypted private-key backup uses PBKDF2-SHA256 with 600,000 iterations and a random salt, then AES-GCM with a random IV and workspace/account-bound context. The passphrase and decrypted private keys are not sent to the server. Unlocked keys are held as non-extractable CryptoKey objects in memory and cleared by the application on logout/lock. An encrypted backup is still susceptible to offline passphrase guessing; use a long, unique passphrase and retain it safely.

First-contact public keys are trusted on first use and fingerprint-pinned per local browser account. Compare fingerprints independently to authenticate the initial contact. A new browser starts without those old pins. There is no public key-transparency service. Group membership is immutable, and group titles/participants/timing remain clear metadata. The protocol does not provide forward secrecy, post-compromise security, key rotation, administrative chat recovery or audited protection equivalent to a mature secure messenger.

## Limits of browser-delivered encryption

Ordinary database inspection and the administrative app account do not reveal message plaintext. However, the host operator controls the application code delivered to browsers. Malicious JavaScript, an extension, an infected device or a participant can expose decrypted messages. Non-extractable keys do not stop malicious same-origin code from invoking decryption. Do not promise protection from a malicious application distributor.

The protocol has local functional and tamper checks, but no independent cryptographic audit. Use a reviewed messaging protocol and a reviewed client-distribution model before making a strong company-wide confidentiality commitment. See the [WebCrypto security considerations](https://www.w3.org/TR/2017/REC-WebCryptoAPI-20170126/#security-considerations).

## Data and integrations

Ordinary HR records, local files, provider previews and audit records are stored in SQLite without database-level encryption. File access scopes are enforced by API checks, but the host's OS administrator can inspect ordinary data. Windows DPAPI protects OAuth credentials under the service account. Protect the host, backups and HTTPS endpoint accordingly. No employee chat plaintext is passed into the AI assistant.

Provider writes require explicit user actions; sensitive HR drafts and requests also require approval. Completion IDs and states prevent duplicate sends. Unknown outcomes remain marked for provider verification after timeouts or interrupted runs. There is no automatic retry of uncertain writes. Google calendar/task copying is an on-demand operation, not a guarantee of full two-way synchronization.

The service is a single-process threaded HTTP/SQLite pilot. It binds to loopback by default, expects a separately managed HTTPS proxy for other devices, and has not been tested for large concurrent workforces. High-availability operations, automated backups, retention/erasure administration, disaster recovery, code signing, penetration testing and enterprise identity lifecycle controls remain deployment work.


## Reporting a vulnerability

Email Ayushman Choudhary at ayushman0404@gmail.com with a minimal reproduction using fictional data. Please do not post exploitable details or employee data in a public issue. There is no guaranteed response SLA.
