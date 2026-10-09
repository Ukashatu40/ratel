"""Security primitives: encryption of Ki/OPc, the key provider, API key format and hashing.

May import: domain, config, common, and the cryptography library. Must not import: api, services,
repositories. The key provider is an interface (`KeyProvider`) so a KMS can replace the file one.
"""
