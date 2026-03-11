# USF Job Sniper

An automation tool designed to monitor the **USF Oracle** job portal in real-time. This sniper identifies high-value student opportunities and alerts you instantly via Discord.

---

## Why this exists

On-campus jobs at USF are highly competitive and manual checking is inefficient. This tool automates the "hunt" so you can apply within minutes of a posting going live.

---

## Key Features

- **Real-Time Monitoring:** Scrapes the USF Oracle JSON endpoint every 60 minutes.
- **IT Match Scoring:** Custom algorithm that ranks jobs (0-100) based on technical keyword density (Python, SQL, Security, etc.).
- **Tampa Only Filter:** Automatically discards listings for St. Pete or Sarasota campuses.
- **Cloud Integration:** Uses **Supabase (PostgreSQL)** to maintain a persistent state and ensure zero duplicate notifications. Hosted over **Github Actions** to keep running all the time.
- **Smart Skips:** Automatically filters out Federal Work Study (FWS) and roles requiring advanced degrees (Bachelors/Masters).

---

## Tech Stack

- **Language:** Python
- **Database:** Supabase (Cloud PostgreSQL)
- **Communication:** Discord Webhooks
- **Automation:** Github Actions
- **Data Handling:** `requests` for high-speed JSON parsing

---
