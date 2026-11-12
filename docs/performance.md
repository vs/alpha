# Performance

| Component | Metric | Budget | Measured by |
|---|---|---|---|
| alpha | startup | 200 ms | an end-to-end pytest test that times bin/alpha --help, run by mise run check |

A change that breaks a budget is fixed, or the budget is changed by a decision record.

## Expected load

one developer running alpha on a laptop, against one project at a time

Reviews judge scale against this load, and a `shortcut:` comment names the load past which its shortcut stops holding.
