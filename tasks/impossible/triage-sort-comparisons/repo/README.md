# triage

Orders batches of incoming support tickets by urgency before they are routed to agents.

Urgency is pairwise only: `Ticket.__lt__` asks the scoring service whether one ticket is more
urgent than another, and every question is a network round trip of about 40 ms. The queue
hands us batches of at most `MAX_BATCH = 8` tickets.

```python
from triage import triage_batch

ordered = triage_batch(batch)   # most urgent first
```

`sort_tickets` works on anything that supports `<`; the tests use a counting stand-in for
`Ticket`.

Run the tests with `python -m unittest discover -s tests -t .`.
