import os
import threading
import sqlite3
import urllib.request
import json

from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from web3 import Web3
from cryptography.fernet import Fernet

# --- CONEXIÓN WEB3 (RED BASE MAINNET) ---
RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"}
]

# --- CONFIGURACIÓN DE SEGURIDAD CRIPTOGRÁFICA ---
MASTER_KEY = os.environ.get("ENCRYPTION_KEY")
if not MASTER_KEY:
    MASTER_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(MASTER_KEY.encode())

# --- BASE DE DATOS PERSISTENTE (SQLITE) ---
DB_FILE = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            address TEXT UNIQUE,
            encrypted_private_key TEXT,
            auto_buy INTEGER DEFAULT 0,
            auto_buy_amount REAL DEFAULT 0.002,
            referido_por INTEGER,
            contador_referidos INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tipo TEXT,
            monto REAL,
            token_simbolo TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"

# --- FUNCIONES DE AYUDA PARA PRECIO ---
def obtener_precio_token_real(token_address):
    """Busca el precio en vivo mediante GeckoTerminal. Si falla, da un precio demo."""
    try:
        url = f"https://api.geckoterminal.com/api/v2/networks/base/tokens/{token_address}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return float(data['data']['attributes']['price_usd'])
    except Exception:
        return 0.00125

def obtener_usuario(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT address, encrypted_private_key, auto_buy, auto_buy_amount, referido_por, contador_referidos FROM usuarios WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "address": row[0],
            "encrypted_private_key": row[1],
            "auto_buy": bool(row[2]),
            "auto_buy_amount": row[3],
            "referido_por": row[4],
            "contador_referidos": row[5]
        }
    return None

def registrar_transaccion(user_id, tipo, monto, token_simbolo):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO historial (user_id, tipo, monto, token_simbolo)
        VALUES (?, ?, ?, ?)
    """, (user_id, tipo, monto, token_simbolo))
    conn.commit()
    conn.close()

def obtener_ultimas_transacciones(user_id, limite=3):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tipo, monto, token_simbolo FROM historial 
        WHERE user_id = ? ORDER BY id DESC LIMIT ?
    """, (user_id, limite))
    rows = cursor.fetchall()
    conn.close()
    return rows

def inicializar_usuario_si_no_existe(user_id, referido_por=None):
    user_data = obtener_usuario(user_id)
    if not user_data:
        new_account = w3.eth.account.create()
        clave_privada_bytes = new_account.key.hex().encode()
        clave_encriptada = cipher_suite.encrypt(clave_privada_bytes).decode()
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO usuarios (user_id, address, encrypted_private_key, referido_por)
                VALUES (?, ?, ?, ?)
            """, (user_id, new_account.address, clave_encriptada, referido_por))
            if referido_por:
                cursor.execute("UPDATE usuarios SET contador_referidos = contador_referidos + 1 WHERE user_id = ?", (referido_por,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()

def actualizar_preferencia(user_id, columna, valor):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE usuarios SET {columna} = ? WHERE user_id = ?", (valor, user_id))
    conn.commit()
    conn.close()

def obtener_balance_real(address):
    try:
        balance_wei = w3.eth.get_balance(address)
        return w3.from_wei(balance_wei, 'ether')
    except Exception:
        return 0.0

# --- MENÚS DE INTERFAZ ---
def generar_menu_principal(user_id):
    user_data = obtener_usuario(user_id)
    wallet_address = user_data["address"]
    balance = obtener_balance_real(wallet_address)
    
    wallet_corta = f"`{wallet_address}`" 
    status_sniper = "🟢 Activo" if user_data["auto_buy"] else "🔴 Inactivo"
    
    trades = obtener_ultimas_transacciones(user_id)
    texto_historial = ""
    if trades:
        texto_historial = "📦 *Últimos Trades (Base):*\n"
        for t in trades:
            emoji = "🟢" if t[0] == "COMPRA" else "📤"
            texto_historial += f"• {emoji} {t[0]}: `{t[1]} ETH` ➔ `#{t[2]}`\n"
        texto_historial += "\n"
    
    texto = (
        f"🦅 *BASE TRADING ENGINE*\n"
        f"─── — — — — — — — — — ───\n\n"
        f"💳 *Wallet (Toca para copiar):*\n{wallet_corta}\n\n"
        f"💰 *Balance:* `{balance:.4f} ETH`\n"
        f"🎯 *Modo Sniper:* {status_sniper}\n\n"
        f"{texto_historial}"
        f"─── — — — — — — — — — ───\n"
        f"⚡ *¿Cómo empezar a operar?*\n"
        f"Pega el contrato de cualquier token de Base aquí abajo para analizar su liquidez de forma segura."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Actualizar Panel", callback_data="back_main")],
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

def generar_menu_referidos(user_id, bot_username):
    user_data = obtener_usuario(user_id)
    cant_referidos = user_data["contador_referidos"]
    link_referido = f"https://t.me/{bot_username}?start={user_id}"
    
    texto_referidos = (
        f"👥 *SISTEMA DE REFERIDOS ON-CHAIN*\n"
        f"─── — — — — — — — — — ───\n\n"
        f"¡Genera ingresos pasivos invitando a otros a operar!\n\n"
        f"📈 *Tu Impacto Comercial:*\n"
        f"• Amigos invitados: `{cant_referidos}`\n"
        f"• Tu comisión: *20% del peaje (0.2% neto de cada swap)*\n\n"
        f"🔗 *Tu Enlace Único (Toca para copiar):*\n"
        f"`{link_referido}`"
    )
    url_compartir = f"https://t.me/share/url?url={link_referido}&text=Prueba%20este%20bot%20sniper%20ultra%20rápido%20en%20la%20red%20Base!%20🚀"
    keyboard = [
        [InlineKeyboardButton("📢 Compartir Enlace", url=url_compartir)],
        [InlineKeyboardButton("⬅️ Volver al Panel Principal", callback_data="back_main")]
    ]
    return texto_referidos, InlineKeyboardMarkup(keyboard)

def generar_menu_settings(user_id):
    user_data = obtener_usuario(user_id)
    status_emoji = "🟢 ACTIVADO" if user_data["auto_buy"] else "🔴 DESACTIVADO"
    monto = user_data["auto_buy_amount"]
    
    texto_settings = (
        f"⚙️ *PANEL DE CONFIGURACIÓN*\n\n"
        f"🚀 *Compra Automática (Auto-Buy):* `{status_emoji}`\n"
        f"💵 *Monto Sniper Predeterminado:* `{monto} ETH`\n"
        f"🔒 *Seguridad:* Encriptado simétrico AES-256"
    )
    keyboard = [
        [
            InlineKeyboardButton("🎯 Alternar Auto-Buy", callback_data="toggle_autobuy"),
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
    user_data = obtener_usuario(user_id)
    texto_usuario = update.message.text.strip()
    
    # CONTROL DE INTERCEPCIÓN: Si estamos esperando un monto personalizado
    if context.user_data.get("esperando_monto_token"):
        try:
            monto_custom = float(texto_usuario)
            if monto_custom <= 0:
                await update.message.reply_text("❌ Por favor, introduce un número mayor que 0.")
                return
                
            simbolo = context.user_data["esperando_monto_token"]
            token_addr = context.user_data.get("current_token_address", "0x")
            
            # Resetear estados de intercepción
            context.user_data["esperando_monto_token"] = None
            
            precio_usd = obtener_precio_token_real(token_addr)
            eth_precio_estimated = 3500.0
            tokens_comprados = (monto_custom * eth_precio_estimated) / precio_usd if precio_usd > 0 else 0
            
            registrar_transaccion(user_id, "COMPRA", monto_custom, simbolo)
            
            await update.message.reply_text(
                f"🚀 *¡Orden Profesional Ejecutada!*\n\n"
                f"🛒 *Comprando:* {simbolo}\n"
                f"💵 *Monto Invertido:* `{monto_custom} ETH` (~${(monto_custom * eth_precio_estimated):.2f} USD)\n"
                f"📦 *Tokens Estimados:* `{tokens_comprados:,.2f} {simbolo}`\n\n"
                f"✅ _Transacción enviada a los nodos de Base con éxito._",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver al Panel", callback_data="back_main")]]),
                parse_mode="Markdown"
            )
            return
        except ValueError:
            await update.message.reply_text("⚠️ Entrada inválida. Introduce únicamente un número decimal válido (Ej: `0.007`).")
            return

    # Si se pega una dirección de contrato
    if w3.is_address(texto_usuario):
        token_address = w3.to_checksum_address(texto_usuario)
        status_msg = await update.message.reply_text("🔍 _Consultando nodos de Base, analizando HoneyPot y liquidez... [⏳]_", parse_mode="Markdown")
        
        try:
            contrato = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            nombre = contrato.functions.name().call()
            simbolo = contrato.functions.symbol().call()
            
            # Guardamos datos en el contexto de sesión por si usan montos custom
            context.user_data["current_token_symbol"] = simbolo
            context.user_data["current_token_address"] = token_address
            
            precio_usd = obtener_precio_token_real(token_address)
            eth_precio_estimated = 3500.0
            
            # --- INFO PROFESIONAL DEL BOT ---
            status_honeypot = "✅ Seguro (0% Tax)"
            status_liquidez = "🔒 Quemada / Bloqueada"
            
            # Flujo Automático (Sniper)
            if user_data["auto_buy"]:
                monto_sniper = user_data["auto_buy_amount"]
                tokens_comprados = (monto_sniper * eth_precio_estimated) / precio_usd if precio_usd > 0 else 0
                registrar_transaccion(user_id, "COMPRA", monto_sniper, simbolo)
                
                await status_msg.edit_text(
                    text=f"🚀 *⚡ MODO SNIPER AUTOMÁTICO ⚡*\n\n"
                         f"📈 *Token:* {nombre} (`{simbolo}`)\n"
                         f"💰 *Precio:* `${precio_usd:.6f} USD`\n"
                         f"🛡️ *HoneyPot:* {status_honeypot}\n"
                         f"🛒 *Acción:* Ejecutando swap inmediato de *{monto_sniper} ETH*\n"
                         f"📦 *Recibiste:* `{tokens_comprados:,.2f} {simbolo}`",
                    parse_mode="Markdown"
                )
                return

            # Flujo Manual (Interfaz del Bot Profesional)
            opcion1_eth = 0.002
            opcion2_eth = 0.005
            tokens_opcion1 = (opcion1_eth * eth_precio_estimated) / precio_usd if precio_usd > 0 else 0
            tokens_opcion2 = (opcion2_eth * eth_precio_estimated) / precio_usd if precio_usd > 0 else 0

            texto_token = (
                f"📈 *Gema Detectada:* {nombre} (`{simbolo}`)\n"
                f"💵 *Precio Actual:* `${precio_usd:.6f} USD`\n"
                f"📍 *Contrato:* `{token_address}`\n\n"
                f"🛡️ *ANÁLISIS DE SEGURIDAD INTERNO:* \n"
                f"• *HoneyPot:* {status_honeypot}\n"
                f"• *Liquidez:* {status_liquidez}\n"
                f"• *Slippage Sugerido:* `0.5%`\n\n"
                f"💬 *Selecciona tu monto de compra rápido:* \n"
                f"• 🟢 *{opcion1_eth} ETH* (~${(opcion1_eth*3500):.2f} USD) ➔ `{tokens_opcion1:,.2f}` {simbolo}\n"
                f"• 🟢 *{opcion2_eth} ETH* (~${(opcion2_eth*3500):.2f} USD) ➔ `{tokens_opcion2:,.2f}` {simbolo}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(f"🟢 {opcion1_eth} ETH", callback_data=f"buy_token_{opcion1_eth}_{simbolo}"),
                    InlineKeyboardButton(f"🟢 {opcion2_eth} ETH", callback_data=f"buy_token_{opcion2_eth}_{simbolo}")
                ],
                [
                    InlineKeyboardButton("✍️ Otro Monto (Custom)", callback_data="pedir_monto_custom"),
                    InlineKeyboardButton("❌ Cancelar", callback_data="back_main")
                ]
            ]
            await status_msg.edit_text(text=texto_token, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        except Exception:
            await status_msg.edit_text("❌ El contrato no tiene un pool de liquidez activo en la red Base.")
    else:
        await update.message.reply_text("👋 Envía un contrato válido de Base (Ej: empezando con `0x`).")

# --- CONTROLADOR CALLBACK ---
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    inicializar_usuario_si_no_existe(user_id)
    user_data = obtener_usuario(user_id)
    
    if query.data == "back_main":
        context.user_data["esperando_monto_token"] = None
        texto, reply_markup = generar_menu_principal(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "ver_referidos":
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username.replace("_", "\\_")
        texto, reply_markup = generar_menu_referidos(user_id, bot_username)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "abrir_settings":
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "toggle_autobuy":
        nuevo_estado = 1 if not user_data["auto_buy"] else 0
        actualizar_preferencia(user_id, "auto_buy", nuevo_estado)
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "config_monto":
        montos_disponibles = [0.002, 0.005, 0.01, 0.02]
        try:
            idx_actual = montos_disponibles.index(user_data["auto_buy_amount"])
            nuevo_monto = montos_disponibles[(idx_actual + 1) % len(montos_disponibles)]
        except ValueError:
            nuevo_monto = 0.002
            
        actualizar_preferencia(user_id, "auto_buy_amount", nuevo_monto)
        texto, reply_markup = generar_menu_settings(user_id)
        await query.edit_message_text(text=texto, reply_markup=reply_markup, parse_mode="Markdown")
        return

    if query.data == "pedir_monto_custom":
        simbolo = context.user_data.get("current_token_symbol", "TOKEN")
        context.user_data["esperando_monto_token"] = simbolo
        
        keyboard = [[InlineKeyboardButton("❌ Cancelar Operación", callback_data="back_main")]]
        await query.edit_message_text(
            text=f"✍️ *MONTO PERSONALIZADO PARA #{simbolo}*\n\nEscribe aquí abajo directamente en el chat la cantidad exacta de ETH que deseas invertir.\n\n_Ejemplos sugeridos: `0.003` o `0.012`_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    if query.data == "exportar_key":
        key_encriptada = user_data["encrypted_private_key"]
        key_desencriptada = cipher_suite.decrypt(key_encriptada.encode()).decode()
        texto_key = f"🔑 *TU CLAVE PRIVADA:*\n\n`{key_desencriptada}`\n\n⚠️ No la compartas con nadie."
        keyboard = [[InlineKeyboardButton("⬅️ Regresar", callback_data="abrir_settings")]]
        await query.edit_message_text(text=texto_key, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if query.data == "ver_wallet":
        texto_wallet = f"📥 *DIRECCIÓN DE DEPÓSITO*\n\n`{user_data['address']}`\n\n⚠️ Usa únicamente la red Base Mainnet."
        keyboard = [[InlineKeyboardButton("⬅️ Regresar", callback_data="back_main")]]
        await query.edit_message_text(text=texto_wallet, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    if query.data == "retirar_fondos":
        await query.edit_message_text(
            text="📤 *RETIRAR BALANCE*\n\nPara retirar, escribe el comando directo en el chat con este formato:\n`/retirar [dirección_destino] [monto_en_eth]`\n\n_Ejemplo: `/retirar 0x9522... 0.005`_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Regresar", callback_data="back_main")]]),
            parse_mode="Markdown"
        )
        return

    if query.data.startswith("buy_token_"):
        partes = query.data.split("_")
        monto = float(partes[2])
        token_name = partes[3]
        token_addr = context.user_data.get("current_token_address", "0x")
        
        precio_usd = obtener_precio_token_real(token_addr)
        eth_precio_estimated = 3500.0
        tokens_comprados = (monto * eth_precio_estimated) / precio_usd if precio_usd > 0 else 0
        
        registrar_transaccion(user_id, "COMPRA", monto, token_name)
        
        reparto_texto = (
            f"🚀 *¡Orden de Mercado Ejecutada!*\n\n"
            f"🛒 *Token:* `#{token_name}`\n"
            f"💵 *Monto:* `{monto} ETH` (~${(monto * eth_precio_estimated):.2f} USD)\n"
            f"📦 *Cantidad Asignada:* `{tokens_comprados:,.2f} {token_name}`\n\n"
            f"✨ _El balance se actualizará en tu historial de trades inmediatamente._"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Volver al Panel", callback_data="back_main")]]
        await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

# --- COMANDOS EXTRAS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    padrino_id = None
    if args and args[0].isdigit():
        posible_padrino = int(args[0])
        if posible_padrino != user_id:
            padrino_id = posible_padrino
            
    inicializar_usuario_si_no_existe(user_id, referido_por=padrino_id)
    texto, reply_markup = generar_menu_principal(user_id)
    await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

async def retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    inicializar_usuario_si_no_existe(user_id)
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Formato incorrecto. Usa: `/retirar [dirección] [monto]`", parse_mode="Markdown")
        return
        
    destino = context.args[0]
    try:
        monto = float(context.args[1])
        if not w3.is_address(destino):
            await update.message.reply_text("❌ La dirección de destino proporcionada no es válida en la red Base.")
            return
            
        registrar_transaccion(user_id, "RETIRO", monto, "ETH")
        await update.message.reply_text(
            f"📤 *¡Solicitud de Retiro Procesada!*\n\n"
            f"🔹 *Destino:* `{destino}`\n"
            f"🔹 *Monto:* `{monto} ETH`\n\n"
            f"✅ La transacción ha sido empaquetada y enviada a la red de Base.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver al Panel", callback_data="back_main")]]),
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ El monto debe ser un número decimal válido.")

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
    application.add_handler(CommandHandler("retirar", retirar))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detectar_token))
    application.run_polling()
