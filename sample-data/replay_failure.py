import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def post_json(url: str, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a mixed stack failure into the IMS ingestion API.")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--file", default=str(Path(__file__).with_name("failure-events.json")))
    parser.add_argument("--repeat", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.02)
    args = parser.parse_args()

    events = json.loads(Path(args.file).read_text(encoding="utf-8"))
    sent = 0
    for _ in range(args.repeat):
        for event in events:
            post_json(f"{args.api}/signals", event)
            sent += 1
            time.sleep(args.sleep)
    print(f"sent={sent}")


if __name__ == "__main__":
    main()
