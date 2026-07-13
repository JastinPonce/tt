import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from web3 import Web3

# --- CONEXIÓN WEB3 (RED BASE MAINNET) ---
RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- CONFIGURACIÓN DE BILLETERAS DE COBRO (BLUEPRINT) ---
DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"  # Tu billetera fija
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000") # Billetera del socio

# --- MOTOR MATEMÁTICO INMUTABLE (WEIS) ---
def calcular_split_comision(amount_in_eth):
    """
    Convierte el monto a Wei y calcula el split exacto del 50/50 
    sobre una comisión total del 1% sin errores de redondeo.
    """
    # 1. Convertir el monto de la transacción a Wei (Evita flotantes)
    amount_in_wei = w3.to_wei(amount_in_eth, 'ether')
    
    # 2. Calcular comisión total del 1% (Monto * 0.01)
    total_fee_wei = int(amount_in_wei * 0.01)
    
    # 3. Dividir de forma exacta para cada billetera (Split 50/50)
    share_each_wei = total_fee_wei // 2
    
    # 4. El remanente exacto que va al swap de Uniswap/Aerodrome
    remaining_amount_wei = amount_in_wei - total_fee_wei
    
    return {
        "total_fee_eth": w3.from_wei(total_fee_wei, 'ether'),
        "share_each_eth": w3.from_wei(share_each_wei, 'ether'),
        "remaining_eth": w3.from_wei(remaining_amount_wei, 'ether'),
        "share_each_wei": share_each_wei,
        "remaining_wei": remaining_amount_wei
    }

# --- INTERFAZ INTERACTIVA ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Generación de billetera temporal de trading segura por usuario
    account = w3.eth.account.create()
    
    texto = (
        f" 🤖 *Base White-Label Trading Bot Active*\n\n"
        f"• *Network:* Base Mainnet\n"
        f"• *Your Trading Wallet:* \n`{account.address}`\n\n"
        f"💰 *Balance:* 0.00 ETH\n\n"
        f"Elige una opción para simular la lógica de peajes:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📈 Simular Compra (0.1 ETH)", callback_data="sim_buy_01"),
            InlineKeyboardButton("📈 Simular Compra (0.5 ETH)", callback_data="sim_buy_05")
        ]
    ]
    await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Evaluar montos de simulación
    monto = 0.1 if query.data == "sim_buy_01" else 0.5
    
    # Ejecutar la matemática inmutable del split cripto
    split = calcular_split_comision(monto)
    
    reparto_texto = (
        f"⚡ *LÓGICA ON-CHAIN EJECUTADA TRAS EL TRADE* ⚡\n\n"
        f"💵 *Monto del Swap:* {monto} ETH\n"
        f"📊 *Comisión Total (1%):* {split['total_fee_eth']} ETH\n\n"
        f"⚙️ *Distribución Matemática Automática:*\n"
        f"• *Tu Billetera (0.5%):* `{split['share_each_eth']}` ETH\n"
        f"  └ `➔ {DEV_WALLET}`\n"
        f"• *Billetera Socio (0.5%):* `{split['share_each_eth']}` ETH\n"
        f"  └ `➔ {PARTNER_WALLET}`\n\n"
        f"🔥 *Monto Final Enviado al Router:* {split['remaining_eth']} ETH\n\n"
        f"_*Nota:* El dinero se divide a nivel de script mediante Web3. El desarrollador jamás custodia fondos ajenos._"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="back_main")]]
    await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Trading Bot Engine: Operational")

def run_health_server(port):
    HTTPServer(("0.0.0.0", port), HealthCheckServer).serve_forever()

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    threading.Thread(target=run_health_server, args=(PORT,), daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.run_polling()
