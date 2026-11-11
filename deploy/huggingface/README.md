---
title: CallVerse
emoji: 📞
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: cc-by-nc-sa-4.0
short_description: Multi-agent digital twin of an e-commerce contact centre
---

# CallVerse

A multi-agent digital twin of an e-commerce contact centre. AI customers and real visitors chat with an AI
advisor, a router sends each chat to the right desk, and a quality agent scores every conversation. Managers
watch it all live, plan staff and monitor the AI components.

| Open | What you find there |
|---|---|
| {{SPACE_URL}}/ | **Front office**: the customer portal, the advisor desk and the phone line |
| {{SPACE_URL}}/back-office/ | **Back office**: the live contact centre, forecasts, workforce plans, AI monitoring |
| {{SPACE_URL}}/docs | The REST API (Swagger) |

## Good to know

- **AI models.** The agents use free hosted models (OpenRouter). Their daily quota is small and shared by every
  visitor. When it is used up, the agents switch to their offline templates and rules until the next day
  (00:00 UTC): the app keeps working, with simpler answers.
- **Your data.** Chats and customers you add stay on this Space only until it restarts; then everything goes
  back to the starting data. Please do not type real personal data.
- **Voice.** Talking and listening use your browser's speech features (best in Chrome or Edge).
- **Sleeping.** A free Space sleeps after 48 hours without visitors. The first visit wakes it up (about a minute).

## Data and licenses

- Olist Brazilian e-commerce dataset (CC BY-NC-SA 4.0): orders, customers, products and sellers.
- Bitext retail e-commerce customer-service dataset (CDLA-Sharing 1.0): customer messages and their intents.
- Synthetic contacts, tickets and chats generated from both, marked as synthetic.

For non-commercial and educational use, like the Olist data it is built on (CC BY-NC-SA 4.0).
