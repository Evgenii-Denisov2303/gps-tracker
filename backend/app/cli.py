import argparse
import getpass
from datetime import timedelta

from sqlalchemy import delete, select

from .db import SessionLocal, utcnow
from .models import Admin, AdminSession, LocationPoint, LoginLimit
from .security import hasher


def main():
    parser = argparse.ArgumentParser(description="Fleet GPS administration")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("admin", help="Create admin or reset password (interactive)")
    admin.add_argument("username")
    viewer = commands.add_parser("viewer", help="Create/reset a read-only viewer; revokes existing sessions")
    viewer.add_argument("username")
    prune = commands.add_parser("prune", help="Explicitly delete points older than N days")
    prune.add_argument("--days", type=int, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command in ("admin", "viewer"):
            if not 1 <= len(args.username) <= 100:
                parser.error("Username length must be 1..100")
            password = getpass.getpass("Password (12+ characters): ")
            if len(password) < 12 or len(password) > 256:
                parser.error("Password must be 12..256 characters")
            if password != getpass.getpass("Repeat password: "):
                parser.error("Passwords differ")
            user = db.scalar(select(Admin).where(Admin.username == args.username))
            if user:
                user.password_hash = hasher.hash(password)
                user.read_only = args.command == "viewer"
                db.execute(delete(AdminSession).where(AdminSession.admin_id == user.id))
            else:
                db.add(Admin(username=args.username, password_hash=hasher.hash(password), read_only=args.command == "viewer"))
            db.commit()
            print("Account saved; existing sessions revoked. Role: " + args.command)
        else:
            if args.days < 1:
                parser.error("--days must be positive")
            result = db.execute(delete(LocationPoint).where(LocationPoint.gps_timestamp < utcnow() - timedelta(days=args.days)))
            db.execute(delete(AdminSession).where(AdminSession.expires_at < utcnow()))
            db.execute(delete(LoginLimit).where(LoginLimit.reset_at < utcnow()))
            db.commit()
            print(f"Deleted {result.rowcount} old GPS points.")


if __name__ == "__main__":
    main()
