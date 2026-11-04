GATHER WORLD — PHASE 7: GATHER AI

Adds a logged-in AI assistant using Google's Gemini generateContent REST API. The server reads GEMINI_API_KEY from the private environment and never sends it to the browser.

Configuration in your private .env:
GEMINI_API_KEY=your_private_key
GEMINI_MODEL=gemini-3.8-flash

Open /ai, create a conversation, and send a prompt. Conversations are stored in gw_ai_conversations and gw_ai_messages and are visible only to their owner. Users can delete each conversation. Request throttling is enabled per account.

Important: messages are sent to Google Gemini for generation and stored in your Gather World Neon database. Do not type passwords, API keys, payment information or other secrets into AI chat. API availability, pricing, quota and model access depend on your Google AI project.

API implementation follows the official Gemini API generateContent REST reference.
