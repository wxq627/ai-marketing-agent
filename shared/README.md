# Published Strategy Catalog

`published_strategy_catalog.json` is the static strategy snapshot consumed by
the customer-facing application. It is generated from published B-side
strategy packages, not edited manually.

When a strategy is published or archived through the B-side API, the file is
refreshed automatically. Commit and push this directory to make the latest
snapshot available through GitHub Raw.

The catalog contains only demo identifiers and published strategy data. Do not
use this publication pattern for production customer data.
