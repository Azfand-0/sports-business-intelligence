# Forecasting Model Report

Trained on 34 games, evaluated on 12 held-out games (small-sample caveat applies).

## Attendance Forecast
| Model | MAE | RMSE | R2 |
|---|---|---|---|
| Linear Regression | 240.94 | 294.77 | 0.795 |
| Random Forest | 247.22 | 348.42 | 0.714 |

### Top Feature Importance (Attendance)
| Feature            |   Importance | Model             |
|:-------------------|-------------:|:------------------|
| IsRivalGame        |  838.594     | Linear Regression |
| Weather_Snow       |  520.392     | Linear Regression |
| Competition_Cup    |  289.52      | Linear Regression |
| Competition_League |  289.52      | Linear Regression |
| Weather_Clear      |  272.06      | Linear Regression |
| IsRivalGame        |    0.273927  | Random Forest     |
| OpponentRanking    |    0.123406  | Random Forest     |
| Competition_League |    0.0931155 | Random Forest     |
| Weather_Snow       |    0.0915228 | Random Forest     |
| Competition_Cup    |    0.0907659 | Random Forest     |

## Revenue Forecast
| Model | MAE | RMSE | R2 |
|---|---|---|---|
| Linear Regression | 14836.37 | 16974.03 | 0.762 |
| Random Forest | 11838.25 | 15493.57 | 0.802 |

### Top Feature Importance (Revenue)
| Feature            |    Importance | Model             |
|:-------------------|--------------:|:------------------|
| IsRivalGame        | 47268.4       | Linear Regression |
| Competition_League | 18023         | Linear Regression |
| Competition_Cup    | 18023         | Linear Regression |
| Weather_Snow       | 14615.3       | Linear Regression |
| IsHoliday          | 13909.1       | Linear Regression |
| IsRivalGame        |     0.446571  | Random Forest     |
| Competition_Cup    |     0.110259  | Random Forest     |
| Competition_League |     0.0984447 | Random Forest     |
| OpponentRanking    |     0.0790644 | Random Forest     |
| Temperature        |     0.0432481 | Random Forest     |