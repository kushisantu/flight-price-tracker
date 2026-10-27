# Model card: lgbm-2024q3-2024q4

This model estimates the paid fare distribution for a directional DB1B market. It is not a forecast of what a ticket will cost on a booking date. DB1B has no purchase date.

## Data

Source: US DOT DB1B Market. Training rows are 2024 Q3 and 2024 Q4 only. 2025 Q1 supplies the conformal adjustment and is also the second rolling-origin score. 2025 Q2 is the holdout and is not used for training, tuning, or calibration.

Market rows are one direction of travel. The extract has no round-trip flag, so none is invented. Nonstop is coupons equal to 1. Carrier share is that airline's fraction of the route's passengers in the training quarters only.

The sample flight board is unchanged. A route with no training tickets stays uncovered. A route with fewer than 50 training passengers is labeled low confidence.

## Fit

Seven LightGBM quantile models: 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95. Predictions are sorted so a lower quantile cannot sit above a higher one. Seed 1. The displayed 10th to 90th band is then shifted by a conformal offset of 6.36, chosen so about 80 percent of 2025 Q1 tickets fall inside.

Selected parameters: `leaves63`, learning rate 0.05, 63 leaves, 110 rounds.

| Config | Fold | Median MAE | Rounds |
| --- | --- | ---: | ---: |
| leaves31 | 2024Q3-to-2024Q4 | 96.30 | 120 |
| leaves31 | 2024Q3Q4-to-2025Q1 | 96.68 | 120 |
| leaves63 | 2024Q3-to-2024Q4 | 96.20 | 120 |
| leaves63 | 2024Q3Q4-to-2025Q1 | 96.66 | 101 |

Mean absolute TreeSHAP on 2000 training rows (seed 1), from LightGBM `pred_contrib`:

| Feature | Mean absolute SHAP |
| --- | ---: |
| airline | 35.20 |
| distance | 33.97 |
| origin | 10.69 |
| dest | 10.52 |
| coupons | 8.93 |
| carrier_share | 7.27 |
| quarter | 6.37 |
| stops | 0.00 |
| nonstop | 0.00 |

Stops and nonstop receive no splits. In this extract, stops are coupons minus one, and nonstop means one coupon, so coupons already carry that information.

MLflow writes a local file store at `backend/mlruns`. The training script sets `MLFLOW_ALLOW_FILE_STORE` so that folder is accepted.

## Holdout

2025 Q2 tickets that both this model and the empirical table can score: 7,884,075.

| Estimate | MAE | 10–90 coverage |
| --- | ---: | ---: |
| Phase 2 median | $89.93 | 81.9% |
| Empirical median (empirical-2024q3-2025q1) | $97.42 | 81.1% |
| Route average | $102.13 |  |
| Linear model | $118.76 |  |

Raw model 10–90 coverage, before the conformal shift: 78.7%.
Conformal 10–90 coverage: 81.9%.

### By training volume

| Tier | Rows | Median MAE | Conformal coverage |
| --- | ---: | ---: | ---: |
| 5000_plus | 3,102,764 | $87.61 | 81.7% |
| 500_4999 | 3,210,686 | $86.54 | 82.0% |
| 50_499 | 1,288,415 | $107.50 | 82.6% |
| no_training_route | 4,506 | $64.14 | 79.4% |
| under_50 | 277,704 | $125.38 | 83.4% |

### By airline

The fifteen airlines with the most holdout passengers in the comparison set:

| Airline | Passengers | Median MAE | Conformal coverage |
| --- | ---: | ---: | ---: |
| WN | 2,863,078 | $69.33 | 82.0% |
| AA | 2,842,124 | $105.67 | 82.7% |
| DL | 2,723,940 | $116.95 | 80.0% |
| UA | 2,216,073 | $112.86 | 80.8% |
| AS | 803,919 | $96.22 | 82.7% |
| NK | 685,983 | $38.88 | 86.1% |
| B6 | 661,019 | $87.70 | 78.4% |
| F9 | 660,718 | $39.80 | 87.4% |
| G4 | 469,749 | $29.94 | 83.0% |
| HA | 189,435 | $84.93 | 80.7% |
| MX | 149,636 | $36.86 | 82.1% |
| SY | 96,975 | $42.26 | 83.8% |
| XP | 65,148 | $31.45 | 77.1% |
| 3M | 4,048 | $55.60 | 74.7% |
| LF | 96 | $47.45 | 81.3% |

## Limits

The quarterly file is a 10 percent sample. The model does not know how far ahead a ticket was bought, the weekday, or whether the market was half of a round trip. Uncovered routes are stated as uncovered. The older whitelist LightGBM files are kept and are not served.
