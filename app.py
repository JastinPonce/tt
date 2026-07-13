import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from web3 import Web3
from cryptography.fernet import Fernet

# --- CONEXIÓN WEB3 (RED BASE MAINNET) ---
RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- CONFIGURACIÓN DE SEGURIDAD (PASO 1) ---
# Intentamos leer una clave maestra de Render; si no existe, generamos una automática para pruebas
MASTER_KEY = os.environ.get("ENCRYPTION_KEY")
if not MASTER_KEY:
    # Genera una clave segura temporal para que el bot no se caiga si no está configurada en Render
    MASTER_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(MASTER_KEY.encode())

# Base de datos simulada en memoria para guardar las wallets de los usuarios de forma segura
USER_DATABASE = {}

# --- CONFIGURACIÓN DE BILLETERAS DE COBRO ---
DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000")

# --- MOTOR DE SEGURIDAD: OBTENER O CREAR WALLET ENCRIPTADA ---
def obtener_o_crear_wallet(user_id):
    """Si el usuario no tiene wallet, crea una y encripta su clave privada"""
    if user_id in USER_DATABASE:
        return USER_DATABASE[user_id]["address"]
    
    # 1. Crear billetera nueva en la Blockchain de Base
    new_account = w3.eth.account.create()
    
    # 2. Encriptar la clave privada usando AES-256 (Cifrado simétrico)
    clave_privada_bytes = new_account.key.hex().encode()
    clave_encriptada = cipher_suite.encrypt(clave_privada_bytes).decode()
    
    # 3. Guardar la wallet (La clave privada real NO se guarda en texto plano)
    USER_DATABASE[user_id] = {
        "address": new_account.address,
        "encrypted_private_key": clave_encriptada
    }
    return new_account.address

# --- MOTOR MATEMÁTICO DEL SPLIT ---
def calcular_split_comision(amount_in_eth):
    amount_in_wei = w3.to_wei(amount_in_eth, 'ether')
    total_fee_wei = int(amount_in_wei * 0.01)
    share_each_wei = total_fee_wei // 2
    remaining_amount_wei = amount_in_wei - total_fee_wei
    
    return {
        "total_fee_eth": w3.from_wei(total_fee_wei, 'ether'),
        "share_each_eth": w3.from_wei(share_each_wei, 'ether'),
        "remaining_eth": w3.from_wei(remaining_amount_wei, 'ether')
    }

# --- TEXTO DEL MENÚ PRINCIPAL ---
def generar_menu_principal(user_name, wallet_address):
    texto = (
        f" 🤖 *Base White-Label Trading Bot Active*\n\n"
        f"¡Hola {user_name}! Tu cuenta está lista.\n\n"
        f"• *Network:* Base Mainnet\n"
        f"• *Your Secure Wallet:* \n`{wallet_address}`\n\n"
        f"🔒 _Clave privada encriptada en la base de datos con AES-256_\n\n"
        f"💰 *Balance:* 0.00 ETH\n\n"
        f"Elige una opción para simular la lógica de peajes:"
    )
    keyboard = [
        [
            InlineKeyboardButton("📈 Simular Compra (0.1 ETH)", callback_data="sim_buy_01"),
            InlineKeyboardButton("📈 Simular Compra (0.5 ETH)", callback_data="sim_buy_05")
        ]
    ]
    return texto, InlineKeyboardMarkup(keyboard)

# --- COMANDOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    wallet_address = obtener_o_crear_wallet(user.id)
    
    texto, reply_markup = generar_menu_principal(user.first_name, wallet_address)
    await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    # CORRECCIÓN: Si el usuario presiona "Volver", regresamos al menú principal sin calcular nada
    if query.data == "back_main":
        wallet_address = obtener_o_crear_wallet(user.id)
        texto, reply_markup = generar_menu_principal(user.first_name, wallet_address)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    # Manejo de simulaciones de compra
    monto = 0.1 if query.data == "sim_buy_01" else 0.5
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
        f"_*Nota:* El botón de volver ahora funciona de forma nativa recargando tu wallet segura._"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data="back_main")]]
    await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Operational")

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
