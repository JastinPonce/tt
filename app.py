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

# ABI Mínimo estándar ERC-20 para leer datos de cualquier token en la blockchain
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

# --- CONFIGURACIÓN DE BILLETERAS DE COBRO ---
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

def generar_menu_principal(user_name, wallet_address):
    texto = (
        f" 🤖 *Base White-Label Trading Bot Active*\n\n"
        f"¡Hola {user_name}! Tu cuenta está lista.\n\n"
        f"• *Network:* Base Mainnet\n"
        f"• *Your Secure Wallet:* \n`{wallet_address}`\n\n"
        f"💰 *Balance:* 0.00 ETH\n\n"
        f"📥 *¿Cómo comprar un Token?*\n"
        f"Simplemente pega el contrato del token de la red Base aquí abajo en el chat."
    )
    keyboard = [
        [
            InlineKeyboardButton("📊 Simular Split (0.1 ETH)", callback_data="sim_buy_01"),
            InlineKeyboardButton("📊 Simular Split (0.5 ETH)", callback_data="sim_buy_05")
        ]
    ]
    return texto, InlineKeyboardMarkup(keyboard)

# --- MANEJO DE ENTRADA DE TEXTO (DETECTAR CONTRATOS EN REAL) ---
async def detectar_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta si el usuario envió una dirección de contrato válida y extrae sus datos on-chain"""
    texto_usuario = update.message.text.strip()
    
    # Verificar si cumple con el formato de dirección de Ethereum/Base (0x + 40 caracteres hexadecimales)
    if w3.is_address(texto_usuario):
        token_address = w3.to_checksum_address(texto_usuario)
        
        try:
            # Conectarse al contrato inteligente en la Blockchain de Base
            contrato = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            
            # Leer datos reales on-chain de forma asíncrona simulada mediante hilos de Web3
            nombre = contrato.functions.name().call()
            simbolo = contrato.functions.symbol().call()
            
            texto_token = (
                f"🔍 *TOKEN DETECTADO EN LA RED BASE* 🔍\n\n"
                f"• *Nombre:* {nombre}\n"
                f"• *Símbolo:* {simbolo}\n"
                f"• *Contrato:* `{token_address}`\n\n"
                f"Elige una opción para simular la compra de este token aplicando la división 50/50:"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(f"🟢 Comprar 0.05 ETH", callback_data=f"buy_token_0.05_{simbolo}"),
                    InlineKeyboardButton(f"🟢 Comprar 0.1 ETH", callback_data=f"buy_token_0.1_{simbolo}")
                ],
                [InlineKeyboardButton("⬅️ Cancelar", callback_data="back_main")]
            ]
            
            await update.message.reply_text(texto_token, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text("❌ La dirección es válida, pero no parece ser un token ERC-20 activo en la red Base.")
    else:
        await update.message.reply_text("👋 Envía una dirección de contrato de Base válida (debe empezar con `0x`).")

# --- MANEJO DE CALLBACKS ---
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    if query.data == "back_main":
        wallet_address = obtener_o_crear_wallet(user.id)
        texto, reply_markup = generar_menu_principal(user.first_name, wallet_address)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    # Procesar simulación estándar o simulación con token detectado
    data = query.data
    monto = 0.1
    token_name = "TOKEN"
    
    if data.startswith("buy_token_"):
        partes = data.split("_")
        monto = float(partes[2])
        token_name = partes[3]
    elif data == "sim_buy_05":
        monto = 0.5
        
    split = calcular_split_comision(monto)
    
    reparto_texto = (
        f"⚡ *LÓGICA ON-CHAIN PARA COMPRA DE {token_name}* ⚡\n\n"
        f"💵 *Monto invertido:* {monto} ETH\n"
        f"📊 *Comisión Retenida (1%):* {split['total_fee_eth']} ETH\n\n"
        f"⚙️ *Split Temido por la Competencia (Inmutable):*\n"
        f"• *Tu Billetera (0.5%):* `{split['share_each_eth']}` ETH\n"
        f"  └ `➔ {DEV_WALLET}`\n"
        f"• *Billetera Socio (0.5%):* `{split['share_each_eth']}` ETH\n"
        f"  └ `➔ {PARTNER_WALLET}`\n\n"
        f"🔥 *Monto que entra al pool de intercambio:* {split['remaining_eth']} ETH\n\n"
        f"El bot está listo para enrutar este remanente directamente hacia Aerodrome."
    )
    
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
    
    threading.Thread(target=lambda: HTTPServer(("0.0.0.0", port if (port:=PORT) else 8080), HealthCheckServer).serve_forever(), daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    # Capturar cualquier mensaje de texto para analizar si es un contrato
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detectar_token))
    application.run_polling()
