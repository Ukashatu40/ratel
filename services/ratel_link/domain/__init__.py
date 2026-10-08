"""Domain: what RatelLink knows, as plain data and rules. The innermost layer.

May import: the standard library and pydantic. Must not import: any other ratel_link layer,
FastAPI, a database driver or a crypto library. No I/O, no logging, no clock. If a rule can be
written here, write it here: it is the easiest code to test and to review.
"""
