# Space B = the lab's configuration, applied as is

Space B uses the configuration from Jakub Lasak's lab, without any change:
[`deep-dives/genie-sales-analytics/genie-setup/01_Genie_Space_Setup.md`](https://github.com/jrlasak/databricks-code-practice/blob/main/deep-dives/genie-sales-analytics/genie-setup/01_Genie_Space_Setup.md)

It is referenced rather than copied here, so the lab's author keeps the reference version.

## What was applied

| Lab section | Content | Applied |
|---|---|---|
| § 3 About | Name and description | Yes (description only) |
| § 4 Instructions → Text | General instructions: current month, last month, store vs customer region, product names, output format | Yes, verbatim |
| § 5 Joins | 4 joins from `fact_sales` to `dim_date`, `dim_product`, `dim_store`, `dim_customer`, Many to One | Yes |
| § 6 SQL Expressions | 5 measures (`total_revenue`, `total_margin`, `margin_pct`, `units_sold`, `avg_order_value`) + 1 filter (`is_discounted`), English synonyms | Yes |
| § 7a Example queries | 8 certified queries with parameters | Yes |
| § 7b SQL functions | `simulate_discount`, `top_drivers`, `explain_driver` | Yes |
| § 8 Common questions | Suggested prompts shown to users | No: they do not change how Genie answers |

## Differences from the lab's instructions

- The Genie UI has changed since the lab was written: joins, SQL expressions and example queries now live in
  **Configure → Examples**, not under Instructions. The content is the same.
- Genie's **Improve** button was never used, so no instruction was rewritten by AI.
- No French synonym was added: that is what spaces C and D test.
