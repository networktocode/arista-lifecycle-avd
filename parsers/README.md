# parsers

TextFSM templates served to Nautobot Operational Compliance through its
`nautobot_operational_compliance.command_parsers` Git datasource. Path convention:
`parsers/<network_driver>/<command with spaces as underscores>.<parser type>`.

These cover EOS show commands that have neither a `| json` form on cEOS nor an ntc-templates entry.
