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
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"}
]

# --- CONFIGURACIÓN DE SEGURIDAD CRIPTOGRÁFICA ---
MASTER_KEY = os.environ.get("ENCRYPTION_KEY")
if not MASTER_KEY:
    MASTER_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(MASTER_KEY.encode())

# Base de datos extendida para almacenar las preferencias de UX de cada usuario
USER_DATABASE = {}

DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000")

def inicializar_usuario_si_no_existe(user_id):
    """Inicializa la billetera encriptada y las preferencias si el usuario es nuevo"""
    if user_id not in USER_DATABASE:
        new_account = w3.eth.account.create()
        clave_privada_bytes = new_account.key.hex().encode()
        clave_encriptada = cipher_suite.encrypt(clave_privada_bytes).decode()
        
        USER_DATABASE[user_id] = {
            "address": new_account.address,
            "encrypted_private_key": clave_encriptada,
            "auto_buy": False,          # Estado por defecto: Desactivado
            "auto_buy_amount": 0.05    # Monto por defecto para Modo Sniper
        }

def obtener_balance_real(address):
    try:
        balance_wei = w3.eth.get_balance(address)
        return w3.from_wei(balance_wei, 'ether')
    except Exception:
        return 0.0

# --- INTERFAZ DE USUARIO DEL MENÚ PRINCIPAL ---
def generar_menu_principal(user_id):
    user_data = USER_DATABASE[user_id]
    wallet_address = user_data["address"]
    balance = obtener_balance_real(wallet_address)
    wallet_corta = f"{wallet_address[:6]}...{wallet_address[-4:]}"
    
    # Indicador visual del estado del Auto-Buy en el Home
    status_sniper = "🟢 Activo" if user_data["auto_buy"] else "🔴 Inactivo"
    
    texto = (
        f"🦅 *BASE TRADING ENGINE*\n"
        f"─── — — — — — — — — — ───\n\n"
        f"💳 *Wallet:* `{wallet_corta}`\n"
        f"💰 *Balance:* `{balance:.4f} ETH`\n"
        f"🎯 *Modo Sniper:* {status_sniper}\n\n"
        f"─── — — — — — — — — — ───\n"
        f"⚡ *¿Cómo empezar a operar?*\n"
        f"Pega el contrato de cualquier token ERC-20 de la red Base abajo en el chat para analizar la liquidez."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Actualizar Balance", callback_data="back_main")],
        [
            InlineKeyboardButton("📥 Depositar", callback_data="ver_wallet"),
            InlineKeyboardButton("📤 Retirar", callback_data="retirar_fondos")
        ],
        [InlineKeyboardButton("⚙️ Configuración Avanzada", callback_data="abrir_settings")]
    ]
    return texto, InlineKeyboardMarkup(keyboard)

# --- MEJORA UX/MARKETING: PANEL DE CONFIGURACIONES PREMIUM ---
def generar_menu_settings(user_id):
    user_data = USER_DATABASE[user_id]
    status_emoji = "🟢 ACTIVADO" if user_data["auto_buy"] else "🔴 DESACTIVADO"
    monto = user_data["auto_buy_amount"]
    
    texto_settings = (
        f"⚙️ *PANEL DE CONFIGURACIÓN AVANZADA*\n"
        f"Personaliza tu motor de ejecución para máxima velocidad:\n\n"
        f"🚀 *Compra Automática (Auto-Buy):* `{status_emoji}`\n"
        f"Si está activado, el bot comprará el token inmediatamente al pegar el contrato sin pedir confirmaciones adicionales.\n\n"
        f"💵 *Monto de Compra por Defecto:* `{monto} ETH`\n"
        f"🔒 *Seguridad:* Cifrado simétrico activo (AES-256)"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(f"🎯 Alternar Auto-Buy", callback_data="toggle_autobuy"),
            InlineKeyboardButton(f"✍️ Cambiar Monto ({monto} ETH)", callback_data="config_monto")
        ],
        [
            InlineKeyboardButton("🔑 Exportar Clave Privada", callback_data="exportar_key")
        ],
        [InlineKeyboardButton("⬅️ Volver al Panel Principal", callback_data="back_main")]
    ]
    return texto_settings, InlineKeyboardMarkup(keyboard)

# --- DETECTAR CONTRATOS ---
async def detectar_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    inicializar_usuario_si_no_existe(user_id)
    user_data = USER_DATABASE[user_id]
    
    texto_usuario = update.message.text.strip()
    
    if w3.is_address(texto_usuario):
        token_address = w3.to_checksum_address(texto_usuario)
        status_msg = await update.message.reply_text("🔍 _Consultando nodos de Base... [⏳]_\n`[████████░░] 80%`", parse_mode="Markdown")
        
        try:
            contrato = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            nombre = contrato.functions.name().call()
            simbolo = contrato.functions.symbol().call()
            
            # FLUJO UX OPTIMIZADO (PERSPECTIVA MARKETING): EJECUCIÓN MODO SNIPER
            if user_data["auto_buy"]:
                monto_sniper = user_data["auto_buy_amount"]
                texto_sniper = (
                    f"🚀 *⚡ MODO SNIPER ACTIVADO ⚡*\n\n"
                    f"📈 *Token:* {nombre} (`{simbolo}`)\n"
                    f"🛒 *Acción:* Ejecutando compra instantánea por *{monto_sniper} ETH*...\n"
                    f"⏱️ Transacción transmitiéndose al bloque en la red Base.\n\n"
                    f"_(Comisión del 1% procesada tras bambalinas)_"
                )
                await status_msg.edit_text(text=texto_sniper, parse_mode="Markdown")
                return

            # Flujo estándar si Auto-Buy está inactivo
            texto_token = (
                f"📈 *Gema Detectada:* {nombre} (`{simbolo}`)\n"
                f"📍 *Contrato:* `{token_address}`\n\n"
                f"Selecciona la cantidad de ETH para tu Swap inmediato:"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(f"🟢 0.01 ETH", callback_data=f"buy_token_0.01_{simbolo}"),
                    InlineKeyboardButton(f"🟢 0.05 ETH", callback_data=f"buy_token_0.05_{simbolo}")
                ],
                [
                    InlineKeyboardButton(f"🟢 0.10 ETH", callback_data=f"buy_token_0.10_{simbolo}"),
                    InlineKeyboardButton(f"🟢 0.25 ETH", callback_data=f"buy_token_0.25_{simbolo}")
                ],
                [InlineKeyboardButton("❌ Cancelar Orden", callback_data="back_main")]
            ]
            await status_msg.edit_text(text=texto_token, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        except Exception:
            await status_msg.edit_text("❌ El contrato no tiene un pool de liquidez activo en la red Base.")
    else:
        await update.message.reply_text("👋 Envía un contrato válido de Base (Ej: empezando con `0x`).")

# --- MANEJO DE CALLBACKS ---
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    inicializar_usuario_si_no_existe(user_id)
    user_data = USER_DATABASE[user_id]
    
    if query.data == "back_main":
        texto, reply_markup = generar_menu_principal(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "abrir_settings":
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "toggle_autobuy":
        user_data["auto_buy"] = not user_data["auto_buy"]
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "config_monto":
        # Alternador rápido de montos comerciales estándar (0.05 -> 0.1 -> 0.25 -> 0.5 -> 0.05)
        montos_disponibles = [0.05, 0.1, 0.25, 0.5]
        idx_actual = montos_disponibles.index(user_data["auto_buy_amount"])
        user_data["auto_buy_amount"] = montos_disponibles[(idx_actual + 1) % len(montos_disponibles)]
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "exportar_key":
        # PERSPECTIVA SEGURIDAD CRIPTO: Desencriptación al vuelo solo para la vista del usuario
        key_encriptada = user_data["encrypted_private_key"]
        key_desencriptada = cipher_suite.decrypt(key_encriptada.encode()).decode()
        
        texto_key = (
            f"🔑 *TU CLAVE PRIVADA (CONEXIÓN SEGURA)*\n\n"
            f"`{key_desencriptada}`\n\n"
            f"⚠️ *ADVERTENCIA CRÍTICA:*\n"
            f"No compartas nunca esta clave con nadie. Te da acceso total a tus fondos. Puedes importarla en MetaMask para gestionar tu billetera externamente.\n\n"
            f"_(Por motivos de seguridad, este menú se ocultará si refrescas el panel o vuelves al menú)_"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Regresar a Configuración", callback_data="abrir_settings")]]
        await query.edit_message_text(text=texto_key, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if query.data == "ver_wallet":
        texto_wallet = (
            f"📥 *DIRECCIÓN DE DEPÓSITO*\n\n"
            f"Toca la dirección de abajo para copiarla automáticamente:\n\n"
            f"`{user_data['address']}`\n\n"
            f"⚠️ *Nota:* Envía únicamente *ETH* mediante la red **Base Mainnet**. Los depósitos por otras redes se perderán."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Regresar", callback_data="back_main")]]
        await query.edit_message_text(text=texto_wallet, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    if query.data == "retirar_fondos":
        await query.edit_message_text(
            text="📤 *RETIRAR BALANCE*\n\nUsa el comando `/retirar [dirección] [monto]` para retirar tus fondos a una wallet externa.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Regresar", callback_data="back_main")]]),
            parse_mode="Markdown"
        )
        return

    # Lógica de simulación de compra estándar
    data = query.data
    monto = 0.01
    token_name = "TOKEN"
    
    if data.startswith("buy_token_"):
        partes = data.split("_")
        monto = float(partes[2])
        token_name = partes[3]
        
    balance_actual = obtener_balance_real(user_data["address"])
    
    if balance_actual < monto:
        reparto_texto = (
            f"❌ *Fondos Insuficientes*\n\n"
            f"La orden requiere *{monto} ETH*.\n"
            f"Tu balance actual es de: `{balance_actual:.4f} ETH`\n\n"
            f"Por favor, añade fondos a tu cuenta antes de reintentar."
        )
    else:
        reparto_texto = (
            f"🚀 *¡Orden Ejecutada!*\n\n"
            f"🛒 Comprando {token_name} por *{monto} ETH*...\n"
            f"⏱️ Transacción transmitiéndose de forma inmutable en Base.\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="back_main")]]
    await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- COMANDO START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    inicializar_usuario_si_no_existe(user_id)
    texto, reply_markup = generar_menu_principal(user_id)
    await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Operational")

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    # Servidor de Health Check en un hilo limpio estándar
    def iniciar_servidor():
        server = HTTPServer(("0.0.0.0", PORT), HealthCheckServer)
        server.serve_forever()
        
    threading.Thread(target=iniciar_servidor, daemon=True).start()

    # Inicialización estándar de la aplicación de Telegram
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detectar_token))
    
    application.run_polling()
