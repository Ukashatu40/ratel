"""Domain: what the ledger knows, as plain data and rules. The innermost layer.

May import: the standard library. Must not import: any other bss_money layer, SQLAlchemy, a
database driver, FastAPI. No I/O, no logging, no clock. If a rule can be written here, write it
here: it is the easiest code to test and to review.
"""
