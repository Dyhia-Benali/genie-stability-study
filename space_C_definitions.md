# Space C = space B + business definitions

Space C is a clone of space B. Only the definitions below were added, after diagnosing
the failures of spaces A and B. No example query was written for a tested question, to
avoid "teaching to the test". Held-out phrasings (F5-H*, F8-H*) check that the fix generalises.

## 1. General instructions (appended at the end)

```
FRENCH BUSINESS SHORTHAND: "CA" means chiffre d'affaires = revenue (use the total_revenue measure).
"M" = this month, "M-1" = last month (the second-most-recent year_month), "M-2" = two months before this month.

QUARTERS: "this quarter" = the calendar quarter that contains the most recent year_month.
"Last quarter" / "previous quarter" = the full calendar quarter just before it
(if the latest month is 2026-10, last quarter = 2026-07 to 2026-09). Never use a rolling 3-month window.

PRODUCT: a product is a SKU (dim_product.product_id). Several SKUs share the same product_name,
so always group by product_id and show product_name next to it.
```

## 2. Measure `total_revenue`: synonyms added

`CA, chiffre d'affaires`

## 3. New measure `discounted_revenue_pct`

- Code: `SUM(CASE WHEN fact_sales.discount_amount > 0 THEN fact_sales.net_sales ELSE 0 END) / NULLIF(SUM(fact_sales.net_sales), 0) * 100`
- Synonyms: `discounted revenue share, discount penetration`
- Instructions: `Share of net revenue coming from order lines that had a discount applied, in percent. Use for questions about how much of revenue or sales was discounted or on promotion.`
