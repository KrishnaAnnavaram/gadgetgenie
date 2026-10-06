"""``gadgetgenie`` command line: seed, ask, eval, serve."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__


def _seed(args) -> None:
    from .config import Settings
    from .etl.seed import write_postgres, write_sqlite

    settings = Settings.from_env()
    devices: list[dict] = []
    if args.laptops_csv or args.phones_csv:
        from .etl.loaders import load_laptops, load_phones

        if not args.source:
            sys.exit("--source is required with CSV input (record where the data came from and its licence)")
        for path, loader in ((args.laptops_csv, load_laptops), (args.phones_csv, load_phones)):
            if not path:
                continue
            rows, report = loader(path, source=args.source, price_currency=args.price_currency,
                                  rate_to_usd=args.rate_to_usd, price_as_of=args.price_as_of)
            print(f"{path}: loaded {report.rows_loaded}/{report.rows_read}, rejected {len(report.rejected)}, "
                  f"missing values kept as NULL: {dict(report.missing.most_common(5))}")
            devices += rows
    else:
        from .etl.synthetic import generate

        devices = generate(seed=args.seed)
    if args.postgres:
        print(f"PostgreSQL: {write_postgres(devices, args.postgres)} devices")
    else:
        path = write_sqlite(devices, args.sqlite or settings.sqlite_path)
        print(f"SQLite: {path} ({len(devices)} devices)")


def _ask(args) -> None:
    from .core.service import build_recommender

    answer = build_recommender().ask(args.question)
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2, ensure_ascii=False, default=str))
        return
    print(answer.text)
    for note in answer.notes:
        print(f"note: {note}")
    if answer.sql:
        print(f"\nSQL ({answer.attempts} attempt(s)): {answer.sql}")
    for row in answer.rows:
        print("  " + ", ".join(f"{k}={'unknown' if v is None else v}" for k, v in row.items()))


def _eval(args) -> None:
    from .core.service import build_recommender
    from .evaluation import evaluate, format_report, load_gold

    report = evaluate(build_recommender(), load_gold(args.gold))
    print(format_report(report))
    if args.out:
        from pathlib import Path

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"report written to {out}")


def _serve(args) -> None:  # pragma: no cover - starts a server
    import uvicorn

    uvicorn.run("gadgetgenie.api.app:create_app", factory=True, host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gadgetgenie", description="Plain-English device recommendations")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="build the catalogue database (synthetic by default)")
    seed.add_argument("--seed", type=int, default=11)
    seed.add_argument("--sqlite", help="output path (default SQLITE_PATH)")
    seed.add_argument("--postgres", metavar="OWNER_DSN", help="load into PostgreSQL instead (owner account)")
    seed.add_argument("--laptops-csv")
    seed.add_argument("--phones-csv")
    seed.add_argument("--source", help="provenance string stored with every row")
    seed.add_argument("--price-currency", default="USD")
    seed.add_argument("--rate-to-usd", type=float, help="USD per unit of --price-currency used for conversion")
    seed.add_argument("--price-as-of", help="date the prices were collected (YYYY-MM-DD)")
    seed.set_defaults(func=_seed)

    ask = sub.add_parser("ask", help="ask one question")
    ask.add_argument("question")
    ask.add_argument("--json", action="store_true")
    ask.set_defaults(func=_ask)

    ev = sub.add_parser("eval", help="run the gold-set evaluation")
    ev.add_argument("--gold", help="gold JSONL file (default: bundled set)")
    ev.add_argument("--out", help="write the JSON report here")
    ev.set_defaults(func=_eval)

    serve = sub.add_parser("serve", help="run the web app (needs the 'api' extra)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)

    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args.func(args)


if __name__ == "__main__":
    main()
