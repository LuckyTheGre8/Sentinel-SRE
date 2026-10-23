import asyncio
import json

from sentinel_ops.demo import smoke

if __name__ == "__main__":
    print(json.dumps(asyncio.run(smoke(2)), indent=2))
