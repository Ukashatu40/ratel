// VAT 7.5% (finance confirms the rate). Whole kobo only: price x 75 / 1000, rounded.
export const VAT_PER_MILLE = 75;
export const vatKobo = (priceKobo: number) => Math.round((priceKobo * VAT_PER_MILLE) / 1000);
export const totalKobo = (priceKobo: number) => priceKobo + vatKobo(priceKobo);