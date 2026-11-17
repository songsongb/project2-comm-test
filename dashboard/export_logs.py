"""Read-only, streaming export of every raw record; safe while SQLite WAL is live."""
import argparse
import sqlite3
from pathlib import Path
from .config import DATA_DIR


def export(database, output):
    database, output = Path(database).resolve(), Path(output).resolve()
    if database == output:
        raise ValueError("출력 파일은 데이터베이스와 달라야 합니다")
    count = 0
    # mode=ro must not create an empty DB if a path is wrong.
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        with output.open("x", encoding="utf-8", newline="\n") as out:
            for (payload,) in db.execute("SELECT payload FROM records ORDER BY rowid"):
                out.write(payload + "\n")
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATA_DIR / "dashboard.sqlite3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.database, args.output)} raw records to {args.output}")


if __name__ == "__main__":
    main()
