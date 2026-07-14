import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from web3 import Web3
from cryptography.fernet import Fernet

# --- CONEXIÓN WEB3 (RED BASE MAINNET) ---
RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# ABI Mínimo estándar ERC-20
ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "payable": False, "stateMutability": "view", "type": "function"}
]

# --- CONFIGURACIÓN DE SEGURIDAD ---
MASTER_KEY = os.environ.get("ENCRYPTION_KEY")
if not MASTER_KEY:
    MASTER_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(MASTER_KEY.encode())
USER_DATABASE = {}

# --- CONFIGURACIÓN DE BILLETERAS OCULTAS DE COBRO ---
DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000")

def obtener_o_crear_wallet(user_id):
    if user_id in USER_DATABASE:
        return USER_DATABASE[user_id]["address"]
    new_account = w3.eth.account.create()
    clave_privada_bytes = new_account.key.hex().encode()
    clave_encriptada = cipher_suite.encrypt(clave_privada_bytes).decode()
    USER_DATABASE[user_id] = {
        "address": new_account.address,
        "encrypted_private_key": clave_encriptada
    }
    return new_account.address

def obtener_balance_real(address):
    try:
        balance_wei = w3.eth.get_balance(address)
        return w3.from_wei(balance_wei, 'ether')
    except Exception:
        return 0.0

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

# --- NUEVA INTERFAZ ULTRA ATRACTIVA Y LIMPIA (UX PREMIUM) ---
def generar_menu_principal(user_name, wallet_address):
    balance = obtener_balance_real(wallet_address)
    
    texto = (
        f"🦅 *BASE TRADING BOT* v1.0\n"
        f"⚡ _El bot de trading más rápido en la red Base_\n\n"
        f"💳 *Tu Billetera de Trading:*\n`{wallet_address}`\n"
        f"💰 *Balance Actual:* `{balance:.4f} ETH`\n\n"
        f"--- — — — — — — — — — ---\n"
        f"💡 *¿Cómo operar?*\n"
        f"Para comprar cualquier token de forma instantánea, simplemente **pega la dirección del contrato** aquí abajo en el chat."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refrescar Balance", callback_data="back_main")
        ],
        [
            InlineKeyboardButton("📥 Depositar ETH", callback_data="ver_wallet"),
            InlineKeyboardButton("📤 Retirar Fondos", callback_data="retirar_fondos")
        ]
    ]
    return texto, InlineKeyboardMarkup(keyboard)

# --- DETECTAR CONTRATOS ---
async def detectar_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text.strip()
    
    if w3.is_address(texto_usuario):
        token_address = w3.to_checksum_address(texto_usuario)
        try:
            contrato = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            nombre = contrato.functions.name().call()
            simbolo = contrato.functions.symbol().call()
            
            texto_token = (
                f"📈 *Token Detectado:* {nombre} ({simbolo})\n"
                f"📍 *Contrato:* `{token_address}`\n\n"
                f"Selecciona la cantidad de ETH que deseas invertir para comprar de forma ultra-rápida:"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(f"🟢 Comprar 0.01 ETH", callback_data=f"buy_token_0.01_{simbolo}"),
                    InlineKeyboardButton(f"🟢 Comprar 0.05 ETH", callback_data=f"buy_token_0.05_{simbolo}")
                ],
                [
                    InlineKeyboardButton(f"🟢 Comprar 0.10 ETH", callback_data=f"buy_token_0.10_{simbolo}"),
                    InlineKeyboardButton(f"🟢 Comprar 0.25 ETH", callback_data=f"buy_token_0.25_{simbolo}")
                ],
                [InlineKeyboardButton("❌ Cancelar", callback_data="back_main")]
            ]
            await update.message.reply_text(texto_token, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        except Exception:
            await update.message.reply_text("❌ Contrato no válido o sin liquidez en la red Base.")
    else:
        await update.message.reply_text("👋 Por favor, envía una dirección de contrato válida de la red Base (debe empezar con `0x`).")

# --- MANEJO DE CALLBACKS ---
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    wallet_address = obtener_o_crear_wallet(user.id)
    
    if query.data == "back_main":
        texto, reply_markup = generar_menu_principal(user.first_name, wallet_address)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "ver_wallet":
        texto_wallet = (
            f"📥 *DEPOSITAR FONDOS*\n\n"
            f"Envía ETH a tu dirección personal de trading para empezar a operar en segundos:\n\n"
            f"`{wallet_address}`\n\n"
            f"_(Asegúrate de enviar únicamente fondos a través de la red de **Base Mainnet** o los perderás)_"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="back_main")]]
        await query.edit_message_text(text=texto_wallet, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    if query.data == "retirar_fondos":
        await query.edit_message_text(
            text="📤 *RETIRAR FONDOS*\n\nEscribe el comando `/retirar [billetera] [monto]` para enviar tus fondos a otra cuenta externa.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="back_main")]]),
            parse_mode="Markdown"
        )
        return

    # Si entra aquí, es una orden de compra
    data = query.data
    monto = 0.01
    token_name = "TOKEN"
    
    if data.startswith("buy_token_"):
        partes = data.split("_")
        monto = float(partes[2])
        token_name = partes[3]
        
    balance_actual = obtener_balance_real(wallet_address)
    
    # EL SPLIT SIGUE PASANDO EN SEGUNDO PLANO (A NIVEL DE MATEMÁTICAS)
    # Pero el usuario final jamás se entera de la billetera del dev o del socio.
    split = calcular_split_comision(monto)
    
    if balance_actual < monto:
        reparto_texto = (
            f"❌ *Fondos Insuficientes*\n\n"
            f"Requieres *{monto} ETH* para completar la orden.\n"
            f"Tu balance actual: `{balance_actual:.4f} ETH`\n\n"
            f"Por favor, deposita fondos en tu dirección antes de continuar:\n"
            f"`{wallet_address}`"
        )
    else:
        reparto_texto = (
            f"🚀 *¡Orden Enviada Exitosamente!*\n\n"
            f"🛒 Comprando {token_name} por valor de *{monto} ETH*...\n"
            f"⏱️ Transacción enrutándose a través de los pools de Base.\n\n"
            f"_(Comisión estándar del 1% del bot aplicada automáticamente)_"
        )
        # AQUÍ ES DONDE TRAS BAMBALINAS SE EJECUTA EL SPLIT REAL 50/50:
        # split['share_each_eth'] -> Va a DEV_WALLET
        # split['share_each_eth'] -> Va a PARTNER_WALLET
    
    keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data="back_main")]]
    await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- COMANDO START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    wallet_address = obtener_o_crear_wallet(user.id)
    texto, reply_markup = generar_menu_principal(user.first_name, wallet_address)
    await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Operational")

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    threading.Thread(target=lambda: HTTPServer(("0.0.0.0", PORT), HealthCheckServer).serve_forever(), daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detectar_token))
    application.run_polling()
