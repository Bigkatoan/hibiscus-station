# Hibiscus server contract snapshot

`hibiscus-v0.1.1/` is the API contract of the Hibiscus server (`api/openapi.yaml` and the policy schema
files the fake server reads: `act`, `diffusion`, `train`, `presets`) at tag
[`v0.1.1`](https://github.com/Bigkatoan/Hibiscus/tree/v0.1.1/api), the version the pinned
`hibiscus` CLI dependency (`pyproject.toml`) was released with. `../fake_server.py` and
`../openapi_contract.py` come from the same tag (`cli/tests/`). The only edit: the example server
host is `hibiscus.example.com`.

Station never calls the server directly: pairing, uploads, pulls and the run list all go through the
CLI package (`hibiscus_station/remote.py`). When the CLI pin moves to a new tag, refresh these files
from that tag in the same commit.
