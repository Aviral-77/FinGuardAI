# Demo scripts

Preset triggers so nothing has to be typed on stage. Each hits the live API; the
canvas reacts over WebSocket. Point them at a different host with
`BASE=http://host:8000 ./01-victim-transfer.sh`.

Run order:

| Beat | Script | What it proves |
|---|---|---|
| 0 | `00-reset.sh` | A normal afternoon — nothing flagged |
| 1 | `01-victim-transfer.sh` | Victim lands at 35, **Monitor only** — the system does not cry wolf |
| 2 | `02-fanout.sh` | Scores climb, the ring assembles, the hub crosses 86 |
| 3 | `03-freeze.sh` | Contain the ring |
| 3 | `04-blocked-attempt.sh` | A further transfer into the frozen mule **bounces (409)** — the freeze is real |
| — | `05-download-report.sh` | The full bank-grade case PDF |

The same beats are wired to the on-screen control strip and to the number keys
`0/1/2/3`, so you can drive the whole demo from the browser without a terminal.
