"""Add (or refresh) this app's site block in another Caddy's Caddyfile, between managed markers.

Usage: python3 register_site.py CADDYFILE DOMAIN USER PASSWORD_HASH
Writes in place (same inode, so a single-file bind mount in the running container sees the change)
and keeps a timestamped backup next to it. Prints the backup path.
"""

from __future__ import annotations

import re
import shutil
import sys
import time

BEGIN, END = "# >>> governed-banking (managed by deploy/deploy.sh)", "# <<< governed-banking"


def block(domain: str, user: str, pw_hash: str) -> str:
    return f"""{BEGIN}
{domain} {{
	encode zstd gzip
	@gated {{
		not {{
			path /api/*
			header Authorization "Bearer *"
			not path /api/login
		}}
	}}
	basic_auth @gated {{
		{user} {pw_hash}
	}}
	handle_path /api/* {{
		reverse_proxy gba-api:8000 {{
			flush_interval -1
		}}
	}}
	handle {{
		reverse_proxy gba-web:3000
	}}
}}
{END}
"""


def merge(current: str, new_block: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
    if pattern.search(current):
        return pattern.sub(lambda _: new_block, current)
    return current.rstrip("\n") + "\n\n" + new_block


def main() -> None:
    path, domain, user, pw_hash = sys.argv[1:5]
    backup = f"{path}.bak.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    with open(path, encoding="utf-8") as f:
        current = f.read()
    with open(path, "w", encoding="utf-8") as f:  # truncate + write keeps the inode
        f.write(merge(current, block(domain, user, pw_hash)))
    print(backup)


if __name__ == "__main__":
    main()
