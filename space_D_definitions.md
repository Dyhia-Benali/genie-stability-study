# Space D = space C, with the month rule rewritten

## Why
In space C, Genie understood "M-1" / "prior month" correctly but wrote:

    WHERE year_month = (SELECT year_month FROM dim_date ORDER BY year_month DESC LIMIT 1 OFFSET 1)

dim_date has one row per DAY, so OFFSET 1 lands on another day of the SAME month:
the query silently returned the current month's revenue (1,641,721 instead of 1,756,281).
The pattern was not new: space B used it once for "last month" (held-out phrasing F5-HEN2) and twice for
"last quarter". In C it appeared on 3 "last month" phrasings; the wording added in C
("the second-most-recent year_month") probably made it more frequent, but did not create it.
The fix is therefore to state the table grain and the exact pattern, not just to reword the definition.

## The only change
In General Instructions, replace the FRENCH BUSINESS SHORTHAND paragraph added for space C with:

```
FRENCH BUSINESS SHORTHAND: "CA" means chiffre d'affaires = revenue (use the total_revenue measure).
"M" = this month, "M-1" = last month, "M-2" = two months before this month.

MONTH ARITHMETIC: dim_date has one row per DAY. Never use ORDER BY ... LIMIT / OFFSET on dim_date to pick a month.
Last month (M-1) = (SELECT MAX(year_month) FROM bramblepeak_retail.sales.dim_date
                    WHERE year_month < (SELECT MAX(year_month) FROM bramblepeak_retail.sales.dim_date)).
For M-2 and earlier, first take SELECT DISTINCT year_month FROM bramblepeak_retail.sales.dim_date, then order it.
```

Everything else (QUARTERS, PRODUCT, CA synonyms, discounted_revenue_pct measure) stays exactly as in space C.
