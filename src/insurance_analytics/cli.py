import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Synthetic insurance analytics portfolio")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--output", default="artifacts/demo")
    demo.add_argument("--backend", choices=["logistic", "xgboost"], default="logistic")
    for name, port in [("dashboard", 8050), ("api", 8000)]:
        command = sub.add_parser(name)
        command.add_argument("--host", default="127.0.0.1")
        command.add_argument("--port", type=int, default=port)
    args = parser.parse_args()
    if args.command == "demo":
        from .demo import run

        print(json.dumps(run(args.output, args.backend), indent=2))
    elif args.command == "dashboard":
        from .dashboard import create_dashboard

        create_dashboard().run(host=args.host, port=args.port, debug=False)
    else:
        import uvicorn

        uvicorn.run("insurance_analytics.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
