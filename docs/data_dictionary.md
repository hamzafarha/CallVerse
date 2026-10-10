# CallVerse Data Dictionary

## Overview

This document outlines the data schemas and entities planned for the CallVerse contact center simulation and forecasting pipelines.

## Core Entities

### 1. Contacts (`data/processed/contacts.parquet`)
- `contact_id` (str): Unique contact identifier.
- `customer_id` (str): Unique customer identifier.
- `channel` (str): Contact channel (`voice`, `chat`, `email`).
- `timestamp_arrival` (datetime): Timestamp when customer entered the queue.
- `timestamp_service_start` (datetime): Timestamp when service commenced.
- `timestamp_completed` (datetime): Timestamp when interaction concluded.
- `wait_time_sec` (float): Duration in seconds spent waiting in queue.
- `handle_time_sec` (float): Duration in seconds spent in active service.
- `status` (str): Outcome status (`resolved`, `abandoned`, `transferred`).
- `topic` (str): Interaction topic / inquiry category.
- `sentiment_initial` (float): Sentiment polarity score at arrival [-1.0, 1.0].
- `sentiment_final` (float): Sentiment polarity score at completion [-1.0, 1.0].
- `advisor_id` (str, nullable): Handling advisor identifier.

### 2. Advisors / Workforce (`data/processed/advisors.parquet`)
- `advisor_id` (str): Unique agent identifier.
- `skill_level` (int): Tier skill rating [1-5].
- `specialties` (list[str]): List of specialized topics handled.
- `shift_start` (datetime): Shift start timestamp.
- `shift_end` (datetime): Shift end timestamp.
- `utilization_rate` (float): Proportion of shift time actively serving contacts.

### 3. Knowledge Base Articles (`data/knowledge_base/`)
- `article_id` (str): Unique knowledge article identifier.
- `title` (str): Article title.
- `category` (str): Knowledge base category / topic.
- `content` (str): Full resolution instructions and policy text.

### 4. Forecast Intervals (`artifacts/forecasts/`)
- `interval_start` (datetime): Aggregate time-window start (e.g. 15-minute or 1-hour).
- `channel` (str): Contact channel.
- `predicted_volume` (int): Forecasted arrival count.
- `actual_volume` (int, nullable): Observed arrival count for evaluation.
