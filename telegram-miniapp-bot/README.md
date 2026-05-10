# Telegram Mini App Bot

This project is a Telegram bot integrated with a Telegram Mini App. The bot allows users to interact with a product list and place orders through a web interface.

## Project Structure

```
telegram-miniapp-bot
├── bot
│   ├── main.py                # Main entry point of the Telegram bot
│   ├── handlers.py            # Handlers for bot commands and messages
│   ├── db.py                  # Database interactions for orders and products
│   ├── keyboards.py            # Custom keyboards for the bot
│   ├── config.py              # Configuration settings (e.g., bot token)
│   └── requirements.txt       # Dependencies for the bot
├── mini_app
│   ├── package.json           # Configuration for the mini app
│   ├── public
│   │   └── index.html         # HTML structure for the product list
│   └── src
│       ├── index.js           # Entry point for the mini app's JavaScript
│       └── web_app.js         # Logic for product display and order submission
├── .env.example                # Example environment variables
├── .gitignore                  # Files to ignore by Git
├── docker-compose.yml          # Multi-container Docker application setup
└── README.md                   # Project documentation
```

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd telegram-miniapp-bot
   ```

2. **Set up the environment:**
   - Copy the `.env.example` to `.env` and fill in the required environment variables, including your Telegram bot token and any other necessary configurations.

3. **Install dependencies:**
   - For the bot, navigate to the `bot` directory and install the required packages:
     ```bash
     pip install -r requirements.txt
     ```
   - For the mini app, navigate to the `mini_app` directory and install the necessary packages:
     ```bash
     npm install
     ```

4. **Run the bot:**
   - Start the bot by running the `main.py` file:
     ```bash
     python bot/main.py
     ```

5. **Run the mini app:**
   - Start the mini app by running:
     ```bash
     npm start
     ```

## Usage

- Start a chat with your Telegram bot and use the `/start` command to receive a button that opens the web app.
- In the web app, browse the product list and click the "Buyurtma berish" button to place an order.

## Integration Notes

- Ensure that the web app is hosted and accessible via a URL that the Telegram bot can use to open it.
- The bot and mini app communicate through the Telegram Bot API, so ensure that the necessary permissions are set up in your bot configuration.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.