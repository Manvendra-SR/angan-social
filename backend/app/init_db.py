"""Create the database tables.

    python -m app.init_db            # create missing tables
    python -m app.init_db --reset    # DROP all tables, then create them

create_all() only creates tables that don't exist yet. It never alters an
existing table, so after changing a model either reset (dev data is lost)
or apply the change with ALTER TABLE by hand.
"""
import argparse
from sqlalchemy import create_engine
from app.core.config import settings
from app.models import Base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()

    # DDL goes over the direct (non-pooled) connection
    engine = create_engine(settings.DATABASE_URL)
    print(f"Database host: {engine.url.host}")

    if args.reset:
        answer = input("This deletes ALL data. Type 'reset' to continue: ")
        if answer != "reset":
            print("Aborted.")
            return
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")

    Base.metadata.create_all(engine)
    print("Tables:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
