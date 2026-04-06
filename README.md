# Exchange Holidays

A Streamlit web app to explore market holiday calendars by exchange, compare closures across multiple markets, and export results to CSV or Excel.

## Features

- Select one or more exchanges
- Choose a custom date range
- View results in two formats:
  - **Long view**: one row per closure
  - **Wide view**: one column per exchange
- Includes:
  - regular holidays
  - ad-hoc / special closures
- Export results to:
  - CSV
  - Excel

## Supported Exchanges

The app uses `exchange_calendars` and only shows exchange codes available in the installed package.

Examples include:

- NYSE
- Borsa Italiana
- Xetra
- London Stock Exchange
- Euronext markets
- Tokyo Stock Exchange
- Hong Kong Stock Exchange
- and many others

## Tech Stack

- **Python**
- **Streamlit**
- **pandas**
- **exchange_calendars**
- **openpyxl**

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/exchange-holidays.git
cd exchange-holidays
