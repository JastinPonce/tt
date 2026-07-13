import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from web3 import Web3

# --- CONEXIÓN WEB3 (RED BASE) ---
RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- CONFIGURACIÓN DE BILLETERAS Y COMISIONES ---
FEE_PERCENTAGE = 0.01  # 1% Total
DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"  # Tu billetera (Fija)
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000") # Se cambia en Render por socio

# --- COMANDOS DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera una interfaz de trading para el usuario"""
    user_id = update.effective_user.id
    
    # Simulación de wallet asignada al usuario (En producción se guarda de forma segura)
    account = w3.eth.account.create()
    user_address = account.address
    
    texto = (
        f" Welcome to Base Trading Bot\n\n"
        f"Network: Base Mainnet\n"
        f"Your Trading Wallet:\n`{user_address}`\n\n"
        f" Balance: 0.00 ETH\n\n"
        f"Elige una opción para operar de forma ultra-rápida:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(" Buy ETH/TOKEN", callback_data="buy_menu"),
            InlineKeyboardButton(" Sell TOKEN/ETH", callback_data="sell_menu")
        ],
        [InlineKeyboardButton(" Wallet Info / Refresh", callback_data="wallet_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de los botones"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "buy_menu":
        # Aquí se presentaría la interfaz de split automatizado on-chain
        reparto_texto = (
            f" Lógica de Peajes Activa (Split 50/50):\n"
            f"• Comisión del Trade: 1.0%\n"
            f"• Developer Fee (0.5%): `{DEV_WALLET}`\n"
            f"• Partner Fee (0.5%): `{PARTNER_WALLET}`\n\n"
            f"Envía el contrato del token de la red Base que deseas comprar."
        )
        await query.edit_message_text(text=reparto_texto, parse_mode="Markdown")

# --- SERVIDOR WEB PARA EL HEALTH CHECK DE RENDER ---
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Trading Bot Engine: Active")

def run_health_server(port):
    server = HTTPServer(("0.0.0.0", port), HealthCheckServer)
    server.serve_forever()

# --- ARRANQUE ---
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    if not TOKEN:
        print("ERROR: No se encontró la variable TELEGRAM_TOKEN")
        exit(1)

    # Iniciar servidor web de respaldo
    server_thread = threading.Thread(target=run_health_server, args=(PORT,), daemon=True)
    server_thread.start()
    print(f"Servidor HTTP corriendo en el puerto {PORT}")

    # Configurar Bot de Telegram
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    
    print("Bot de Trading iniciado y escuchando en Base Network...")
    application.run_polling()
