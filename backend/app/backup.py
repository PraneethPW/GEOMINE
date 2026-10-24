"""Encrypted PostgreSQL backups and restore drills into a separate empty database."""

import argparse
import base64
import os
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from psycopg import connect
from psycopg.conninfo import conninfo_to_dict

from .config import settings

MAGIC = b"GEOMINE-BACKUP-1\n"


def encryption_key():
    try:
        key = base64.urlsafe_b64decode(
            os.environ.get("BACKUP_ENCRYPTION_KEY") or settings().backup_encryption_key
        )
    except (KeyError, ValueError):
        raise ValueError(
            "Set BACKUP_ENCRYPTION_KEY to a base64-encoded random 32-byte key."
        ) from None
    if len(key) != 32:
        raise ValueError("Backup key must contain exactly 32 random bytes.")
    return key


def postgres_environment(url):
    config = conninfo_to_dict(url)
    result = os.environ.copy()
    names = {
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "channel_binding": "PGCHANNELBINDING",
        "options": "PGOPTIONS",
    }
    for key, value in config.items():
        if key in names:
            result[names[key]] = value
    result["PGCONNECT_TIMEOUT"] = "20"
    return result


def backup(destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Use a new backup filename; existing backups are immutable.")
    key, iv = encryption_key(), os.urandom(12)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".geomine-backup-", dir=destination.parent
    )
    process = None
    try:
        with os.fdopen(descriptor, "wb") as output, tempfile.TemporaryFile() as errors:
            output.write(MAGIC + iv)
            encryptor = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
            encryptor.authenticate_additional_data(MAGIC)
            process = subprocess.Popen(
                [
                    os.environ.get("PG_DUMP_BIN", "pg_dump"),
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--schema=" + settings().database_schema,
                ],
                stdout=subprocess.PIPE,
                stderr=errors,
                env=postgres_environment(settings().database_url),
            )
            while chunk := process.stdout.read(1024 * 1024):
                output.write(encryptor.update(chunk))
            process.stdout.close()
            if process.wait() != 0:
                raise ValueError(
                    "PostgreSQL backup failed. Check connectivity and pg_dump/server version compatibility."
                )
            output.write(encryptor.finalize())
            output.write(encryptor.tag)
            output.flush()
            os.fsync(output.fileno())
        # Link provides atomic no-overwrite publication on the same filesystem.
        os.link(temporary, destination)
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait()
        Path(temporary).unlink(missing_ok=True)
    return {"status": "encrypted", "bytes": destination.stat().st_size}


def decrypt_to(archive, output):
    key = encryption_key()
    with Path(archive).open("rb") as source:
        if source.read(len(MAGIC)) != MAGIC:
            raise ValueError("Unsupported backup format.")
        iv = source.read(12)
        source.seek(-16, 2)
        tag = source.read(16)
        remaining = source.tell() - 16 - len(MAGIC) - 12
        source.seek(len(MAGIC) + 12)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(iv, tag)).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        while remaining > 0:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("Truncated backup.")
            output.write(decryptor.update(chunk))
            remaining -= len(chunk)
        output.write(decryptor.finalize())
        output.flush()


def restore(archive, target):
    production, destination = (
        conninfo_to_dict(settings().database_url),
        conninfo_to_dict(target),
    )
    if all(production.get(k) == destination.get(k) for k in ("host", "port", "dbname")):
        raise ValueError(
            "Restore target must be a separate database, never the application database."
        )
    with connect(target) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%' AND c.relkind IN ('r','p','v','m','S','f') LIMIT 1"
        ).fetchone()
        if exists:
            raise ValueError(
                "Restore target must be an empty database. Existing data is never replaced."
            )
    with tempfile.NamedTemporaryFile(
        prefix="geomine-restore-", suffix=".dump"
    ) as plain:
        decrypt_to(
            archive, plain
        )  # Authenticate the entire file before any database writes.
        result = subprocess.run(
            [
                os.environ.get("PG_RESTORE_BIN", "pg_restore"),
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                "--dbname=" + destination.get("dbname", ""),
                plain.name,
            ],
            env=postgres_environment(target),
            capture_output=True,
        )
        if result.returncode:
            raise ValueError(
                "Restore failed and was rolled back. Check target connectivity and PostgreSQL version."
            )
    return {"status": "restored-to-empty-database"}


def main():
    import json

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("create")
    save.add_argument("--output", type=Path, required=True)
    load = commands.add_parser("restore-drill")
    load.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create":
        result = backup(args.output)
    else:
        target = os.environ.get("RESTORE_DATABASE_URL", "")
        if not target:
            raise ValueError(
                "Set RESTORE_DATABASE_URL to a separate empty drill database."
            )
        result = restore(args.archive, target)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
