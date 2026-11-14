# Ticket lookup

An igni extension: two tools (`lookup_ticket`, `ticket_from_service`),
a `PostToolUse` hook that writes an audit line, and a page that calls
`lookup_ticket`. Its service is `../service`.

Check it with `igni ext doctor .` and try it on this machine with
`IGNI_DEV_EXTENSIONS=1 igni ext install .`; [the example's README](../README.md#run-it)
says what comes next.
