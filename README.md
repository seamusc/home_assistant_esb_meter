# ESB Meter — Home Assistant Integration

A Home Assistant custom integration that scrapes half-hourly electricity usage data from [ESB Networks](https://myaccount.esbnetworks.ie) and pushes it directly into HA's long-term statistics — no InfluxDB or external database required.

## Features

- Full UI setup via **Settings → Integrations → Add Integration → ESB Meter**
- Injects historical 30-minute interval data into the HA Energy Dashboard
- Polls every 6 hours (data updates approximately once daily)
- No external database dependencies

## Requirements

- A registered account at [myaccount.esbnetworks.ie](https://myaccount.esbnetworks.ie) with your MPRN linked
- Home Assistant 2023.12 or newer

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations → Custom Repositories**
2. Add this repository URL with category **Integration**
3. Search for "ESB Meter" and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/esb_meter/` into your HA config's `custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Integrations → Add Integration**
2. Search for **ESB Meter**
3. Enter your ESB Networks email, password, and MPRN (found on your electricity bill)

## Energy Dashboard

After setup, go to **Settings → Dashboards → Energy** and add the ESB Meter statistic as a grid consumption source.

## Notes

- ESB Networks returns all available historical data (~20k+ records). On first setup this may take a moment to import.
- The CSV data is in kW per 30-minute period; this integration converts to kWh automatically.
- Timestamps in the source data are Irish Standard Time (Europe/Dublin) and are stored as UTC in HA.

## Credits

Scraping logic based on [badger707/esb-smart-meter-reading-automation](https://github.com/badger707/esb-smart-meter-reading-automation).
