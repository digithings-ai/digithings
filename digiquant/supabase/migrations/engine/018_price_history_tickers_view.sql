-- Distinct tickers in price_history for comparables picker (Performance page).
-- security_invoker: RLS on underlying price_history applies.

CREATE OR REPLACE VIEW public.price_history_tickers
WITH (security_invoker = true) AS
SELECT DISTINCT ticker
FROM public.price_history
ORDER BY ticker;

COMMENT ON VIEW public.price_history_tickers IS
  'Distinct symbols present in price_history; used to populate comparable ETF/asset dropdown.';

GRANT SELECT ON public.price_history_tickers TO anon, authenticated;
