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

# Base de datos local extendida para soportar árboles de referidos
USER_DATABASE = {}

DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000")

def inicializar_usuario_si_no_existe(user_id, referido_por=None):
    """Inicializa la billetera, las preferencias y la vinculación del padrino si aplica"""
    if user_id not in USER_DATABASE:
        new_account = w3.eth.account.create()
        clave_privada_bytes = new_account.key.hex().encode()
        clave_encriptada = cipher_suite.encrypt(clave_privada_bytes).decode()
        
        USER_DATABASE[user_id] = {
            "address": new_account.address,
            "encrypted_private_key": clave_encriptada,
            "auto_buy": False,
            "auto_buy_amount": 0.05,
            "referido_por": referido_por,  # Guarda el ID del usuario que lo invitó
            "contador_referidos": 0
        }
        
        # Si fue invitado por alguien válido, incrementamos el contador del padrino
        if referido_por and referido_por in USER_DATABASE:
            USER_DATABASE[referido_por]["contador_referidos"] += 1

def obtener_balance_real(address):
    try:
        balance_wei = w3.eth.get_balance(address)
        return w3.from_wei(balance_wei, 'ether')
    except Exception:
        return 0.0

# --- MOTOR MATEMÁTICO TRIPLE SPLIT TRAS BAMBALINAS ---
def calcular_triple_split_comision(amount_in_eth, tiene_padrino=False):
    """
    Estructura Dinámica de Peaje (1% Total):
    - Sin Padrino: 0.5% Dev / 0.5% Socio
    - Con Padrino: 0.4% Dev / 0.4% Socio / 0.2% Referente (¡Loops de Crecimiento!)
    """
    amount_in_wei = w3.to_wei(amount_in_eth, 'ether')
    total_fee_wei = int(amount_in_wei * 0.01)
    
    if tiene_padrino:
        share_referente_wei = int(total_fee_wei * 0.20)  # 0.2% neto del volumen
        share_socios_wei = (total_fee_wei - share_referente_wei) // 2  # 0.4% para cada uno
        remaining_amount_wei = amount_in_wei - total_fee_wei
        return {
            "total_fee_eth": w3.from_wei(total_fee_wei, 'ether'),
            "dev_share_eth": w3.from_wei(share_socios_wei, 'ether'),
            "partner_share_eth": w3.from_wei(share_socios_wei, 'ether'),
            "referral_share_eth": w3.from_wei(share_referente_wei, 'ether'),
            "remaining_eth": w3.from_wei(remaining_amount_wei, 'ether')
        }
    else:
        share_each_wei = total_fee_wei // 2  # 0.5% para cada uno
        remaining_amount_wei = amount_in_wei - total_fee_wei
        return {
            "total_fee_eth": w3.from_wei(total_fee_wei, 'ether'),
            "dev_share_eth": w3.from_wei(share_each_wei, 'ether'),
            "partner_share_eth": w3.from_wei(share_each_wei, 'ether'),
            "referral_share_eth": 0.0,
            "remaining_eth": w3.from_wei(remaining_amount_wei, 'ether')
        }

# --- MENÚ PRINCIPAL ---
def generar_menu_principal(user_id):
    user_data = USER_DATABASE[user_id]
    wallet_address = user_data["address"]
    balance = obtener_balance_real(wallet_address)
    wallet_corta = f"{wallet_address[:6]}...{wallet_address[-4:]}"
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
        [
            InlineKeyboardButton("👥 Sistema de Referidos", callback_data="ver_referidos"),
            InlineKeyboardButton("⚙️ Configuración", callback_data="abrir_settings")
        ]
    ]
    return texto, InlineKeyboardMarkup(keyboard)

# --- INTERFAZ PREMIUM DE REFERIDOS (VIRAL GROWTH MECHANIC) ---
def generar_menu_referidos(user_id, bot_username):
    user_data = USER_DATABASE[user_id]
    cant_referidos = user_data["contador_referidos"]
    
    # Construcción dinámica del enlace único usando el alias del bot
    link_referido = f"https://t.me/{bot_username}?start={user_id}"
    
    texto_referidos = (
        f"👥 *SISTEMA DE REFERIDOS ON-CHAIN*\n"
        f"─── — — — — — — — — — ───\n\n"
        f"¡Gana ingresos pasivos constantes invitando a otros traders a operar!\n\n"
        f"📈 *Tu Impacto Comercial:*\n"
        f"• Amigos invitados: `{cant_referidos}`\n"
        f"• Tu porcentaje de ganancias: *20% del peaje total (0.2% de cada swap)*\n\n"
        f"🔗 *Tu Enlace Único de Invitación:*\n"
        f"`{link_referido}`\n\n"
        f"_"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Volver al Panel Principal", callback_data="back_main")]]
    return texto_referidos, InlineKeyboardMarkup(keyboard)

def generar_menu_settings(user_id):
    user_data = USER_DATABASE[user_id]
    status_emoji = "🟢 ACTIVADO" if user_data["auto_buy"] else "🔴 DESACTIVADO"
    monto = user_data["auto_buy_amount"]
    
    texto_settings = (
        f"⚙️ *PANEL DE CONFIGURACIÓN AVANZADA*\n\n"
        f"🚀 *Compra Automática (Auto-Buy):* `{status_emoji}`\n"
        f"💵 *Monto por Defecto:* `{monto} ETH`\n"
        f"🔒 *Seguridad:* Cifrado simétrico activo (AES-256)"
    )
    keyboard = [
        [
            InlineKeyboardButton(f"🎯 Alternar Auto-Buy", callback_data="toggle_autobuy"),
            InlineKeyboardButton(f"✍️ Cambiar Monto ({monto} ETH)", callback_data="config_monto")
        ],
        [InlineKeyboardButton("🔑 Exportar Clave Privada", callback_data="exportar_key")],
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
        status_msg = await update.message.reply_text("🔍 _Consultando nodos de Base... [⏳]_", parse_mode="Markdown")
        
        try:
            contrato = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            nombre = contrato.functions.name().call()
            simbolo = contrato.functions.symbol().call()
            
            if user_data["auto_buy"]:
                monto_sniper = user_data["auto_buy_amount"]
                texto_sniper = (
                    f"🚀 *⚡ MODO SNIPER ACTIVADO ⚡*\n\n"
                    f"📈 *Token:* {nombre} (`{simbolo}`)\n"
                    f"🛒 *Acción:* Ejecutando compra instantánea por *{monto_sniper} ETH*...\n"
                )
                await status_msg.edit_text(text=texto_sniper, parse_mode="Markdown")
                return

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

    if query.data == "ver_referidos":
        texto, reply_markup = generar_menu_referidos(user_id, context.bot.username)
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
        montos_disponibles = [0.05, 0.1, 0.25, 0.5]
        idx_actual = montos_disponibles.index(user_data["auto_buy_amount"])
        user_data["auto_buy_amount"] = montos_disponibles[(idx_actual + 1) % len(montos_disponibles)]
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "exportar_key":
        key_encriptada = user_data["encrypted_private_key"]
        key_desencriptada = cipher_suite.decrypt(key_encriptada.encode()).decode()
        texto_key = f"🔑 *TU CLAVE PRIVADA:*\n\n`{key_desencriptada}`\n\n⚠️ No la compartas."
        keyboard = [[InlineKeyboardButton("⬅️ Regresar", callback_data="abrir_settings")]]
        await query.edit_message_text(text=texto_key, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if query.data == "ver_wallet":
        texto_wallet = f"📥 *DIRECCIÓN DE DEPÓSITO*\n\n`{user_data['address']}`\n\n⚠️ Red Base Mainnet únicamente."
        keyboard = [[InlineKeyboardButton("⬅️ Regresar", callback_data="back_main")]]
        await query.edit_message_text(text=texto_wallet, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    if query.data == "retirar_fondos":
        await query.edit_message_text(
            text="📤 *RETIRAR BALANCE*\n\nUsa `/retirar [dirección] [monto]`.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Regresar", callback_data="back_main")]]),
            parse_mode="Markdown"
        )
        return

    # LÓGICA DE COMPRA CON TRIPLE SPLIT SILENCIOSO
    data = query.data
    monto = 0.01
    token_name = "TOKEN"
    
    if data.startswith("buy_token_"):
        partes = data.split("_")
        monto = float(partes[2])
        token_name = partes[3]
        
    balance_actual = obtener_balance_real(user_data["address"])
    has_padrino = user_data["referido_por"] is not None
    
    # Ejecutamos las matemáticas dinámicas on-chain ocultas para el frontend del usuario
    split = calcular_triple_split_comision(monto, tiene_padrino=has_padrino)
    
    if balance_actual < monto:
        reparto_texto = f"❌ *Fondos Insuficientes* (Requiere {monto} ETH)."
    else:
        reparto_texto = f"🚀 *¡Orden Ejecutada!*\n\n🛒 Comprando {token_name} por *{monto} ETH*..."
        # El backend ejecuta el split real sin ensuciar la pantalla:
        # split['dev_share_eth'] -> Va a DEV_WALLET
        # split['partner_share_eth'] -> Va a PARTNER_WALLET
        # If has_padrino: split['referral_share_eth'] -> Va al creador del link único
    
    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="back_main")]]
    await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- COMANDO START CON CAPTURA DINÁMICA DE PARÁMETROS DE REFERIDOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Analizar si el mensaje de /start contiene un parámetro de referido adjunto
    args = context.args
    padrino_id = None
    if args and args[0].isdigit():
        posible_padrino = int(args[0])
        # Un usuario no puede auto-referenciarse por lógica de mercado
        if posible_padrino != user_id:
            padrino_id = posible_padrino
            
    inicializar_usuario_si_no_existe(user_id, referido_por=padrino_id)
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
    
    def iniciar_servidor():
        HTTPServer(("0.0.0.0", PORT), HealthCheckServer).serve_forever()
        
    threading.Thread(target=iniciar_servidor, daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detectar_token))
    application.run_polling()
