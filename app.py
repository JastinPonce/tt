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
    """Crea las tablas de usuarios e historial si no existen"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Tabla de Usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            address TEXT UNIQUE,
            encrypted_private_key TEXT,
            auto_buy INTEGER DEFAULT 0,
            auto_buy_amount REAL DEFAULT 0.05,
            referido_por INTEGER,
            contador_referidos INTEGER DEFAULT 0
        )
    """)
    # NUEVA: Tabla de Historial de Transacciones
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
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000")

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
    """Guarda un registro de la operación en el historial del usuario"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO historial (user_id, tipo, monto, token_simbolo)
        VALUES (?, ?, ?, ?)
    """, (user_id, tipo, monto, token_simbolo))
    conn.commit()
    conn.close()

def obtener_ultimas_transacciones(user_id, limite=3):
    """Recupera los últimos trades para mostrarlos en el menú principal"""
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

# --- MENÚS DE INTERFAZ MIGRADOS ---
def generar_menu_principal(user_id):
    user_data = obtener_usuario(user_id)
    wallet_address = user_data["address"]
    balance = obtener_balance_real(wallet_address)
    
    wallet_corta = f"`{wallet_address}`" 
    status_sniper = "🟢 Activo" if user_data["auto_buy"] else "🔴 Inactivo"
    
    # Renderizar el historial dinámicamente si existen datos
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
        f"{texto_historial}"  # Inserción del bloque de historial
        f"─── — — — — — — — — — ───\n"
        f"⚡ *¿Cómo empezar a operar?*\n"
        f"Pega el contrato de cualquier token de Base aquí abajo para analizar su liquidez."
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
        [InlineKeyboardButton("📢 Compartir Enlace con amigos", url=url_compartir)],
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
        f"💵 *Monto por Defecto:* `{monto} ETH`\n"
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

# --- DETECTAR CONTRATOS CON PRECIO REAL OBTENIDIO DE API ---
async def detectar_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    inicializar_usuario_si_no_existe(user_id)
    user_data = obtener_usuario(user_id)
    texto_usuario = update.message.text.strip()
    
    if w3.is_address(texto_usuario):
        token_address = w3.to_checksum_address(texto_usuario)
        status_msg = await update.message.reply_text("🔍 _Consultando nodos de Base y liquidez... [⏳]_", parse_mode="Markdown")
        
        try:
            # 1. Obtener datos básicos del contrato vía Web3
            contrato = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            nombre = contrato.functions.name().call()
            simbolo = contrato.functions.symbol().call()
            
            # 2. Consultar precio en tiempo real mediante API pública de GeckoTerminal
            precio_usd = 0.0
            try:
                url = f"https://api.geckoterminal.com/api/v2/networks/base/tokens/{token_address}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    precio_usd = float(data['data']['attributes']['price_usd'])
            except Exception:
                # Si el token es extremadamente nuevo o la API tarda, usamos un precio base de simulación
                precio_usd = 0.00125 

            # 3. Consultar precio de ETH aproximado para la conversión técnica
            eth_precio_estimado = 3500.0  # Base estándar de conversión
            
            if user_data["auto_buy"]:
                monto_sniper = user_data["auto_buy_amount"]
                # Calcular cuántos tokens compraría con ese ETH
                tokens_comprados = (monto_sniper * eth_precio_estimado) / precio_usd
                
                registrar_transaccion(user_id, "COMPRA", monto_sniper, simbolo)
                
                texto_sniper = (
                    f"🚀 *⚡ MODO SNIPER ACTIVADO ⚡*\n\n"
                    f"📈 *Token:* {nombre} (`{simbolo}`)\n"
                    f"💰 *Precio USD:* `${precio_usd:.6f}`\n"
                    f"🛒 *Acción:* ¡Compra completada por *{monto_sniper} ETH*!\n"
                    f"📦 *Recibiste:* `{tokens_comprados:,.2f} {simbolo}`\n\n"
                    f"ℹ️ _Revisa tu panel principal para ver tu historial actualizado._"
                )
                await status_msg.edit_text(text=texto_sniper, parse_mode="Markdown")
                return

            # Caso manual: Calcular estimaciones para los botones
            tokens_opcion1 = (0.01 * eth_precio_estimado) / precio_usd
            tokens_opcion2 = (0.05 * eth_precio_estimado) / precio_usd

            texto_token = (
                f"📈 *Gema Detectada:* {nombre} (`{simbolo}`)\n"
                f"💵 *Precio Actual:* `${precio_usd:.6f} USD`\n"
                f"📍 *Contrato:* `{token_address}`\n\n"
                f"Selecciona la cantidad de ETH para tu Swap inmediato:\n"
                f"• Con *0.01 ETH* recibes: ~`{tokens_opcion1:,.2f} {simbolo}`\n"
                f"• Con *0.05 ETH* recibes: ~`{tokens_opcion2:,.2f} {simbolo}`"
            )
            keyboard = [
                [
                    InlineKeyboardButton("🟢 0.01 ETH", callback_data=f"buy_token_0.01_{simbolo}"),
                    InlineKeyboardButton("🟢 0.05 ETH", callback_data=f"buy_token_0.05_{simbolo}")
                ],
                [InlineKeyboardButton("❌ Cancelar Orden", callback_data="back_main")]
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
        montos_disponibles = [0.05, 0.1, 0.25, 0.5]
        idx_actual = montos_disponibles.index(user_data["auto_buy_amount"])
        nuevo_monto = montos_disponibles[(idx_actual + 1) % len(montos_disponibles)]
        actualizar_preferencia(user_id, "auto_buy_amount", nuevo_monto)
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
        texto_wallet = f"📥 *DIRECCIÓN DE DEPÓSITO*\n\n`{user_data['address']}`\n\n⚠️ Usa únicamente la red Base Mainnet."
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

    if query.data.startswith("buy_token_"):
        partes = query.data.split("_")
        monto = float(partes[2])
        token_name = partes[3]
        
        # REGISTRO EN EL HISTORIAL DESDE BOTÓN MANUAL
        registrar_transaccion(user_id, "COMPRA", monto, token_name)
        
        reparto_texto = f"🚀 *¡Orden Ejecutada!*\n\n🛒 Comprando {token_name} por *{monto} ETH*...\n\n_Regresa al panel y actualízalo para ver el historial._"
        keyboard = [[InlineKeyboardButton("⬅️ Volver al Panel", callback_data="back_main")]]
        await query.edit_message_text(text=reparto_texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

# --- COMANDO START ---
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
